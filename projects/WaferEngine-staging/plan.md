# WaferEngine-staging Plan

Human-maintained roadmap and durable progress narrative. This is the canonical home for project goals, milestones, decisions, and next actions. Generated/current status belongs in `tracking/status.md`.

## Goals

- Understand qwen3-1.7B end-to-end serving variants on WSE-3: fused `e2e`, host-bridged `e2e-pdSeparate`, and their relationship to newer standalone decode/prefill kernels.
- Quantify KV-cache preserve-vs-evict/offload tradeoffs for WSE-3, including in-place, in-bank, idle-PE, host-DRAM, and recompute tiers.
- Measure effective prefill→decode KV handoff bandwidth honestly, counting both on-fabric movement and on-PE gather/transpose/re-layout compute.

## Milestones

- [x] e2e fused first CS-3 device PASS on mock weights; static geometry/floorplan recorded for prefill→decode transfer.
- [x] pdSeparate max-context and large-context prefill SRAM failure documented.
- [x] KV preserve/evict tier ladder captured, including Le's T0.5 in-bank reuse addition and force-decode-in-place direction.
- [x] Standalone-vs-integrated kernel parity gap documented.
- [x] Instrument prefill→decode transfer segments A/B/C with TSC and compute first effective-GB/s number.
- [ ] If exact silicon per-state KV-transfer breakdown is needed, slim/fix the widened per-step profiler; otherwise treat it as parked because profiler-off fullT proves the transfer path itself is healthy.
- [x] Resolve pre-S6 KV-management abstraction question: shared compute exists, but retain cannot be abstracted into integrated kernels until S4/S5 lifecycle port.
- [x] Bring up prefill warm-start (`START_CHUNKS` prefix reuse): byte-identical PASS in sim and on real WSE-3 after fixing three independent defects.
- [x] Re-measure the prefill prefix-reuse saving on real-dim device configs; real-scale WSE-3 results now show strongly sub-linear savings (25% reuse → 7.7%, 50% → 22.8%, 75% → 45.2%).
- [x] Scope forced-token decode, T0.5 in-bank reuse, and T1 idle-PE offload prototypes.
- [x] Implement S6b forced-token decode in staged form: S0 inert `F=1`, S1 correctness with host-fed F embeddings, S2 tail-skip/token-drain guard; Step 2 is sim-verified at F=4 and the F-sweep shows the toy-scale speedup is mostly skip-compute, not pipeline fill.
- [ ] Decide whether fused e2e should carry prefill's sampled token into decode (host hop or new on-chip `pf_ht_tail` → HT_head wire) before making end-to-end accuracy claims.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-07-05 | Treat integrated e2e/pdSeparate as older snapshots, not the serving source of truth. | Standalone kernels carry newer multi-round, runtime-varlen, chunked-prefill, EOS, softmax, and oracle fixes that integrated copies lack. | `memory/topics/standalone-vs-integrated-kernel-parity.md` |
| 2026-07-05 | Frame KV preserve-vs-evict as a tier ladder, not a binary on-chip/off-chip choice. | T0/T0.5/T1/T2/T3 have different reuse costs, capacity, and kernel support requirements. | `memory/topics/kv-cache-policy-tradeoffs.md` |
| 2026-07-06 | Count both transfer and transform compute in prefill→decode bandwidth. | The handoff is not a flat memcpy; gather, transpose, re-layout, seam shift, and decode cache writes all contribute to wall time. | `memory/topics/prefill-decode-transfer-bandwidth.md` |
| 2026-07-06 | Use WSE-3 TSC at 1.1 GHz for the e2e segment timing design. | The SDK bandwidth-test's 0.85 GHz constant is wrong for WaferEngine; the timing skill was updated with the project-specific reconciliation. | `memory/topics/prefill-decode-transfer-bandwidth.md` |
| 2026-07-19 | Keep every per-column x-chain payload EVEN (`metainfo_len = 4` = 3 real + 1 pad). | An odd-extent async `fabin → fabout` `@mov16` never fires its completion callback on WSE-3 and silently deadlocks the block; an isolated 8-PE reproducer ruled out queue depth. | `memory/topics/s6a-prefill-warm-start.md` |
| 2026-07-19 | Treat the mock-scale prefill reuse numbers as mechanism-only; no reuse-value claim until real-dim configs are re-measured. | Saving tracks (k/n)² rather than k/n, so prefix reuse has strong diminishing returns — but the grid ran at dim=64/vocab=64, and the L=2048 rows were invalidated by a host cache-key bug. | `memory/topics/s6a-prefill-warm-start.md` |
| 2026-07-20 | Model prefix-reuse value with position weighting, not linear hit rate. | Real-scale WSE-3 results show 50% prefix reuse saves only 22.8% latency and 75% saves 45.2%; reused prefix chunks are the cheapest part, while recomputed suffix chunks dominate. | `memory/topics/s6a-prefill-warm-start.md` |
| 2026-07-20 | Decode retain's benefit is skipping already-executed decode steps, not making each equal-work step cheaper. | Equal-work decode comparisons differ by only ~0.02% fixed overhead; the correct end-state comparison saves 34.6% total decode work by avoiding redoing discarded steps. | `memory/topics/s6a-prefill-warm-start.md` |
| 2026-08-04 | M1-S3 implementation-role contract: Codex stays planner+reviewer and does NOT implement production changes itself; it dispatches the approved bounded task to Claude Code (`claude-fable-5`, fallback `claude-opus-4-8`), which implements + runs the agreed gates; Codex then independently reviews evidence+diff and iterates to gate-pass. | Every step boundary is a hard approval gate; a phrase like "do S3.1 first" selects the next planned step, it does not replace the role contract. The `launch.py` modularisation was scoped as a separate pure-move task with a bit-identical gate and has since been completed + merged before S3.3 (history, not open). | `memory/inbox/2026-08-04-m1-s3-planner-implementation-review-contract.md` (hermes) |
| 2026-08-11 | Report the M1-S3.7 benchmark in raw TSC cycles plus throughput converted at 0.85 GHz. | This matches the decode baseline and the collaborator-deck convention requested for this experiment. It does not supersede the older 1.1-GHz e2e decision; the global clock reconciliation remains open and raw cycles stay authoritative. | `memory/topics/m1-s37-prefix-reuse-device-gates.md` |

## Next actions

- [ ] **Audit the Lane B equation and A/B-crossing slides** for the delta-reload vs full-KV-reload
      definition mismatch: full-KV Lane B is `B(L)=I(L)` with no post-ingress forced delta (adding
      one double-counts); the next free-decode token is a common tail, charged to all lanes or none.
      Targets: `meetings/2026-08-02.pptx` slide 12, `meetings/2026-08-02-src/make_figures.py`. See
      `memory/topics/m2-experiment-register.md` change log 2026-08-03.
- [ ] **Add the shared host/config `1 <= F = prompt_len - start <= decode_len` guard** before
      enabling automatic M1-S3 cache-hit scheduling — `F=0` (seedless exact-history hit) deadlocks
      the step-0 HT_head/HT_tail dependency; M1 runs an exact reuse at `F=1`, not `F=0`. See
      `memory/topics/force-decode-startup-depends-on-prefix.md` § Updates 2026-08-04.
- [ ] **For M1-S4, define actual-length/EOS commit semantics for automatic replacement early-stop.**
      The temporary S3.5 rule fails closed after draining trailing TSC because host slot length may have
      advanced to planned `RoundPlan.end` while the device produced fewer resident KV positions. See
      `memory/topics/automatic-replacement-early-stop-fails-closed.md`.
- [ ] **For every M1 implementation step after S3.7, define and run a real-device gate before closure.**
      Host tests, mocks, compilation, and simulator runs are diagnostic layers only; if the device gate
      is unavailable, keep the step incomplete/blocked. See `memory/topics/m1-s37-prefix-reuse-device-gates.md`.
- [ ] **For M1-S5, separate `bsz` from `SLOT_COUNT` and include `ht_tail` batch scratch in the SRAM model.**
      Full-model `bsz=SLOT_COUNT=3,4` failed before execution from shared PE data-SRAM exhaustion, while
      `1,2` compile/run. Reducing `MAX_SEQ_LEN` alone cannot fix this boundary.
- [ ] **If D9 is ever relaxed, design per-PE resume payloads before arbitrary truncate-then-branch.**
      Current host-seeded and decode-appended KV share one strided placement, so one scalar is exact for
      P-aligned boundaries only; non-P-multiple resumes need per-row valid lengths. See
      `memory/topics/decode-kv-strided-placement-and-resume-granularity.md`.
- [x] **DONE — standalone `launch.py` modularisation** (separate pure-move task, bit-identical gate)
      was discussed, approved, implemented, committed, and merged **before S3.3**; it is history, not
      an open action. The per-step S3 role/gate sequence it established still stands for later steps:
      agree plan → Claude Code implement/test → Codex review → iterate → Codex accept.
- [x] **DONE 2026-07-21** — the long-sequence follow-up is complete: k48 at L=16,384 (49.75% saving) and the decode L=4096 pair (`d2_noreuse` 1,120,316,570 vs `d2_reuse` 567,975,120 → −49.3%). With k48 in hand the earlier "two lengths lie on the same curve" claim is narrowed: fraction dominates, but a second-order length term appears at high reuse and favours the *longer* prompt (75%: L=8192 45.2% vs L=16384 49.8%). Decode length axis now has two points (−34.6% at 1024, −49.3% at 4096, both set by the redo step-ratio, not length). Chart + docs updated in agent-memory + ContextBase.
- [x] **S6a-prefill DONE + verified + MERGED.** Mechanism verified byte-identical in sim AND on real WSE-3 (2026-07-19→07-21) with real-scale perf measured; the three fixes (metainfo even-padding, `ht_head` chunk-slot indexing, two host `start_chunk` assumptions) were **committed as `e0a19fc` and merged into the feature branch `lexu/staging/kv-feature` via PR #1 (`0db3fc2`) on 2026-07-21** (git-verified: `e0a19fc` touches `prefill.csl`/`ht_head.csl`/`launch.py`/`kv_store.py`/`comm_pe.csl`; current `s6b-force-decode` tree byte-identical). **So S6a — decode + prefill — is complete and landed on `kv-feature`.** Branch convention: milestone branches converge onto `lexu/staging/kv-feature`. NB (self-correction): a prior reconciliation this day wrongly called the prefill code "uncommitted / pending review" — I asserted that before checking git; the branch topology shows it was already committed + merged. The stale line it was correcting (in-repo docs' "S6a-prefill IN PROGRESS / handed to a new session", left over from the S6b session) is now fixed to "merged into kv-feature."
- [ ] **Assert on unknown `model_config/*.json` keys.** Still not implemented, and it is the one constraint from the M1-S1 review that was left as prose rather than turned into a guard — which is exactly why it is the one still open. `cfg.get(...)` with a default silently turns a misspelt key into the default: `FORCED_DECODE_LEN` vs `FORCED_DECODE_LENS` meant one config's `[1,4,4,4]` **never once took effect**, and `ACTIVE_SLOT` vs `ACTIVE_SLOTS` turned a red control into a copy of the green one. Validate each new key too: length == `bsz`, value < `SLOT_COUNT`, **no duplicates** (a duplicate = two lanes on one slot = silent cross-contamination).
- [ ] **M1-S2's shape flipped** — it is now mostly *host* work: a per-slot `valid_len` table in `kv_store.py` plus an explicit per-round `retained_len`, retiring the `-1` sentinel. The device barely changes. This is the opposite of the "device loops over slots" design the milestone doc still implies.
- [ ] **Fix two now-stale contract lines in `milestones/M1-intra-pe-reuse.md`** before someone re-derives the wrong answer from them: § S0.2's *"slot empty ⇔ `iter_num_bank[layer][slot] == 0`"* (occupancy is a host judgement under D4) and the grep checklist row naming S1 as the owner of adding that dimension ("not needed, superseded").
- [ ] **Before any pr14 rebase:** enumerate PR #14's renamed symbols and grep our call sites — the dangling-import class does **not** show up as a conflict — and re-run the trial merge at the then-current tip, since the 7-file/18-hunk counts expire as the PR moves.
- [ ] **Re-derive `R*` once M2 produces a real `Δ(L_new)`.** The recomputed `R* ≈ 3.4` uses the stale `Δ = 276 µs`; the 57 ms prefill floor at short prompts already says `Δ` is a function of `L_new`, not a constant.
- [ ] **Settle the TSC clock (0.85 vs 1.1 GHz) for Fig E-1 (and all decode-side TSC).** The 2026-07-06 decision says WaferEngine timing is 1.1 GHz, but the in-repo decode TSC uses 0.85 GHz and reproduces the pr14 654 µs/tok baseline. Fig E-1's GB/s (0.80/band) is quoted at 0.85 GHz; raw `span_cycles` are recorded so it is recomputable. Resolve which clock the decode TSC counter actually runs at (a controlled measurement against a known wall-clock interval), then restate Fig E-1 + the decode-µs numbers.
- [ ] **E13 Gate 3 (decoded-KV round trip):** the remaining E13 step — reload the egressed *decoded* KV and continue decode as an identity round trip. Needs a TOP_K=1 greedy build (determinism) + the round-trip host-loop restructure (receive-egress → reassemble → send-as-next-ingress) + the round-END egress trigger (`EGRESS_AT_STEP != 0`). Optional first: rerun Fig E-1 L_p 2048/4096 (infra casualties) to fill the two mid-curve points.
- [ ] Strengthen the warm-start gate so it fails when reuse silently never engages — byte-identical KV alone also passes a cold run.
- [ ] Decide whether to lift decode's `MAX_SEQ_LEN ≤ 1016` wall; it needs a KV access/layout change that keeps the traversal stride inside the DSD's i8 `.stride` field, not a type widening.
- [ ] Instrument `qwen3_1p7b-e2e` segment timings: t0 `start_kv_transfer`, t1 prefill states 0–3 done, t2 north-shift done, t3 decode `kv_flush_then_init`; validate in sim then on a device-sized config.
- [ ] Fill byte totals for the 2×2 configs from run printouts (`bsz`, `kv_dim_per_pe`, `seq_len_per_pe`, `max_layers_per_block`) so GB/s denominators are explicit.
- [ ] Compare fused on-chip seam path against pdSeparate host-DRAM bridge under the same both-segments-counted metric.
- [ ] Quantify T1 idle-PE offload and T0.5 in-bank reuse; for S6b force-decode, repeat the F-sweep on a block-compute-dominated/real-scale config before making a pipeline-overlap claim.
- [ ] Discuss the no-keyed-routing/static-orchestration framing as a design constraint for KV reuse/tiering; check whether any retained-store or bridge mechanism implicitly assumes content routing.
- [ ] Unblock pdSeparate long-context prefill by shrinking/removing the quadratic score buffer; defer real HF weights/tokenizer/oracle unless Le reprioritizes them.
- [ ] Redraw/annotate `assets/prefill-decode-transfer/e2e-topology-full.svg`: x131 is a decode west strip, and x644 (the real east strip in 2×2) is currently absent.
- [ ] Fix e2e source/documentation hygiene found in the 2026-07-09 read: stale `route_calc.csl:5` axis comment, prefill vocab-padding asymmetry, K-pipe alias invariant check, and `csl_color_audit` raw `@set_config` parsing.

## Narrative progress log

### 2026-08-12 — maintain pass drained three process/tooling captures

- **Encapsulation boundary review:** created
  `memory/topics/encapsulation-refactor-source-boundary-tests.md`. The M1 inner-PE-reuse
  `RoundPlanner` cleanup only actually closed ownership after test-only mutable escape hatches were
  removed and a source-boundary regression test asserted the immutable result surface.
- **Source-comment cleanup gate:** created `memory/topics/source-comment-lossless-compression.md`.
  Comment/docstring-only cleanup should preserve non-obvious contracts and prove executable
  equivalence with docstring-stripped AST comparison, `git diff --check`, and the normal regression
  suite; the exercised branch removed 1,006 net lines across 23 Python files with identical ASTs and
  414 host tests passing.
- **Excalidraw diagram workflow:** marked the capture drained. The durable procedural result lives in
  the shared `excalidraw-diagrams` skill: `.excalidraw` is the source of truth for non-data figures,
  SVG/PNG are derived exports, and agent/human collaboration reloads the source before minimal
  patches.

### 2026-08-11 — S3.7 benchmark semantics and collaborator-deck corrections

- Experiment A now records every setting as `P/R/F/G`: miss `1025/0/1025/255`; partial keeps `P=1025,G=255` while `R` grows and `F` shrinks; exact uses `P=R+1,F=1,G=255`. Its collaborator metric is generated-output tok/s at 0.85 GHz.
- Experiment B now records the actual locality generator: W2/W3/W5 are round-robin 2/3/5-prefix working sets, so reuse distance is `W-1` and LRU hits iff that distance is below `SLOT_COUNT`. With `G=0`, its metric is logical prompt tok/s, not generated tok/s.
- The current weekly deck replaces a misleading theoretical host-reload ceiling plot with actual full-CS-3 E10 resume-only measurements: recompute and reload cross near 700 tokens for that specific slice. This is not a universal policy boundary; full-target reload also depends on retained suffix, target length, eviction cost, and future resume probability.
- M3 discussion is now placement-agnostic at the controller API but static/precompiled at realization time. A lower-edge storage row per PE block is a candidate for E1, not a selected topology; it must expose measured capacity and park/reload cost profiles and pass color/queue audit.

### 2026-08-11 — maintain pass drained four M1/S3.7 captures

- **M1/S3.7 device-gate policy and evidence:** created
  `memory/topics/m1-s37-prefix-reuse-device-gates.md`. Starting with S3.7, each implementation
  step requires an explicit CS-3 gate before being marked complete; simulator/host tests cannot
  substitute for a device verdict. S3.7's tracked positive-prefix reuse case passed on real WSE-3
  (`P_BLOCK_SIZE=8`, `bsz=2`, `slot_count=2`, two 16-step rounds, `PREFIX-REUSE` with no host KV
  reload, ledger `OK`, `rc=0`).
- **Full-model S3.7 baselines:** the same topic now records CS-3 TSC reuse-length and locality
  sweeps at full Qwen3-1.7B geometry. Exact reuse gives about 1.76–1.82× at `bsz=1` and 1.72–1.75×
  at `bsz=2`; slot capacity helps only when it crosses the temporal-locality working-set threshold.
  Coupled `bsz=SLOT_COUNT=3,4` fail before execution from `ht_tail` shared PE SRAM exhaustion, so
  S5 must separate batch and slot count and model batch scratch explicitly.
- **Reusable instrumentation rule:** created
  `memory/topics/explicit-default-off-debug-instrumentation.md`. Retained debug/verifier code must
  be explicit, default-off, fail-closed, and report `SKIPPED` rather than implying an omitted check
  passed; device entry points should reject simulator-only flags before layout/runtime setup.

### 2026-08-10 — maintain pass drained four 2026-08-06→08 captures

- **E13/S3b decode egress:** appended the runtime-extent fabric `@mov` correction to
  `memory/topics/s3b-decode-kv-egress-options.md` and `memory/project.md`: runtime `@set_dsd_length`
  + fabric `@mov` is supported; the real wall is extent `< 0x7fff`; still gate compile/place because
  runtime-narrow fabout placement has failed before.
- **M1 decode resume/layout:** created `memory/topics/decode-kv-strided-placement-and-resume-granularity.md`:
  host-seeded KV and decode-appended KV use the same strided token→row/col placement; a single scalar
  resume is exact only at P-aligned/D9 boundaries, and arbitrary truncate-then-branch would need per-PE
  valid-length payloads.
- **M1 automatic replacement:** created `memory/topics/automatic-replacement-early-stop-fails-closed.md`:
  automatic early-stop fails closed until S4 defines actual-length/EOS commit semantics.
- **Git safety:** appended the `git stash` correction to `memory/topics/never-commit-without-explicit-user-request.md`:
  under a preserve-index / no-Git-mutation contract, `stash` is banned because it mutates and can collapse
  the staged-vs-unstaged boundary.

### 2026-08-06 — maintain pass drained the 9-item inbox backlog (2026-08-03 → 08-06)

- **Two new topics** (methodology/tooling lessons, both promotion candidates):
  `memory/topics/an-oracle-cannot-check-an-input-it-re-derives.md` (a device-vs-oracle gate that
  PASSes a provably-wrong run because both sides re-derived the same setup quantity — plus the
  vacuous-PASS sibling) and `memory/topics/codex-review-times-out-when-source-is-outside-the-root.md`
  (codex-review burns its full ~1800 s timeout with no output when claims reference source outside
  its `-C` root; inline the source + narrow scope).
- **Appended to existing topics:** `force-decode-startup-depends-on-prefix.md` ← the `F=0`
  seedless-hit deadlock (M1 keeps a mandatory `F=1` seed); `m2-s0-baseline-and-timer-provenance.md`
  ← measured `runtime.load()` = ~140–156 s/artifact and the load≠attach correction;
  `m2-experiment-register.md` change log ← the full-KV Lane B definition (`B(L)=I(L)`, no forced
  delta).
- **Into `memory/project.md` Known pitfalls:** the containerized-sim waiter must poll for the output
  artifact not a PID; and `./clean.sh` deletes git-ignored `CLAUDE.md`/`.superpowers/`
  irrecoverably.
- **Into Decisions + Next actions:** the M1-S3 planner/implementation/review role contract (Codex
  plans+reviews, Claude Code implements); Lane B slide audit; `F=1` guard. The `launch.py`
  modularisation from that contract is recorded as **completed history** (merged before S3.3), not
  an open action.
- **Cross-project drain:** `memory/inbox/2026-08-05-decode-one-layer-rectangular-layout-sram.md`
  (the one-layer `64 x 256` decode layout / HT-embedding SRAM wall) was folded into the
  `we-pr14-depth-layout` project (`memory/topics/decode-pipeline-depth-layout.md`), the durable home
  for the decode pipeline-depth experiment. All nine captures marked `Status: drained`.

### 2026-08-03
- **M2 · E13 (decode→host KV egress, the "eviction half" of lane B) — Step 1 COMPLETE + Fig E-1 DELIVERED, all on real WSE-3.** This closes register §1.3's `decode produces KV --X no path X-->` gap: a decode-side slot's KV can now be pulled back to host, byte-correctly.
  - **Gate 1 (shape) PASS** (02:31) + **Gate 2 (content) PASS** (06:02): the shift-based egress (block east-shift gather → `kv_egress_colmux` NORTH drain → 4-band D2H) runs on hardware AND the egressed KV is **bit-identical to the injected KV** (k_diff=0, v_diff=0, nonzero=14.68 M). Decode throughput unchanged (657 µs/tok == e9 baseline) ⇒ egress ON is non-perturbing. The device emit order == `_repack_kv_band`'s ingress order (layer-outer, per-layer K-all-px then V-all-px, px-inner) ⇒ reload is an identity round-trip; the correct host inverse is `repack_stream_to_banks` (NOT the px-outer `split_place`, which Gate 0 self-validated on a device-irrelevant order).
  - **Fig E-1 (decode-side D2H egress cost vs L_p, device TSC on the band-0 colmux head):** a **HOCKEY STICK** — `span ≈ 46 ms fixed floor + payload / 0.80 GB·s⁻¹·band`. Four clean L_p points (raw span_cycles preserved; L_p 2048/4096 were infra casualties):
    - 256/plen1/8 MiB → 39,270,494 cyc; 512/plen2/16 MiB → 39,336,033 cyc (payload DOUBLES, cycles FLAT ⇒ floor-dominated); 1024/plen4/32 MiB → 47,754,412 cyc; 8192/plen32/256 MiB → 287,114,397 cyc.
    - Marginal (linear region) ≈ **0.80–0.83 GB/s per band** — a striking symmetry with the S30 **H2D reload marginal 0.7966 GB/s per band** (decode-side D2H egress and H2D reload have ~the same per-band wire rate). Fixed floor ≈ **46 ms** ≈ S1's 46.146 ms span. `4×` (all bands) ≈ 3.2 GB/s is a **projection** (host drains bands sequentially; a real concurrent aggregate = M4). The ~46 ms floor + single-head serialization is an **as-built artifact** (one PE funnels the whole band).
  - ⚠️ **Clock caveat (ties to the 2026-07-06 decision):** GB/s above uses **0.85 GHz** (consistent with the in-repo decode TSC that reproduces the pr14 654 µs/tok baseline). The agent-memory decision says WaferEngine timing is **1.1 GHz** — if that holds here, divide µs by 1.1/0.85 (× 1.29 GB/s). **Raw `span_cycles` are recorded in `decode_device_verdict.json.egress_tsc`**, so the rate is recomputable once the TSC clock is settled. This 0.85-vs-1.1 GHz reconciliation is now a live open item for Fig E-1 too.
  - **Process/infra:** every code change went implement → Codex-iterate-to-APPROVE → gate (offline-validate before burning a ~55 min device cycle where possible); **nothing committed**. Built the **e9-launcher-polling** driver (background worker + short poll RPCs) to survive the EPCC ingress's ~502-every-15-min channel death — it gives live observability + early-stop AND is the only way a >15-min serve completes on this cluster tonight. Full detail: in-repo `models/qwen3_1p7b-e2e-pdSeparate/E13_SESSION_LOG.md`.
  - **Remaining E13:** Gate 3 (decoded-KV round trip) — needs a TOP_K=1 greedy build + the round-trip host loop restructure; NOT started. Optional: rerun L_p 2048/4096 to fill the two mid-curve points.

### 2026-07-29

- **Drained the 14-item backlog** (2026-07-26 → 07-29) into six topic notes plus
  `memory/project.md`. Two clusters: M1-S1 implementation/verification, and M2 kickoff +
  the git/branch discipline that came out of it.
- **The single most consequential correction: the host KV transport figure.** The
  long-quoted **"as-built ~15 MB/s"** was never measured — its denominator came from a
  `STATUS.md` prose phrase, and it described the wrong branch. It is now
  **1.426 GB/s aggregate / 0.357 GB/s per stream**, with the payload **derived from code**
  (exactly 33,554,432 B/request) and the time **measured** (23.525 ms, real WSE-3, n=2, pr14
  line). Struck through rather than deleted at all nine sites in
  `kv-cache-policy-tradeoffs.md` so it reads as dead if found quoted elsewhere. **This moves
  `R*` from ~0.035 ("always keep KV in place" — a degenerate answer that looked like a strong
  conclusion) to ≈3.4**, a real boundary that typical multi-turn chat sits on both sides of.
  It also shrinks the cross-chip-vs-fabric gap from ~300× to ~3–5×, which materially softens
  that section's original argument. ⚠️ The recomputed `R*` still uses the stale
  `Δ = 276 µs` — re-derive when M2 produces a real `Δ(L_new)`.
- **Decode cost is linear in context, not a constant:** `627.83 µs + 26.45 ns × ctx`,
  R² = 0.998, monotonic across all 8 requests of the M2-S0 run. So the 654.95 µs anchor is a
  mean over one workload's generation-length mix (≈1020 tokens of context). Any estimate that
  multiplies it by `L` understates long-context lanes.
- **Two design retractions, both Le's, both authoritative.** A mixed prefix-hit/prefix-miss
  batch does **not** need ragged support — round start = `min(L_match)` and the redundant
  recomputation is bit-identical to what it overwrites, so correctness falls out with no mask
  or guard; the earlier "S3 must use `bsz=1`" guidance is superseded. And per-slot KV length
  **stays on the host** — the device keeps per-layer scalar counters, and a per-slot table
  becomes mandatory only when the active set changes across rounds *and* you later return to
  a previously-used slot. Both corrections cancelled change-list items rather than adding
  them. Separately: the real blocker for ragged batching is **per-lane RoPE state**, not
  `iter_num`, so any O1 cost estimate derived from the `iter_num` analysis alone is too low.
- **PR #14 never demoted the `e2e` on-chip KV relay** — that claim is true of
  `e2e-pdSeparate` only, and looks like a model mix-up in the work repo's durable prose. The
  correction is **unconfirmed by Le** and moves an adopt-vs-port input in the convenient
  direction, so it is parked in `tracking/conflicts.md` rather than treated as settled.
- **Rebase cost measured** on a trial three-way merge: 7 files, 18 hunks, ~650 lines — and the
  M1-S1 slot seam produces **zero** conflicts. The expensive half is what merged *cleanly*: a
  renamed symbol surviving as a dangling import (code-verified) and a protocol split across
  two files that can merge half.
- **Six of the seven "promotion candidate" flags turned out to be one lesson** — *something
  that looks like evidence, isn't, and fails silently*. Consolidated into a single skill
  proposal in `tracking/conflicts.md` rather than seven entries.

### 2026-07-26

- Drained three 2026-07-25 M1/T0.5 inbox captures into `memory/topics/kv-cache-policy-tradeoffs.md`. Durable additions: cache capacity is slot count `S` while batch `M` is the active subset via `active_slot[m]`; M1 uses fixed contiguous slots behind K/V accessors rather than paging; and active lanes in one decode forward must remain equal-length because scalar `iter_num` is both effective length and packed score stride.
- Added a promotion follow-up for the reusable review heuristic: when adding a per-request dimension, explicitly find which invariants old lockstep uniformity was enforcing for free.

### 2026-07-25

- Drained `memory/inbox/2026-07-22-verify-branch-merge-state-before-asserting-commit-status.md` and `memory/inbox/2026-07-24-squash-merge-breaks-ancestor-check.md` into `memory/topics/git-branch-status-verification.md`: before writing branch/commit/merge status, verify live git state and feature content. Durable prose can be stale, and squash merges make original-tip `merge-base --is-ancestor` checks false-negative even when content is present.
- Drained `memory/inbox/2026-07-24-meshagent-sync-outline-patch-list-drop.md` as a manual skill-promotion follow-up in `tracking/conflicts.md`: `meshagent-sync` should avoid patch-mode edits on Markdown list regions and should list/fetch ContextBase docs before writing same-day session logs or mirrors.

### 2026-07-24

- Drained `memory/inbox/2026-07-23-prefill-kv-bank-slot-overwrite-semantics.md` into `memory/topics/s6a-prefill-warm-start.md`: prefill KV bank slots are chunk-position-indexed, not append-only. Fanout children overwrite the previous child's suffix in place, the shared prefix is reused by not writing those slots, and no explicit erase is needed; multi-request simultaneously-addressable KV remains the T0.5/M1 boundary.
- Drained `memory/inbox/2026-07-23-host-kv-code-placement-convention.md` into `memory/project.md`: per-kernel host-side serving/control helpers live beside each kernel's `launch.py` while kernel forms are still converging, not under `waferengine/engine/` or `models/<kernel>/host/`.

### 2026-07-23

- Drained `memory/inbox/2026-07-22-s6b-force-decode-bringup.md`: S6b Step 1 and Step 2 are now sim-verified for F>1. The host owns the forced-token sequence and feeds the same deterministic 2-D `forced_tokens[F][bsz]` to device and oracle; device output during forced steps is not trusted. Step 1 preserved color-7 balance by keeping the token drain additive, and Step 2 deliberately mirrors ht_tail skip vs ht_head drain gates.
- The controlled S6b F-sweep falsified the earlier toy-scale pipeline-fill hypothesis: cycles fall linearly with forced-step count, indicating fixed skip-compute savings rather than a saturating pipeline knee. Force-decode is still cheaper per forced token at this scale, but real-scale/block-compute-dominated measurements are needed before quoting pipeline-overlap benefits.
- Drained `memory/inbox/2026-07-22-color-audit-floorplan-decode-gotchas.md`: for pure decode KV-ingress layout, `csl-color-audit --floorplan` can show spurious fused-prefill regions and render 1-PE helper strips only as badges, while the matrix view omits switch/router helper PEs entirely. Treat `launch.py`/CSL placement as authoritative for these cases.

### 2026-07-20

- Drained `memory/inbox/2026-07-19-prefill-prefix-reuse-real-scale-perf.md` into `memory/topics/s6a-prefill-warm-start.md` and this plan. Real-scale WSE-3 prefill prefix reuse is now measured at Qwen3-1.7B dims / 524,288 PEs / L=8192: 25% reuse saves 7.7%, 50% saves 22.8%, and 75% saves 45.2% (all byte-identical). Prefix reuse is strongly sub-linear in hit fraction because it skips the cheap early chunks and recomputes the expensive suffix.
- Corrected decode interpretation: retain does not make an equal-work decode step cheaper (~0.02% bookkeeping overhead); it saves by skipping already-executed decode steps. Correct real-scale end-state comparison saves 34.6% total decode work.
- Captured operational guardrail for device measurements: per-point stdout logs are the durable result because `out_*` artifact dirs stay on worker nodes; quote host wall only as context, not latency.

### 2026-07-19

- Drained `memory/inbox/2026-07-19-s6a-prefill-warm-start-bringup.md` into the new topic `memory/topics/s6a-prefill-warm-start.md` and this plan. **Prefill warm-start (`START_CHUNKS` prefix reuse) now executes and is byte-identical in sim and on real WSE-3** — it had never actually run before, because a fabric deadlock masked everything downstream.
- Three independent defects found and fixed: an odd-extent async `fabin → fabout` `@mov16` that silently deadlocks WSE-3 (isolated to an 8-PE reproducer, promoted to the `csl-odd-extent-fabric-forward-hang` skill); an `ht_head.csl` branch hardcoding chunk slot 0; and two host places that assumed `start_chunk == 0`, one of which silently ran warm requests cold.
- Capacity walls differ by kernel: prefill stops at `MAX_SEQ_LEN = 2048` on PE data memory plus task table, decode at 512/1016 because the DSD `.stride` field is `i8`. The decode wall is an ISA field width, not memory, and is unrelated to the similarly-sized ~512 prefill SRAM figure in `e2e-pdSeparate-device-validation.md`.
- Headline (mock scale only, **not** a performance result): prefill prefix-reuse saving tracks **(k/n)², not k/n** — the reused prefix chunks are the cheap ones. If it holds at real dim, prefix reuse has strong diminishing returns. Flagged as must-re-measure before use.

### 2026-07-18

- Drained `memory/inbox/2026-07-16-fabric-no-keyed-routing-orchestration.md` into `memory/topics/csl-control-payload-mechanisms.md`. Durable framing: WSE fabric has no keyed/content routing; KV gather and related ML communication patterns are static topologies driven by deterministic steppers/rotations/chains. Added a follow-up to discuss how this constrains KV reuse/tiering designs.
- Moved generated all-kernel state-machine aggregate indexes from `memory/inbox/` to `assets/kernel-algo/` and updated `memory/topics/qwen3-kernel-analysis-atlas.md` so they stop appearing as un-drained captures.


> **Canonical M0 plan/state lives in the in-repo durable docs** (`ROADMAP.md`, `PROGRESS.md`,
> `milestones/M0-reuse-foundation.md`) per repo precedence; entries below are background.

### 2026-07-13

- Drained `memory/inbox/2026-07-13-kv-management-abstraction-design.md` into `memory/topics/s6a-decode-kv-retain.md` and corrected the parity-topic pointer. Durable decision: KV compute is shared enough to keep the seam isolated, but integrated kernels lack the runtime multi-round lifecycle where retain attaches, so S6 stays standalone-first and extraction waits for S4/S5. Prefill retain is viable as a `start_chunk` warm-start; force-decode remains an M2 mechanism.

### 2026-07-12

- **M0/S3 keyed KV store skeleton designed** (design-only; awaits Le's review before S4–S6 coding).
  Resolved for M0: key = **request id**, granularity = **whole-blob/exact key**, storage =
  **host-side keyed retained pool**, plus a **retrieve-by-key API**. Prefix-hash content key +
  token-vs-block match parked to M1 (block-constrained). Full design in
  `milestones/M0-reuse-foundation.md § S3`; background folded into
  `memory/topics/kv-cache-policy-tradeoffs.md` (2026-07-12 Updates).
- **Mechanism vs policy separation (Le):** M0 delivers the on-chip KV *sharing mechanism*; policy
  (hit detection, eviction) is deferred and not needed yet (M0/M1 use self-constructed artificial
  token ids). **New placement axis surfaced (was missing from GOALS): where the store + eventual
  policy runs — host (P1) / on-chip all-PEs (P2) / on-chip entrance PE (P3).** All three **open,
  nothing rejected**; host **for now** (least-effort, mechanism-only). SDK v2.10 note: on-PE allows
  only a compile-time integer-keyed table (no map/heap/strings/recursion). Escalated to `GOALS.md §7` + WS4.
- Prior M0 work (background): S1 status re-check gate (2026-07-11) and S2 PR#14 port contract
  (2026-07-11) — see `topics/pr14-real-serving-port-contract.md`.

### 2026-07-09

- Drained `memory/inbox/2026-07-09-e2e-kernel-qa-log.md` into `memory/topics/e2e-kernel-dataflow-and-topology.md` plus this plan. Durable finding: fused e2e carries KV state on-chip, but decode step 0 is seeded by host/config token ids rather than prefill's sampled first token.
- Captured decode topology details: demux/HT_head seams, K-pipe strip mechanics, forced color aliasing, latent `P_Y_BLOCK_NUM >= 4` west-strip hazard, and the new `assets/decode-kpipe/kpipe-south.svg` diagram.
- Recorded the delegated tensor-layout reference under `assets/data-layout/`, including the decode/prefill axis rotation and follow-up source-cleanup items.

### 2026-07-06

- Drained `memory/inbox/2026-07-06-prefill-decode-transfer-bandwidth.md` into this plan and `memory/topics/prefill-decode-transfer-bandwidth.md`. The durable finding is that the fused e2e KV handoff has three timed pieces — prefill gather+transform, north seam shift, and decode receive+cache write — and effective bandwidth must include the compute-heavy transformations, not just wire time.
- Preserved the timing mechanism/design update: use per-PE TSC (`<time>`, 48-bit, 1.1 GHz), first split segments per PE, then cross-PE reference-corrected end-to-end GB/s.
- Converted `memory/context.md` and `tracking/status.md` into thin generated projections pointing here and to topic notes.

### 2026-07-05

- KV-cache policy tradeoff and standalone-vs-integrated parity topics captured the main research framing for preserve/evict work.

### 2026-07-22

- Drained seven 2026-07-21 WaferEngine-staging captures. Added `memory/topics/s6b-force-decode.md`: decode already force-decodes one host token at step 0, so S6b generalizes this to token-granular `F`; `F=1` is today’s inert baseline, with staged S0/S1/S2 implementation and a still-unverified pipeline-speed hypothesis.
- Updated `memory/topics/s6a-prefill-warm-start.md` with the prefill metainfo two-channel bridge: per-request scalar metadata rides both the i32 token-id prepend path and the fp16 X-tile append path, bridged/re-stamped at `ht_head`; widening must update both or deadlock.
- Updated `memory/topics/s6a-decode-kv-retain.md` with the retain/recompute distinction: retain carries the effective-length counter; RoPE phase is recomputed from that counter each round, not carried as live phase state.
- Updated `memory/topics/prefill-decode-transfer-bandwidth.md`: profiler-off `fullT` proves full-size KV transfer is healthy; the widened per-step profiler is the hang. Single-link WSE-3 device ceiling is 3.91 GB/s, so the ~1.8 GB/s aggregate KV-transfer result is latency/serialization-bound, not fabric-ceiling-bound. Added e2e TSC/toolchain gotchas.
- Added a CS-3 operational pitfall to `memory/project.md`: ssh transport death (`rc=255`) can bypass the timeout guard’s `csctl cancel`, so check for orphan wafer jobs on reconnect.
