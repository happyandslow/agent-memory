> Persisted snapshot. [ContextBase handoff](https://context.ed-aisys.com/doc/2026-09-13-handoff-layoutc-tall-a2-first-group-and-cs-3-latency-atCsdearmd). [Self-contained source/design/figure/evidence bundle](../artifacts/2026-09-13-layoutC-handoff-bundle.zip). Local source citations below refer to gala2; on another machine use the corresponding paths inside the bundle. The nested canonical handoff is `docs/reports/2026-09-13-layoutC-implementation-handoff.md`.

# LayoutC implementation handoff — 2026-09-13

Owner: Le Xu. Scope: the unequal-height Qwen3-4B A1/A2/A3 implementation,
first-group correctness, preliminary single-layer performance, and the remaining
full-model integration. Evidence cutoff: 2026-09-13. This handoff adds no device run.

## 1. Start here

The first five-layer group runs on real CS-3 using independent synthetic layer
banks and on-wafer feedback. A separate matched single-layer benchmark is complete.
The trained 36-layer model, mirrored compute groups, inter-group links, live KV
bootstrap, Head/Tail, and request loop have not been demonstrated by this work.

The ultimate objective remains to run the complete 4B model with the new layout,
preserving the original arithmetic operators. Complete-group correctness precedes
downstream integration claims; full-model performance follows full-model correctness.
The preliminary single-layer experiment was separately requested and is not that
final performance gate.

Read these in order:

1. [First-group implementation and verification](/home/lexu/wse3-performance-model/docs/reports/2026-09-13-layoutC-first-group-feedback.md).
2. [Single-layer CS-3 performance](/home/lexu/wse3-performance-model/docs/reports/2026-09-13-layoutC-single-layer-performance.md).
3. [Reviewed full-model routing plan](/home/lexu/wse3-performance-model/docs/plans/2026-09-13-layoutC-full-model-routing-allocation.md), especially its final implementation checkpoint.
4. [First-group Claude Code review](/home/lexu/wse3-performance-model/docs/reports/2026-09-13-layoutC-first-group-feedback-review.md) and [routing-plan review](/home/lexu/wse3-performance-model/docs/reports/2026-09-13-layoutC-routing-plan-claude-review.md).
5. [Original-code numerical attribution](/home/lexu/wse3-performance-model/docs/reports/2026-09-11-layoutC-upstream-numerical-attribution.md) and [aligned-step output](/home/lexu/wse3-performance-model/docs/reports/2026-09-11-layoutC-aligned-step-validation-output.md).

## 2. Live source identity and entrypoints

Workspace: `/home/lexu/wse3-performance-model`; branch `main`; HEAD at handoff
`38ac5b7a7d999689fe472c766e233fe545502c95`; origin
`https://github.com/happyandslow/wse3-performance-model.git`.
The demo is untracked, so HEAD alone does **not** identify its source. The companion
handoff bundle contains a current source snapshot and per-file SHA-256 manifest;
the experiment archives separately preserve the exact executed versions.

| File / implementation site | Responsibility |
|---|---|
| [launch_tall.py:91](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/launch_tall.py:91) | Geometry, role-specialized images, fixture baking, routes, compilation, execution and output checks. `--feedback` selects multiple local banks. |
| [tall_layout.py:64](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/host/tall_layout.py:64) | Full geometry and capacity; `y_group` caps full-size reduction subgroups at 16. |
| [tall_stage.csl:127](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/src/tall_stage.csl:127) | `next_stage`, X/Z redistribution and queue phase changes. |
| [tall_stage.csl:183](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/src/tall_stage.csl:183) | A1/A2/A3 schedule; bank selection, QKV sender selection, residual sends, input release. |
| [group_link.csl:63](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/src/group_link.csl:63) | Two-fragment f16 endpoint protocol, markers, ACK and readiness. |
| [group_strip.csl:26](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/src/group_strip.csl:26) | Router strip bootstrap, terminal notification, reset scan and START. |
| [group_routing.py:33](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/host/group_routing.py:33) | Actual first-group route construction. |
| [group_allocation.py:73](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/host/group_allocation.py:73) | Captured allocation and conflict checking; inspect compiled image parameters as well. |
| [group_fixture.py:11](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/host/group_fixture.py:11) | Distinct layer weights, per-bank cache and input packing. |
| [group_reference.py:236](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/host/group_reference.py:236) | Existing operators evaluated in the geometry's reduction/rounding order. |
| [run_tall_bounded.py:20](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/scripts/run_tall_bounded.py:20) | Whole-process deadline; CS-3 controller must retain ownership of job cleanup. |

Original baseline: `happyandslow/WaferEngine` commit
`b136ab64b3f5575c72fb722fb972ef5c77f4c9fe`, `models/qwen3_4b-decode`.
Its local [decode.csl](/home/lexu/wse3-performance-model/demo/qwen3-4b-decode-sram/code/qwen3_4b-decode-baseline/src/decode.csl)
has SHA-256 `c3da0e464dfefb8831dc17c32c8eee27485919e5b54a1d9374b0838af774272b`.
Use the original adapter frozen in the performance archive, not an arbitrary
current unsplit mini path. The adapter changes boot ownership, not the original
arithmetic/collective function bodies.

## 3. Geometry and retained design decisions

Dimensions below are **columns × rows**. Within one unmirrored 256×256 block:

| Region | Logical block coordinates | Hidden shard per row |
|---|---|---:|
| A1 | x0–127, y0–79 | 2560 / 80 = 32 |
| Spare | x0–127, y80–95 | — |
| A3 | x0–127, y96–255 | 2560 / 160 = 16 |
| A2 | x128–255, y0–255 | 2560 / 256 = 10 |

A1/A2/A3 are separately specialized images. This does not prove every irrelevant
placeholder buffer was eliminated; complete per-region dead-buffer/SRAM auditing
remains a follow-up, especially before real weights and external components.

- **QKV:** one sender per A1 column: `(c, c mod 80)`, 128 senders total. C8
  handles c0–79; C9 handles c80–127. Rows0–47 contain two distinct senders,
  not two sends from every column. Each fragment reaches its matching A2 column,
  then broadcasts along that column. Column ownership is unchanged.
- **X and Z:** preserve global feature indices when converting 32→10 and 10→16
  elements per row. Current internal X/Z paths use two-element transfer atoms;
  this is distinct from the new router-only external feedback path.
- **A3→A1 feedback:** select A3 column0 in each row because output is replicated
  horizontally. Two distinct 16-value rows form one 32-value A1 row, then each
  target column receives a copy. This is concatenation, not reduction.
- **Source order:** forward upstream traffic before injecting the local source.
  Northbound first-group order is descending A3 rows: `2r+1` fills offset16,
  then `2r` fills offset0. Strips forward/turn payload in routers; strip CE tasks
  handle control/reset. Do not reintroduce mandatory CE payload relay at each hop.
- **Markers and readiness:** counted f16 receives and ordered control wavelets
  share the data path. IQ0 is blocked during the counted transfers and unblocked
  for marker dispatch. Payload counts alone do not release the next frame.
- **Terminal/reset:** keep termination inside the final receiving row; ROW_DONE
  precedes STREAM_END. All row0 PEs join acknowledgment after STREAM_END and X
  consumer completion. Terminal notification must reach the bottom root before
  reset; reset return precedes START. Local readiness is not a global drain.
- **Resources:** collective IQ/OQ3–7 remain reserved. First-group A1 feedback
  uses IQ0; A3 OQ1 uses U16, OQ2 uses D17, IQ2 receives START15. R uses horizontal
  C18/C19 and vertical C18/C23. A2 retains its own spatially disjoint C16.
  See actual allocation/code rather than treating a color as globally free.
- **Scheduling:** change weight/KV bank for each layer; keep token position fixed
  through its layers. Advance RoPE once per token. The fixture supplies independent
  token inputs; it does not implement full-model autoregressive credit safety.
- Preserve operators and existing numerical behavior. Layout-dependent local
  accumulation/reduction order may change native bits. Do not relax tolerances
  or replace operators merely to force ideal NumPy agreement.

The conceptual K-pipe role now belongs to WEST x131 and CENTER x388 bridge strips,
plus the bottom turn. Do not add the old separate eight-pipe module on top of them.
Full-model transport names are U/D (north/south), B (bottom turn), H/T (Head/Tail),
K (KV bootstrap), and R (control/rearm). Their full allocation remains proposed.

## 4. Full-model placement: design, not an integrated executable

Proposed footprint: 650×1028 including external components/corridors.

| Group | Layer IDs | x | y | Orientation |
|---|---|---|---|---|
| G0 | 0–4 | 132–387 | 2–257 | south |
| G1 | 5–9 | 132–387 | 258–513 | south |
| G2 | 10–14 | 132–387 | 514–769 | south |
| G3 | 15–19 | 132–387 | 770–1025 | south |
| G4 | 20–23 | 389–644 | 770–1025 | north, mirrored |
| G5 | 24–27 | 389–644 | 514–769 | north, mirrored |
| G6 | 28–31 | 389–644 | 258–513 | north, mirrored |
| G7 | 32–35 | 389–644 | 2–257 | north, mirrored |

Head x3–130/y2–257; Tail x3–130/y258–513; mux on y514. Host/demux x0–2;
service reserve x3–130/y515–1025; EAST KV strip x645; auxiliary x646–649;
north corridor y0–1; bottom corridor y1026–1027. Mirroring must transform logical
rows in compute, weight/KV packing and routes together, not only rectangles.

![Full-wafer region/color audit — analytical, not final compilation](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-13-layoutC-color-regions.png)

This figure predates the final route proposals and first-group implementation.
Use it for placement and baseline region claims. The reviewed routing plan and
actual first-group allocation supersede its unassigned or historical color entries.

## 5. Validated results and their limits

| Evidence | Result | Boundary |
|---|---|---|
| CS-3 f16 transport microtests | Both directions; distinct consecutive frames; delayed receiver; dropped/duplicated fragment and held receiver controls | Transport microtest, not mirrored compute |
| CS-3 mini five layers × 33 tokens | 10,560 exact normal output elements | Synthetic, independent banks/inputs |
| CS-3 full five layers × 2 tokens | 5,120 exact normal output elements | Final device computation code |
| CS-3 full five-layer cache probe × 33 tokens | 83,886,080 K/V values and all bank cursors/steps checked; corruption control fails | Disposable on-device comparison; last frame is flags, not normal FFN output; previous 32 frames normal |
| CPU aligned-step intervention | Four comparisons, each 6,668 checkpoints / 5,804,436 checked values exact | Analytical replay anchored to previous CS-3 final arrays; not device intermediate replay |
| Claude Code first-group follow-up | No remaining blocking findings reported | Review scope/dispositions retained; not full-model approval |

Full final-code job: `wsjob-7fc9rfiaksqi9xvxntsisf`; full cache job:
`wsjob-2ihkgma7mxwmshtygk8npc`. See evidence JSONs for every job and configuration.
No diagnostic/cache probes remain in maintained kernels. Earlier large-subgroup
blocking is not diagnosed; successful full-size evidence uses subgroups of 16.

The source-order oracle is NumPy/CPU code modeling the existing device operators
and each layout's ordering; it is distinct from the ideal mathematical NumPy
reference. Original operators already differ from that mathematical reference.
Native tall and original outputs need not be bit-identical. Earlier standalone
max-absolute mathematical checks still fail; they were not silently relaxed.

### Preliminary single-layer latency — real CS-3

| Initial historical KV length | Original ATTN+FFN cycles | Tall A1+A2+A3 cycles | Tall/original |
|---|---:|---:|---:|
| 1280 | 26,377 | 102,511 | 3.886× |
| 5120 | 28,000 | 104,330 | 3.726× |

Batch1, BF16, one layer, seed910 synthetic dense weights, capacity8192; dimensions
hidden2560/attention4096/KV1024/head128/FFN9728. Same logical weights, inputs and KV
in both geometries. Three independent jobs per cell, 33 decode inputs per job,
first4 excluded from timing statistics, median of29 then median across3 jobs.
All 1,013,760 normal-run output elements match their respective source-order oracle.

“Prefill1280” means **1280 preloaded historical KV positions**, not measured prefill
execution. First decode attends to1281 logical positions including its new K/V;
later lengths grow. No real prompt, trained checkpoint, embedding or prefill kernel
executes here.

A single collector PE records TSC before START and after every output row has
completed. D2H occurs only after all33 intervals. The interval includes on-wafer
release/collection/ACK overhead and serializes input admission. It excludes
Head/Tail, layer feedback, host transfers and prefill. It is not pipeline throughput.
Empty boundary costs8231/8232 cycles; it was not subtracted because completion can
overlap computation. An inserted1,000,000-cycle delay increased the reading by
1,000,026 cycles. No frequency conversion was assumed.

The new block reserves65,536 PEs versus131,072 original; half the area does not
imply lower serial latency. The experiment has not localized the slowdown. Larger
per-PE work and X/Z movement are hypotheses to measure, not established causes.

![Measured serialized single-layer latency](/home/lexu/wse3-performance-model/docs/reports/2026-09-13-layoutC-single-layer-performance.png)

## 6. Diagram guide and supersession

Editable `.excalidraw` files are preserved with PNG/SVG exports in the handoff
bundle. Existing diagrams are copied without redrawing or changing their labels.

| Diagram | Read it as |
|---|---|
| [2026-09-13 color regions](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-13-layoutC-color-regions.png) | Current proposed full-wafer geometry; baseline color audit, not final route dump |
| [QKV travel, all senders](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-10-layoutC-travel-qkv.png) | All128 sender locations and column-preserving transport |
| [X travel](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-10-layoutC-travel-x.png) / [Z travel](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-10-layoutC-travel-z.png) | Internal redistribution; distinguish this CE forwarding from new external strips |
| [North switch time slices](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-12-layoutC-north-switch-timeslices.png) / [South switch time slices](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-12-layoutC-south-switch-timeslices.png) | Agreed source-order/router-switch concept; final marker/reset details are in implemented protocol |
| [Hidden reshard](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-10-layoutC-hidden-reshard.png) / [weight axes](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-10-layoutC-weight-axes.png) | Why row shards are32/10/16 and which logical tensor axis changes |
| [Older full allocation](/home/lexu/wse3-performance-model/docs/diagrams/2026-09-10-layoutC-full-allocation.png) | Historical geometry proposal; superseded by the unequal-height/current regional plan |

Older three/five-color alternating CE-relay budgets and the half-height A2 picture
are historical, not requirements of the implemented router-only feedback.
The earlier outside-target STREAM_END collision is why termination stays inside
the last target row. That first-group fix has evidence now; stacked integration
still requires its own test. Do not interpret older memory's “pending validation”
sentence as the current first-group state.

## 7. Reproduction and portable evidence

The companion `2026-09-13-layoutC-handoff-bundle.zip` contains current maintained
source/config snapshots (excluding compiler binaries/build outputs), diagram source
and exports, the reviewed design/audit, results/reviews, and the existing first-group,
single-layer performance and aligned-step reproduction archives. `MANIFEST.json`
records byte counts and SHA-256 for every archived file. `HANDOFF.md` is this document.
Historical attribution report/evidence is included; its older large reproduction
archive remains in the work repository and is not required for the new benchmark,
whose archive already freezes its original adapter and fixture.

Primary original reproduction hashes:

- First group: `85abda6c641f7fec422cf49e9cdd4764b1650c1aaaeb74a2a97692a01d7f08b2`.
- Single-layer performance: `c61bc2143a613a137b687daa2f75be2809a8cec1bcb9f066202243bd7637dd4e`.

Extract each nested reproduction archive into a separate directory. Its README
is authoritative for dependencies and launch context (SDK2.10/WSE-3/BF16).
From the performance reproduction directory, `python analyze.py` rechecks preserved
raw outputs and timing against stored predictions without hardware access.
New hardware runs require the normal authenticated CS-3 launcher and bounded
controller ownership; do not assume the previous connection/job is still live.

Examples on that launcher, from the respective archive's stated working directory:

```bash
# First-group archive: device/ directory
python device.py --case handoff-full --seconds 2400 --options="--feedback --profile full --layers 5 --steps 2"
# Performance archive: extracted root; use unique case names per repetition
python device.py --case handoff-tall --options="--variant tall --prefill 1280"
python device.py --case handoff-original --options="--variant upstream --prefill 1280"
```

The public `launch_tall.py` CS-3 path currently requires feedback and at least two
banks ([guard:100](/home/lexu/wse3-performance-model/demo/qwen3-4b-thinner-stage/layoutC/code/launch_tall.py:100)).
Reproduce the single-layer timing through its dedicated archive, not by inventing
`--feedback --layers 1`. Re-run disposable cache checks after bank/stride changes.

## 8. Next work and acceptance gates

1. **Integration track:** mirror one compute group using a consistent logical-row
   mapping; check two groups and the bottom turn, then all eight groups. Require
   every layer ID0–35 exactly once per model token, unchanged token position across
   layers, separate banks, exact tagged transport and own-order numerical checks.
2. **External components:** finish H 10→32 and T 16→10 resharding; implement live
   per-layer/per-column KV packing, reset/READY and cursors; reconnect Head/Tail,
   record mux, CONFIG, sampling/forced modes, token return, STOP and new-request
   rearm. Audit the complete physical color/queue/port manifest, including turns.
   Standalone southbound transport is not proof of mirrored computation.
3. **Performance diagnostic track:** if chosen next, time A1/A2/A3, QKV and X/Z
   with compatible boundaries to locate the measured latency cost before optimizing.
   Preserve original operators; do not equate single-layer latency with full-pipeline
   throughput. The present handoff does not pick an optimization as already justified.
4. **Resource closure:** recheck linked code/data/task-table limits and eliminate
   unnecessary role buffers; full-model trained-weight/context capacity is not
   guaranteed by the synthetic first-group fit. Larger subgroup hangs remain open.
5. **Numerical deepening:** CPU aligned-step evidence is complete for its fixtures;
   on-device aligned intermediate replay remains additional coverage, not a result
   already obtained. Do not mistake final-output agreement for every intermediate.
6. **Final gate:** trained full-model correctness, consecutive tokens and requests,
   failure/STOP boundaries, then end-to-end latency/throughput measurement.

Retain the [communication-methodology TODO](/home/lexu/wse3-performance-model/demo/communication-algorithm/TODO.md)
as a separate evolving workstream. Do not overwrite its newer CP tasks with this
LayoutC snapshot. The project-wide M1 tracking files and generated memory views
also contain older/different-scope cursors; this handoff does not rewrite them.

## 9. Handoff validation and write boundary

This task writes documentation, a portable evidence/source bundle, one compact
memory inbox locator, and an authenticated ContextBase log with attached artifacts.
It does not modify computation, launch jobs, or alter tracking acceptance gates.
Validation checks local links, archived hashes, reproduction analysis, memory mirror
identity, and ContextBase read-after-write attachment/page placement. The separate
persistence receipt records the resulting URLs, hashes and live repository status.
All changes stay unstaged/uncommitted; no Git history-changing operation is authorized.
