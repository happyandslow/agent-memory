---
topic: pe-sram-memory-breakdown
tags: [waferengine, wse3, meshjit, code-relocation, sram, prefill]
date: 2026-08-04
---

# MeshJIT control-flow relocation: forward branches OK, backward (loop) branches are absolute

Follow-on to the PR #14 prefill SRAM profile (`.text` = the #1 per-PE cost; prefill compute PE
binding at ~92%). Goal: shrink resident `.text` by fetching cold kernel code over the fabric from a
holder PE (`wse-runtime-remote-code-loading` / MeshJIT). Its invariant #1 claims relocated code must
be **leaf + branch-free** — we tested the branch-free half.

## Experiment
`~/MeshJIT/controlflow-experiment/` (copy of `feasibility-demo`). Added two branchy-but-leaf
candidates, both computing `c = x+y`, ran the holder→receiver byte-transfer + `@bitcast`-jump in the
**local sim** (K=8). Discriminating knob = receiver slot address vs candidate source address.

- `cand_cond` (40 B): forward `if (x[0]>0) faddh else fmulh`.
- `cand_loop` (88 B): backward `while (i<nloop[0]) c[i]=x[i]+y[i]`; `nloop` runtime-written so cslc
  can't unroll it → a real backward branch.

## Result (simulator)
| candidate | slot ≠ src (0xb000) | slot = src (0xa800) |
| --- | --- | --- |
| mul/add/madd (straight-line) | PASS | PASS |
| **cond (forward branch)** | **PASS** | PASS |
| **loop (backward branch)** | **STALL/hang** | **PASS** |

Only variable changed between loop PASS↔STALL was the slot address ⇒ **the backward/loop branch is
absolute-encoded (position-DEPENDENT); forward conditionals and straight-line code are
position-INDEPENDENT and relocate freely.**

## Refined rule (supersedes "branch-free" as too strong)
Transplanted code may contain **forward** conditionals, but a **backward branch (loop)** only runs
correctly if the receiver slot is at the **same address** as the source (or branch immediates are
patched by the slot−source delta after copy). Since virtually every real kernel (prefill compute,
init, teardown) is loop-heavy, MeshJIT-offloading them needs ONE of:
1. **address-matched slots** (link each offloadable kernel to a fixed addr; receiver slot at that
   same addr) — zero codegen change, just placement discipline; **cheapest unblock**;
2. **post-copy branch relocation** (patch absolute branch immediates on the receiver — needs the
   WSE-3 branch encoding, undocumented → reverse-engineer);
3. **PIC codegen** (cslc PC-relative-backward-branch mode, if it exists).

## Real CS-3 confirmation (physical wafer, 2026-08-04)
Ran the **matched** config (slot 0xa800 = cand_loop source) on the physical EPCC wafer (cloud
SdkCompiler --fabric-dims=762,1172 + SdkLauncher; RoCE egress to 10.27.28.180..198 = real silicon).
**ALL CANDIDATES PASSED, incl. cand_loop.** ⇒ on real WSE-3 a loop kernel transplanted over the
fabric and `@bitcast`-jumped runs bit-exact when the slot is **address-matched** to its source. The
**address-matched-slot strategy (option 1) is validated on silicon** — the concrete unblock. Repo:
`~/MeshJIT/controlflow-experiment/` (RESULTS.md), run on CS-3 at `~/meshjit-controlflow/`.

## Caveats / next
- The **mismatched** loop was NOT run on the appliance (would likely hang the wsjob); its stall is
  sim-confirmed only. The matched pass is the load-bearing positive result.
- **Leaf half untested.** init/teardown also *call* other fns (non-leaf). Next: a candidate that
  calls a helper, to test the leaf half independently.
- Perf for prefill is a non-issue (long compute-bound run; ~0.5 ms of fabric fetch vs ~7 s). The
  binding constraint is this relocation-correctness question, not performance.

## Related
- [[pe-sram-memory-breakdown]]; skill `wse-runtime-remote-code-loading` (invariant #1 refined here).
- Prefill `.text` candidate map: `/home/lexu/we-sram-profile/prefill_text_meshjit_candidates.md`
  (compute phase kernels = 14.4 KB / 45%, run one-at-a-time under the `prefill_struct` phase state
  machine → prime slot-streaming target).
