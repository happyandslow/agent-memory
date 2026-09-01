# Wavel compute-profile model and batch domain — 2026-09-01

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## Situation

When constructing the first handwritten-plan predictor matrix for coarse
Attention and FFN templates, changing from one PE rectangle/model configuration
to another can also change batch size. Treating such points as a single
"component-size" sweep confounds PE geometry, workload size, and model-family
effects and cannot support a defensible prediction function.

## Confirmed decisions and verified boundary

- Le added Qwen3-1.7B coarse Attention/FFN prediction alongside Qwen3-4B. The
  two Qwen families retain separate frozen model identities; hidden size, head
  dimensions/counts, and FFN dimension are not silently varied inside one
  model-family identity.
- `batch_size` is an explicit performance-model input axis, separate from the
  exact `PERegion` width, height, and placement. A batch binding may create a
  distinct compile-time `ImplementationVariant`, while one calibrated model
  artifact may cover multiple batch/rectangle variants only within its
  declared and validated applicability domain.
- Le selected a decode-only first stage. Prefill will use a separate
  template/model/evidence domain rather than consuming decode calibration.
- S3 will audit batch candidates `{1, 2, 4}` independently for each model
  family and exact template generator. Candidate values are not presumed
  materializable; unsupported points stay out of M2 measurement and fail
  closed in provider queries.
- Decode Attention exposes `active_kv_length` as an explicit model input axis,
  separate from batch and PE geometry. FFN does not carry this axis. The exact
  KV-length sample values remain a later S3 benchmark-matrix decision.
- Le selected a planned 34-configuration sparse matrix instead of a complete
  Cartesian product. Across Qwen3-4B and Qwen3-1.7B, 22 configurations cover
  anchors and single-axis sweeps; 12 cover the selected interactions. Each
  model/component uses `small`, `canonical`, and `large` rectangle levels;
  Attention uses two KV-length levels. The first matrix holds absolute
  placement, the exact communication template, and one common repetition
  policy fixed.
- The 34-point count excludes repetitions, separate communication-template
  profiling, and full-layer sanity runs. Rectangle triplets are selected
  independently around the current example deployment for 4B Attention, 4B
  FFN, 1.7B Attention, and 1.7B FFN; each model also selects its own low/high
  KV pair. Initial local results determine the later geometry pivot.
- Every runnable setting records two consecutive invocations in the same job
  without restart and adds a third invocation if the first pair differs by
  more than 1%. If all 34 configurations materialize, this creates 68 to 102
  recorded observations excluding warmup. The exact rectangle dimensions, KV
  values, 1% relative-difference formula, post-third-run aggregation, and
  instability gate remain open. Every planned point must pass exact-generator
  materializability; an unsupported point becomes a coverage gap rather than
  being replaced merely to preserve the count.
- A pair such as `(256x256, batch=4)` versus `(128x128, batch=1)` does not by
  itself identify either batch scaling or geometry scaling. The benchmark
  design must include cross/anchor points or preserve unsupported/unmeasured
  combinations as `unknown`/out-of-domain; it must not infer a separable model
  from two confounded points.
- At the audited live source boundaries, the selected Qwen3-4B config records
  `bsz=1` and derives `256x256` role rectangles. Tracked Qwen3-1.7B bench
  configs record `bsz=1` for the currently visible `256x128` and `128x128`
  block-shaped examples. Therefore batch 4 is a proposed future matrix point,
  not an already verified baseline at these locators.

## Implications / next actions

- [ ] S3 must audit materializability and freeze separate benchmark manifests
  for both model families, including legal batch values and rectangle sets.
- [ ] Freeze the exact anchor, rectangle levels, two KV-length values,
  interaction points, 1% comparison formula, post-third-run aggregation, and
  instability gate for the bounded decode measurement design.
- [ ] Decide how exact absolute placement participates in compute-model
  applicability and what evidence, if any, permits translation invariance.
- [ ] Replace any fixed count such as "eight shape points" with a matrix over
  model family, component, batch, rectangle, and Attention-only KV-length axes.

## Pointers

- `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode/model_config/device_2x4_8k.json`
- `/home/lexu/WaferEngine/models/qwen3_1p7b-decode/bench/layer_block_rec/model_config/test_device_rect_256x128.json`
- `/home/lexu/WaferEngine/models/qwen3_1p7b-decode/bench/layer_block/model_config/test_device_4x2block.json`
- `projects/wse3-performance-model/memory/inbox/2026-09-01-wavel-provider-contract-first-batch-closure.md`
