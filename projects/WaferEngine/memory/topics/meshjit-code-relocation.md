---
summary: MeshJIT/WaferLLM fabric code relocation and pageability — silicon-validated address-matched-slot rule, pipelined hardware router multicast cost model, real c512 function sizes/use times, CS-3 vecmat holder proof, Q+K RoPE negative economics, and Attention/FFN shared-slot ownership gates.
tags: [waferengine, wse3, meshjit, code-relocation, multicast, sram, prefill, tsc]
---

# MeshJIT code relocation (relieving the .text-dominated prefill PE)

## Why this exists

[[pe-sram-memory-breakdown]] found `.text` is the #1 per-PE cost and the **prefill compute PE is
the binding constraint of the whole real deployment (88.9% c256 / 91.7% c512, only ~4–5 KB free)**.
MeshJIT is the mitigation: fetch cold kernel `.text` over the fabric from a holder PE at phase
boundaries instead of keeping every kernel resident (skill `wse-runtime-remote-code-loading`).
This topic records what is validated on silicon and what the cost model says. Perf for prefill is a
non-issue (long compute-bound run; fabric fetch is ~µs vs ~7 s host / ~506 ms device); the binding
question is relocation **correctness** and whether per-phase reuse pays off.

## Relocation correctness — the refined rule (silicon-validated 2026-08-04)

The skill's invariant #1 ("relocated code must be leaf + branch-free") is **too strong**. Tested
the branch half in `~/MeshJIT/controlflow-experiment/`: holder→receiver byte transfer +
`@bitcast`-jump; the discriminating knob is receiver slot address vs candidate source address.

| candidate | slot ≠ src (0xb000), sim | slot = src (0xa800), sim |
| --- | --- | --- |
| straight-line (mul/add/madd) | PASS | PASS |
| **forward branch** (`if x>0`) | **PASS** | PASS |
| **backward branch / loop** | **STALL/hang** | **PASS** |

Only the slot address changed between loop PASS↔STALL ⇒ **backward/loop branches are
absolute-encoded (position-DEPENDENT); forward conditionals and straight-line code are
position-INDEPENDENT and relocate freely.**

**Real CS-3 confirmation (physical wafer, 2026-08-04):** the **address-matched** config (slot
0xa800 = `cand_loop` source) ran on the EPCC wafer (cloud SdkCompiler `--fabric-dims=762,1172` +
SdkLauncher; RoCE egress to 10.27.28.180..198) and **ALL candidates PASSED, incl. the loop** —
bit-exact. The mismatched loop was NOT run on the appliance (would likely hang the wsjob); its
stall is sim-confirmed only.

Refined rule: transplanted code may contain **forward** conditionals, but a **backward branch
(loop)** only runs correctly if the receiver slot is at the **same address** as the source (or
branch immediates are patched by the slot−source delta after copy). Since real kernels are
loop-heavy, MeshJIT-offloading them needs ONE of:
1. **address-matched slots** — link each offloadable kernel to a fixed addr, receiver slot at that
   same addr. Zero codegen change, just placement discipline. **Validated on silicon = the concrete
   unblock.**
2. **post-copy branch relocation** — patch absolute branch immediates on the receiver (needs the
   undocumented WSE-3 branch encoding → reverse-engineer).
3. **PIC codegen** — a cslc PC-relative-backward-branch mode, if it exists.

**Untested:** the leaf half — init/teardown also *call* helpers (non-leaf). Next: a candidate that
calls a helper, to test the leaf half independently.

## Hardware multicast cost (physical CS-3, 0.85 GHz)

`~/MeshJIT/broadcast-timing/`. Single-color router line: holder `RAMP->EAST`; interior
`WEST->{RAMP,EAST}`; endpoint `WEST->RAMP`. Holder injects once — not sequential unicast, software
relay, or a tree. Receivers pre-arm async `@mov32` slot writes before the kick. SDK bandwidth-test
sync/tic/toc TSC; host applies `ref -= px+py` and reports
`max(receiver_toc-ref) - (holder_tic-ref)` (removes TSC offsets/reference-wave propagation, keeps
data propagation).

Physical endpoint cycles (`shortest / median`; N≤256 has 200 reps, N=512 has 50):

| K | N=1 | N=16 | N=64 | N=256 | N=512 |
|---:|---:|---:|---:|---:|---:|
| 64 B | 39 / 62 | 53 / 77 | 101 / 125 | 293 / 318 | 549 / 574 |
| 256 B | 93 / 150 | 107 / 168 | 155 / 214 | 347 / 406 | 603 / 662 |
| 1 KiB | 309 / 358 | 323 / 372 | 371 / 420 | 563 / 612 | 819 / 868 |
| 2 KiB | 597 / 646 | 655* / 660 | 659 / 708 | 851 / 900 | 1107 / 1156 |

`*` low dispatch mode not sampled at 2 KiB/N=16; fit predicts 611. Lower envelope, exact for all
tested K (u32 extents divisible by 8):

```text
T_shortest(N, K_bytes) = 20 + 9*K/32 + (N-1) cycles.
```

⇒ serialization paid once, wavefront advances **one router hop per cycle** — pipelined hardware
multicast, not `N*K`. At production row width N=512: 1 KiB = 819/868 cyc = 0.964/1.021 µs; 2 KiB =
1107/1156 cyc = 1.302/1.360 µs. Completion-task dispatch adds a repeatable second mode (~+49 cyc
for 1–2 KiB) — keep both minimum and median.

## Real c512 function sizes (PR #14 `a8ab2a5`, 512x1024 block, P=256, seq 8192, chunk 512)

Tight PE `.text` = **30,664 B** (matches `pe-sram-memory-breakdown` prefill c512).

- Fourteen compute-core functions total **14,168 B** (corrects the old candidate page's 14,372 B).
- Five independent phase candidates: qk_norm 1936, silu 1768, rmsnorm 1532, matmul 876, rope 776 B
  = 6,888 B. One shared 1,936 B slot ⇒ theoretical gross saving **4,952 B**.
- Nine attention-group functions total 7,280 B — call/dependency coupled, NOT yet independently
  swappable; **do not count this saving** until closure/multi-slot placement is solved.
- The old FUNC dump's 31,688 B includes the separate 1,024 B task table; the non-stub FUNC sum
  equals `.text` exactly at 30,664 B.

## Exact-body function-use (one PE at (511,0), 4-layer block, seq-8192 c512 request)

CS-3 job `wsjob-vuwqrxhrcxkzb2qetccra9`; each interval subtracts an 18-cycle back-to-back TSC read.

| function | calls | avg cycles | total cycles | total @0.85 GHz |
|---|---:|---:|---:|---:|
| rmsnorm_kernel | 128 | 3549.13 | 454,289 | 534.46 µs |
| qk_norm | 64 | 925.50 | 59,232 | 69.68 µs |
| rope_kernel | 128 | 576.25 | 73,760 | 86.78 µs |
| silu_chunk | 192 | 855.00 | 164,160 | 193.13 µs |
| matmul_compute | 65,792 | 1148.19 | 75,541,967 | 88.873 ms |

Authoritative full-request device forward span: **430,044,189 cycles = 505.934 ms @0.85 GHz**
(host `run` 7.047 s — keep only for end-to-end budget).

## Decision: per-phase reuse promising, per-leaf fetch is not

With fixed payload buckets on the measured N=512 line, load/one-body-call is already >1 for
qk_norm, rope, and silu (1.20–1.51x median) ⇒ **never fetch per leaf invocation**. Matmul only wins
because one loaded body serves 257 step/final calls per projection.

Full-block extrapolation (**hypothesis, not measured**): a hardware comb over 512x1024 has longest
route `511+1023=1534` hops; assuming branch fan-out preserves line throughput, 1 KiB ≈ 1842/1891
cyc = 2.167/2.225 µs, 2 KiB ≈ 2130/2179 cyc = 2.506/2.564 µs. The five-function phase order with one
shared slot causes nine loads/layer-chunk (rmsnorm x2, matmul x4, qk_norm/rope/silu x1); over
4 layers x 16 chunks the extrapolated load cost is **1.335–1.368 ms = 0.264–0.270% of device
forward, ~0.019% of the host run, ~1.5% of these five bodies' total time.**

⇒ **hardware router multicast + phase-granularity reuse is promising for the five independent
kernels; per-leaf fetch is not.** Do not treat the 2-D numbers as measured.

Caveats: experiment uses color 6 + IQ5/OQ5; color 6 is stage-free in the qk_norm/rope/swiglu
snapshots, but production binds all 8 input + output queues — a real integration needs a drained
repaint/rebind/fence, there is no globally free dedicated queue pair. `matmul_compute` timing is
exact-body (excludes async fabric wait in later task-unblock paths, mixes MAC-step with final-cast
calls); one PE profiled, no uninstrumented A/B baseline.

## Next

1. Build + TSC-measure a one-color 2-D comb on a production-size rectangle; verify max-Manhattan
   path model + row-branch contention.
2. Audit a concrete production repaint/rebind schedule and its fence cost.
3. Prototype the five-kernel shared address-matched slot at real phase transitions.
4. Treat attention as a closure-placement problem, not nine independent functions.
5. Test the leaf half of the relocation rule (a candidate that calls a helper).

## Updates — 2026-08-14

Drained three 2026-08-12 WaferLLM/MeshJIT captures into this topic:

- `/home/lexu/WaferLLM/MeshJIT-Decode-GEMV/` proved a minimal SDK-2.10 runtime-pointer GEMV body substitution in simulator: an 8-byte `cand_gemv_step` FMACH body was copied holder `0xa000` → receiver `0xa000`, the receiver retained no candidate symbol, and non-constant K=N=8 GEMV output was bit-exact. This is a feasibility result only: gross body saving 8 B vs a 512-B slot; no SRAM-saving, timing, physical-WSE-3, or production-decode claim. SDK 2.10 rejects runtime function pointers inside lowered `@map`, so integration must use a resident direct-pointer traversal loop or a larger relocated driver, not an unchanged `@map(gemv_static_step, ...)`.
- `/home/lexu/WaferLLM/MeshJIT-Decode-Vecmat/` proved a larger `vecmat_computation`-boundary simulator substitution at WaferLLM main `fd1c2da`: candidate size 228 B / 57 u32, receiver 128-u32 slot at `0xa000`, final holder ELF has no external `gemv_static_step`, receiver ELF has neither candidate nor callback, and signed FP16 8×8 GEMV output was bit-exact. The holder/receiver `.vecmat_abi` section must be byte-identical (46 B at `0x8800`) and kept live explicitly; earlier receiver pruning caused `Invalid address 0x6000 for SRC1`. Treat ABI/DSD/global closure retention as part of the contract.
- The cross-experiment handoff confirms the next target remains one-projection decode-path substitution after an approved SDK-2.10-compatible resident Decode baseline is restored. Keep loop-driver relocation separate until its broader closure is reduced and independently debugged; do not use host wall time as load latency.

## Updates — 2026-08-15

Drained nine 2026-08-12..14 WaferLLM/MeshJIT/pageability captures into this topic:

- `/home/lexu/WaferLLM/MeshJit-Decode/mirror-xq-phase/` advanced the real Decode `vecmat_computation` proof from simulator to physical CS-3. The P=4, bsz=2 dedicated-holder layout uses 16 compute receivers, holder `(4,0)`, and three inert rectangle fillers. The holder stages the 264-B / 66-u32 body into address-matched receiver slots at `0xa000`; CS-3 readback proved the payload SHA-256 `0ff58e36fbcc36a8f41b859d4a72fdc8a177b42598956cbca181ba2003684aba` in all 16 prefixes with zero tails, and resident vs dynamic QKV output was bit-exact. Cloud-linked ELF audit confirms receiver candidate absence, identical 38-B ABI initial images, empty relocations, and holder/filler closure separation. This is a correctness result only: the current receiver still adds a 512-B slot and 320 B `.text`; no timing or net SRAM-saving claim.
- Static and simulator gates immediately before the CS-3 proof remain useful guardrails: a CSL rectangle cannot contain holes (hence the 5x4 holder/filler artifact), `csl-color-audit` refused the mirror because it lacks the expected `launch.py` so only a source-derived color ledger was recorded, P=2/group_num degenerates the two-phase all-reduce, and the first P=4 snake route stalled until NORTH row-start receive cases were added.
- SDK-2.10 production-shaped candidate profiling at WaferLLM `fd1c2da` gives final-link ownership upper bounds, not payload sizes: whole Attention 4,656 B `.text`, whole FFN 1,768 B `.text`, Q+K RoPE 1,056 B, softmax 996 B, score 836 B, QKV 816 B, up+gate 736 B, RMSNorm X/Z 656/648 B, SiLU+z3 192 B. Best next small correctness boundary is combined Q+K RoPE, but economics must account for ABI/profile/slot floor and load/use timing.
- The reusable WSE pageability audit installed on `gala2` separates source closure, linked symbol bytes, removable ownership, and dynamic receiver SRAM as distinct evidence grades. Applied to `happyandslow/WaferEngine` qwen3 decode at `fcfc8c1`, `rope_kernel` was the best first direct candidate (600 B linked, memory DSDs only, DSR ids 1--6), but equal-size candidate symbols had multiple payload hashes and address offsets across compute ELFs, and no IQ/OQ pair was globally free even when colors were lifetime-free. Free color is not admission; loader integration still needs drain/rebind/repaint/fence proof.
- The isolated WaferLLM Q+K RoPE harness passed simulator correctness with a 1,068-B / 267-u32 address-matched payload and pinned `.rope_data` / `.rope_abi`, but its section accounting was a negative economic result: resident 4,496 B, body-absent 3,852 B, dynamic receiver 6,096 B, removable ownership 644 B, admission floor 2,244 B, net receiver saving **-1,600 B**. `abi-pinned` means tractable relocation closure, not economic attractiveness.
- The function-container design checkpoint narrowed Phase 2 scope to two address-matched multi-entry page regions — whole Attention and whole FFN sharing one executable slot. Collectives, queue/task state, route repaint/fence, and completion stay receiver-resident behind command/continuation ABI. `vecmat`, RoPE, and softmax are now internal closure/profile problems inside the two pages, not independent loading targets.
- Phase 1 final-link joint ownership at WaferLLM `fd1c2da`, config `llama8B_4k_1_256`, measured complete receiver data-bank high-water deltas: Attention **5,088 B**, FFN **2,256 B**, joint **10,432 B**. The interaction `5,088 + 2,256 - 10,432 = -3,088 B` means shared closure released only when both boundaries are removed (2,768 B `.text`, 160 B `.data.lo`, 46 B `.data`, 112 B `.bss`, 2 B alignment), not negative savings or a quantity assignable to either page. `A_both` remains 15,296 B, so this is grade-A removable-ownership evidence, not dynamic receiver net saving.
- MeshRT audit scope was corrected: the relevant unit is Attention and FFN computation inside each prefill/decode phase (4 paper models × 2 phases × 2 regions = 16 source candidates), not whole scheduler state machines. All 16 source regions are currently `unsupported-current-loader` for direct injection because they include calls/`@map`, control flow, collective/fabric DSDs, queues/routes/tasks/callback state, or scheduler continuations. This does not reject paging; it points to fissioned, address-matched compute regions with resident thunks. Local SDK cannot relink MeshRT because the Singularity/FUSE/setuid toolchain wrapper is unavailable.
- M1 for Phase 1 Step 3 now has a versioned bounded-scalar CSL page ABI, JSON schema/manifest, deterministic ID generator, declarative resident-symbol seed, and one-slot contract. IDs, `SLOT_ADDR`, DSD/DSR profiles, loader, dispatcher, and runtime are deliberately unimplemented for M2+. Cross-contract validator and compile-only fixture pass; CSL 2.10 requires qualified enum members such as `page_abi.PageId.none`. External Claude Code read-only M1 review is pending explicit approval to send private repository files.

Next gates: complete the user-approved M1 review, do not begin M2 until accepted, and if continuing pageability experiments measure baseline/body-absent/dynamic receiver images plus phase load/use timing before any SRAM/performance claim.

## Updates — 2026-08-17

Drained four 2026-08-15..16 WaferLLM function-container captures into this topic:

- M2 established the compile-only yield/control contract for Decode Attention A0--A7 and FFN F0--F3b. Each page-local compute entry writes a bounded yield record and returns; collectives, route repaint, tasks, queues, loader, and `decode_entry` remain resident/absent from the page bodies. The key continuation split is `PageControlBlock.profile_id` for the current entry profile vs `Continuation.required_profile_id` for the next profile resident control must bind. Terminal A7/F3b request `RECONFIG_Y -> MARK_DONE`; only resident control may later mark `DONE`/`EVICTABLE`. SDK 2.10 compile-only yield fixture passed with ELF SHA-256 `9e2c018afb824bb86c36c9dc6b6c04b090c2600beab09879eed71f2bf6c5fe3f`; this does not validate compute semantics, page link closure, transfer, runtime, or device execution.
- M3 produced a source-hash-pinned declarative ownership and re-entry contract with 24 uniquely owned components and 13 entry profiles. Source-shared compute helpers (`vecmat_computation`, `gemv_static_step`, `fmulh_norm_func`, `fast_exp`) are private-linked into each page that uses them, not placed in a resident common compute library. Yield invalidates mutable DSD/DSR state, and entry profiles explicitly rebind or assign descriptors instead of relying on prior entry contents. U01--U03 remain final-link gates: compiler math/division lowering, `@map`/loop/branch lowering, and global/DSD address plus DSR-kind realization. M3 evidence SHA-256 is `e2e25b1531ce74b95986812bf02af32dc525542459f9601484b698b2e30faae4`.
- M3.5 superseded the first asymmetric accounting (`188 - 1,120 = -932 B`) with a symmetric four-counterpart Grade-E probe built from frozen SDK-2.10 `A_both`. The authoritative actual-sized minimal-probe delta is `SRAM(D_P)-SRAM(D_R)=+188 B`, favoring resident-side vecmat for that probe only. ABI is fixed at `0x3e00/10 B`, pages at `0x4100`; P/R entry offsets are 196/0 B; resident vecmat is `0x3f00/188 B`, callback `0x3fc0/8 B`. The host now accepts only build-generated paired bundles and checks payload SHA-256 plus receiver `out.json` values for P, slot words/address, and entry offset before loading all 256x256 PEs.
- Manual conflict recorded: the M3.5 codex capture says Claude attempts produced no verdict and must not be cited as PASS, while a later Claude capture points to a completed read-only PASS review on staging artifact `.m35_symmetric_refactor` (session `72054b9f`). Maintenance did not decide whether that PASS applies byte-identically to the WaferLLM `m35/` tree; see `tracking/conflicts.md`.

Next gates: start M4 only after user acceptance; generate P/private and R/resident-direct full Attention/FFN candidates from one production-derived, hash-guarded generator; keep communication on the approved M2 command/yield path; and leave vecmat placement for M5 using complete full-page `max(attention, ffn)` slots and complete receiver images rather than the M3.5 minimal-probe result.

## Updates — 2026-08-19

Drained ten 2026-08-16..18 WaferLLM function-container / division-closure captures into this topic:

- M4 generated four deterministic source-link regions for P/R Attention and FFN. It corrected M3 ownership/profile details (A2 score GEMV, A3 score scale, fresh DSD requirements, and U04 frozen-source conflict) and passed SDK-2.10 structural compile plus strict source-transform validation. Evidence remains source-transform/structural compile-only; byte counts beside generated files are source-text bytes, not final payload/SRAM.
- M5 initially stopped at `REVISE`: provisional P links at `.m4_page=0x9000` succeeded, but page-independent receiver-retention sections differed between Attention and FFN, falsifying the section-anchor/export/self-assign/mutable-gate retention tricks as a production receiver ABI. Hidden slot-external `__divhf3` and absent WSE-aware disassembly also blocked closure, so no final slot size, receiver SRAM saving, execution correctness, or Phase-2 admission can be inferred from those provisional links.
- M5R-0/1/2 replaced whole-section byte identity with a per-symbol receiver-union ABI: the receiver owns 33 fixed objects, and each page must prove address equality only for the symbols it consumes. A2 RoPE + score GEMV and F1 RMSNorm + up/gate SDK-2.10 probes compiled with nonempty fixed `.probe` sections, while the generated P/R source keeps DSDs, `Kt`/`Nt`, sum/max and temporary values entry-local. Practical gate: require a live RPC/runtime root, nonzero fixed section/symbols, fresh driver/input/artifact hashes, and expected distinct ELF hashes so a dead-stripped compile cannot pass.
- M5R-3 built the real receiver arena and final-linked P/R Attention+FFN pages into one common slot, but initially stopped at `REVISE_EXTERNAL_CODE_ESCAPE`: 182 page-specialization records still targeted slot-external `__divhf3`, and no WSE-aware disassembly was available. Those historical ELFs remain failure evidence and must not be reinterpreted as PASS.
- DIV-1 isolated the division blocker: constant RMSNorm `cur/4096` does not lower to `__divhf3`, while dynamic RMSNorm inverse, softmax reciprocal, and SiLU division do. SDK `math.inv*` / `math.invsqrt*` exact Route-A shapes remove the named `__divhf3` target in compile/link probes, but this changes the arithmetic lowering path and still needs numerical/special-value comparison.
- DIV-2 built Route B: page-private SDK-derived reciprocal/invsqrt helpers copied from SDK 2.10 sources, with no `<math>` import and no CSL `/`. Named page helpers are 148 B (`invsqrt`) and 184 B (`inv`), eliminate named `__divhf3`, and are retained as the explicit-ownership fail-closed fallback.
- DIV-3/C1 is permanently rejected. The compiler-local `__divhf3` helper matched at one address/hash only by linker coincidence; placement controls were ineffective, and adding an unrelated ordinary `.text` root moved the helper and changed its machine-code hash. It is not an enforceable resident ABI.
- DIV-3/C2 proved the same owned helper bodies can be fixed resident receiver targets, but DIV-4 rejected C2 for the current two-page container: it saves 256 B of aligned slot but adds 424/440 B permanent receiver floor, so complete receiver SRAM is worse than Route B by 168/184 B.
- DIV-4 production-shaped comparison relinked Route A/B/C2 across P/R × Attention/FFN and matched receivers. Route A is the provisional/default static implementation policy because it is simplest and has the same aligned slot and complete receiver allocation as Route B; Route B remains the fail-closed fallback if Route-A lowering/hash/target evidence drifts, WSE-aware closure fails, or numerical comparison fails. C1 and C2 are rejected.
- Step 3 pre-review checkpoint: active choice is Route A + vecmat policy P. P has complete allocated receiver SRAM 20,524 B vs R 20,644 B under both Route A and B; R saves 256 B of slot but adds 376 B permanent receiver floor and has no runtime performance evidence. U04 odd-RoPE source is repaired in generated pages, receiver/slot non-overlap and R five-word ABI call-site checks pass, and WSE-aware AM disassembly now covers all 364 final page ELFs with direct calls/branches/backedges inside `.m4_page` except the approved R vecmat indirect target at `0x7a08`. Formal Step 3 is `PENDING_INDEPENDENT_REVIEW`, not runtime/numerical/device correctness.

Next gate: fresh independent review of the materialized Step-3 pre-review package. If it passes, produce M6 and stop Phase 1 Step 3. Do not claim loader/transfer/invoke correctness, numerical equivalence, simulator/device correctness, latency, or dynamic net savings from the static evidence.

## Updates — 2026-08-21

Drained nine 2026-08-18..20 WaferLLM function-container / static-proxy captures into this topic:

- Phase-1 Step 3 is now canonically closed at PASS / Grade E. Route A plus private-link vecmat Policy P remains the capacity-active policy; Route B/P is the deterministic division fallback; resident vecmat Policy R remains an unmeasured performance alternative and costs 120 B more complete receiver SRAM at bsz=1. The M6 aggregate is authoritative over older immutable pre-machine and pre-review envelopes, which correctly retain REVISE/PENDING dispositions.
- Step 4 D0--D3 is canonically closed at Grade E for bsz=1: D0=20,060 B, D1=20,426 B, D2=20,700 B, D3=29,470 B. D1 is the direct-to-slot loader floor (366 B over D0) with no payload-sized shadow buffer; D2 adds the scalar page ABI, fixed root invoke seam, and two-record command arena (274 B over D1); D3 adds resident command/continuation runtime and terminal quiescence seam (8,770 B over D2). Evidence remains static final-link and machine-control-flow only.
- bsz=2 cannot reuse bsz=1 page roots, continuation offsets, slot capacity, or loader/invoke placement. Its Route-A/P slot is 5,120 B at `[0x1a00,0x2e00)`, loader at `0x2e00`, invoke at `0x2f00`, and pre-profile capacity is already negative: B=27,180 B, D3d=30,998 B, so `B-D3d=-3,818 B` before Step-5 profile ownership.
- Step 5 profile ownership is identical at bsz=1 and bsz=2 under Route-A/P: Attention profile delta 884 B, FFN profile delta 720 B, controlled union delta 1,200 B, interaction 404 B. Complete receivers are 29,470→30,670 B at bsz=1 and 30,998→32,198 B at bsz=2. Receiver compute DSD/Kt/Nt/pointer/scalar ownership is 0 B; unused page DSR declarations and DSR incremental SRAM are 0 B, though kind/id reuse remains a serialized-lifetime protocol constraint.
- Step 6 static-proxy economics fail capacity under the same final-linked occupied-union metric: bsz=1 B=25,716 B vs `D_full_static_proxy`=30,670 B (`B-proxy=-4,954 B`); bsz=2 B=27,180 B vs 32,198 B (`B-proxy=-5,018 B`). Recovering to zero needs 5,018 B in the worst batch; reaching the evaluated +256 B alignment margin needs 5,274 B.
- The Step 6 evidence verdict is `PASS_STEP6_STATIC_PROXY_EVIDENCE / Grade E`, but the design gate remains `REVISE_STEP6_DFULL_UNRESOLVED`: authoritative page-id/epoch/payload latch, all-receiver completion/global quiescence, holder drain/fence, and final production-vs-audit RPC ownership are not frozen. Do not generalize the negative proxy into a universal design NO-GO.
- D3 materializer compression probe: descriptor-table generic copy loop is rejected (+920 B diagnostic and forbidden slot-external `memcpy` closure). A two-word header-guard sparse variant saves 60 B only if a stronger arena-freshness invariant becomes authoritative; it is not selected. Keep official D3d for the frozen baseline.

Next gate: stop before Step 7 and Phase 2. The agreed next discussion is D3 SRAM optimization against the measured 5,018-B zero / 5,274-B +256-margin target. Exact Step 6 can close only after production seams are frozen and final-linked `D_full_admitted` is measured.

## Updates — 2026-08-22

Drained `memory/inbox/2026-08-21-waferllm-step6-dfull-admitted-policy-p.md` into this topic.

- Step 6 now has the exact admitted `D_full_admitted` Policy-P receiver/holder/filler image family for SDK 2.10, P=256, Route A, bsz=1/2. Evidence remains static Grade E: no page transfer or execution has been proven on simfab or CS-3.
- Complete receiver SRAM uses the occupied union of all SHF_ALLOC ranges below `0xc000`, including NOBITS and the fixed 1-KiB task table. The admitted receiver is 31,560 B at bsz=1 and 33,088 B at bsz=2, exactly 890 B larger than the Step-5 proxy in both batches.
- Capacity verdict is `COMPLETE_STEP6_NO_GO_CAPACITY`: bsz=1 has `B-D_full=-5,844 B` and bsz=2 has `B-D_full=-5,908 B`; recovery to the evaluated +256-B margin needs 6,100 B / 6,164 B respectively. The controlled 890-B increase decomposes as topology normalization -8 B, authoritative load/latch +554 B, phase loop +364 B, release plus real holder protocol +100 B, and production-root pruning -120 B.
- Holder/filler overhead is whole-wafer, not part of per-receiver `B-D_full`: holder SRAM is 13,530 B at bsz=1 and 15,066 B at bsz=2; fillers use 4,440 B. The holder owns two full zero-padded catalog slots, OQ2, asynchronous `@mov32` sender, queue-flush task/empty handler, and a holder identity latch.
- Frozen host-attested load contract: one blocking host launch of layout-wide `d_full_load_page` reaches receivers, holder, and fillers; the holder streams the selected full slot and unblocks only after OQ2 drain; receivers perform fixed-count IQ2-to-slot `@mov32`, publish READY last, then unblock. Treat the blocking host return as a contract to validate later, not a runtime proof.
- The holder catalog must be host-provisioned, not linker-zero initialized: extract `.m4_page` from frozen Attention/FFN ELFs, check raw/padded hashes from `page_catalog.json`, concatenate two full slots, reject all-zero catalogs, write only holder `(P,0)`, and D2H-readback exactly before the first load RPC. Check-only evidence records 8,704 B / 2,176 u32 words at bsz=1 and 10,240 B / 2,560 u32 words at bsz=2.
- Review fixes now included: explicit holder catalog provisioning; validation against freshly regenerated machine-audit inventory; fail-closed tombstones before validation prerequisites; and hard rejection of any SHF_ALLOC section crossing `0xc000`. Six host-only tests pass. Keep technical static validation PASS separate from independent review: the expanded external recheck was blocked pending explicit approval to transmit the larger private evidence set.

Next decision: do not enter Phase 2 from this result. Fair comparison requires measuring Policy R with the same exact admitted `D_full` method. Use 5,908 B as the worst-batch break-even gap, or 6,164 B for the +256-B admission margin; D3 remains the dominant common-floor optimization candidate. Correct transferred-page execution is a later runtime-validation gate.

## Updates — 2026-08-23

Drained `memory/inbox/2026-08-22-shared-slot-validation-after-first-load.md` into this topic.

- Shared-slot Route-A/Policy-P runtime validation reached the first dynamic-load stop point only: a coherent P=8 simulator build passed, the original baseline completed on deterministic input, receiver-arena H2D plus `init_task` completed, holder catalog H2D/D2H readback succeeded, and `d_full_load_page(page=1, epoch=1)` returned.
- The run then blocked on the immediate receiver-state D2H readback after page load. No admitted-run RPC or release RPC began, so this does **not** prove slot bytes, page-function invocation, transferred-page correctness, latency, or `B_original == D_dynamic`.
- Treat the post-load receiver-state D2H block as the current runtime-validation gate. Do not continue Phase 2 claims until a separately authorized investigation explains why receiver-state readback cannot complete after the first dynamic load.

Pointers: `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/results/simulator_failure.json`; `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/runs/p8-v4/dynamic_host_trace.jsonl`.

## Updates — 2026-08-24

- The canonical real-size shared-slot validation is now code-snapshotted in WaferLLM branch `attn-ffn-pageability`, commit `b9f5d43a581f70d905e16bcf1959dc8979101194` (parent `fd1c2daae37cd68706c03fc8009887ecee9900f8`). Its committed `attention-ffn-phase1` and `attention-ffn-runtime-validation` subtree hashes are `10e055b0282f3fe03063231f3d5905df218ab2b1` and `20d128baabf9c2ba4f68ad06463a361c93e827c2`.
- The bound result is P=256 `p256-map-e2e-20260824-v5`: validation-only `B_U04_corrected` versus `D_dynamic`, 19/19 checkpoints and Final Z raw-f16 bit-exact on CS-3, with final audit `PASS_P256_MAP_MAX_SHARED_SLOT_E2E`. Dynamic receiver SRAM remains larger than the corrected baseline; no latency/throughput claim exists.
- At the recorded observation time the branch was local-only: no upstream and no matching head on `origin`. Post-commit untracked roots are outside the snapshot. Full commit boundary, recovery commands, and working-tree exclusions are recorded in `memory/inbox/2026-08-24-waferllm-attn-ffn-code-snapshot.md` and the ContextBase P=256 session log.

## Provenance

Drained from two dated captures (2026-08-06 maintain pass):
- `memory/inbox/2026-08-04-meshjit-branch-relocation.md` (relocation correctness, silicon-validated).
- `memory/inbox/2026-08-04-meshjit-line-multicast-cost.md` (multicast cost + real function profile).

Repos/evidence: `~/MeshJIT/controlflow-experiment/` (RESULTS.md, CS-3 `~/meshjit-controlflow/`),
`~/MeshJIT/broadcast-timing/results/` (RESULTS.md),
`~/MeshJIT/function-use-profile/`,
`/home/lexu/we-sram-profile/prefill_text_meshjit_candidates.md`,
`/home/lexu/we-sram-profile/prefill_text_funcs.txt`,
`/home/lexu/we-sram-profile/models/qwen3_1p7b-prefill/out_device_8k_c512_whole_tile_flash/executables/prefill-11.elf`.
ContextBase: https://context.ed-aisys.com/doc/2026-08-04-result-meshjit-physical-multicast-cost-real-c512-use-time-7LlgIfgzCe

## Related

- [[pe-sram-memory-breakdown]] (the `.text` budget this relieves); skill
  `wse-runtime-remote-code-loading` (invariant #1 refined here).
