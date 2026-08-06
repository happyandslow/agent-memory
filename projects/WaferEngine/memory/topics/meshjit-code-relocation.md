---
summary: MeshJIT fabric code relocation to relieve the .text-dominated prefill PE — silicon-validated address-matched-slot rule (forward branches relocate, backward loops are absolute), pipelined hardware router multicast cost model, and real c512 function sizes / exact-body use times that say fetch per-phase not per-leaf.
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
