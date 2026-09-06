# Qwen coarse-component geometry and KV audit — 2026-09-01

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

## Situation

Before freezing the first coarse Attention/FFN benchmark matrix, the proposed
three rectangle levels and two Attention KV-length levels must be checked
together against the tracked Qwen3-4B and Qwen3-1.7B generators. Treating the
geometry and KV axes independently can create nominal matrix points that the
same artifact cannot represent.

## Verified finding

- At the clean Qwen3-4B source boundary
  `93a6d0e6986ac1cd91c8abc80fa9e0a032e13f52`, the role-split generator creates
  separate Attention and FFN images but requires one shared square block size.
  The canonical device configuration materializes both roles only at
  `256x256`; no tracked isolated or rectangular 4B role generator exists.
- At WaferEngine `fcfc8c163a4bebe0d886ae062334dfcb1b0d8406`, the tracked
  Qwen3-1.7B benches cover a full transformer layer at `128x128` and
  `256x128`, while the full deployment uses `256x256`. Attention and FFN run
  sequentially on the same transformer-block PE region. The rectangular source
  separates X and Y sharding and records phase-segment boundaries, but it does
  not provide independently materializable Attention/FFN templates; its host
  bench also explicitly omits numerical validation.
- Consequently, the 4B and 1.7B template decompositions differ. 4B has disjoint
  role templates and an inter-role edge; the first 1.7B contract has one direct
  full-layer template with two exclusive phase-prediction boundaries and no
  invented inter-region edge. A future 1.7B role split is a new implementation
  variant requiring new evidence.
- The geometry trio `128x128`, `256x128`, `256x256` is arithmetically compatible
  with both frozen model shapes: all hidden, attention, KV, and FFN shard widths
  remain integral and the GQA ratios are preserved. It also permits the
  source-backed prefill bindings `4096/7936` for 4B and `256/768` for 1.7B
  across both Y extents. In the current decode order, the new K/V entry is
  appended before the score operation, so the corresponding first scored
  active-KV lengths are one larger if `active_kv_length` uses post-append
  semantics. Le confirmed the post-append query meaning: the selected 4B
  seed/active pairs are `4096/4097` and `7936/7937`; the 1.7B pairs are
  `256/257` and `768/769`. Repetitions must re-arm the same seed.
- Le selected `128x128`, `256x128`, and `256x256` as the first L-shaped
  geometry sweep. `128x256` is the first follow-up cross-point before claiming
  a general independent-X/Y model. A current full generator's block-aligned
  prefill restriction may reject later geometry/KV combinations, but it is not
  a general reason to forbid height 512 for a future bounded component
  generator.

## Next action

- S3 must classify exact/partial/missing coverage for the selected geometries,
  add the bounded 4B standalone role generators or explicit completion gaps,
  keep 1.7B phase metrics on one full-layer variant, and re-deduplicate the run
  manifest. The former 34 count is only a query/result-coverage upper bound,
  because one 1.7B invocation can produce both phase metrics.

## Evidence pointers

- `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode/launch.py:188-203,240-269,334-375,1082-1123`
- `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode/model_config/device_2x4_8k.json`
- `/home/lexu/worktrees/1.7b-pipeline-af/models/qwen3_4b-decode/request_config/device_prefill4k.json`
- `/home/lexu/WaferEngine/models/qwen3_1p7b-decode/bench/layer_block/model_config/test_device_4x2block.json`
- `/home/lexu/WaferEngine/models/qwen3_1p7b-decode/bench/layer_block_rec/model_config/test_device_rect_256x128.json`
- `/home/lexu/WaferEngine/models/qwen3_1p7b-decode/bench/layer_block_rec/utils.py:38-104`
- `/home/lexu/WaferEngine/models/qwen3_1p7b-decode/bench/layer_block_rec/src/decode.csl:1197-1266`
- `/home/lexu/WaferEngine/models/qwen3_1p7b-decode/model_config/test_device_2x4block_kv_varlen.json`
