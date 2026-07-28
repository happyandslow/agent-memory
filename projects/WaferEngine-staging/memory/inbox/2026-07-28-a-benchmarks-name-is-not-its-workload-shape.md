# A benchmark's name is not its workload shape — audit what the request set actually exercises before measuring with it

Date: 2026-07-28 · Repo: `WaferEngine-staging` · `models/qwen3_1p7b-e2e-pdSeparate` (M2 kickoff)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

A model directory ships a standing end-to-end request set with recorded timings and a golden-token
reference. It is the obvious vehicle for the next experiment. Before reusing it, check what its
requests are *shaped* like — a set can be perfectly valid as a regression baseline and structurally
incapable of exercising the thing you are about to study.

## What `mtbench8` actually is

`models/qwen3_1p7b-e2e-pdSeparate/request_config/mtbench8/` — **8 independent single-turn prompts**
(`prompts.json` is a flat list of strings; no turn structure), MT-Bench-flavoured open-ended writing
and explanation tasks, driven against `serve_2x4_8k20k` with a commit-pinned
`golden_token_ids_<sha>.json` for bit-identity regression checks.

Shape: **prompts 21–36 tokens, generations 478–3381 tokens.** Decode-dominated, zero-reuse.

## Why that disqualifies it for a KV-reuse cost study

1. **It exercises no KV reuse at all.** Eight unrelated prompts, no shared system prompt, no
   multi-turn continuation — nothing to retain, offload, or recompute. **The name actively
   misleads: MT-Bench's "MT" is multi-turn, but this config drives it single-turn.** Anyone reading
   the directory name and assuming multi-turn reuse coverage would be wrong in the most expensive
   possible way.
2. **The prompts are shorter than the transfer quantization.** 21–36 tokens against
   `CHUNK_SIZE = 256`: every prefill ships one full padded chunk, so `per_req_kv_egress_ms` is a
   **floor**, not a length-proportional measurement. It cannot produce a bandwidth-vs-length curve —
   and a bandwidth *derived* from it inherits the padding assumption.
3. **It cannot separate the alternatives under test.** At `L_prompt ≈ 30`, re-prefill costs the
   ~57 ms fixed floor, force-decode costs ~30 tokens' worth, and offload moves one padded chunk —
   all three dominated by fixed costs. The crossings that matter live at `L` in the thousands.

## What it *is* good for

Exactly the baseline-reproduction role: recorded timings, a golden-token reference, and the
"8/8 bit-identical" device validation that the frozen `io_loc` pins cite as their justification.
Keep it for that; do not stretch it.

## What to do instead

- Read `prompts.json` (not the directory name) and write down: prompt length distribution,
  generation length distribution, shared-prefix structure, turn structure.
- Compare prompt length against every quantization in the path (chunk size, block size, page size).
  A workload below the quantum measures the floor, not the slope.
- For reuse studies, **fabricate** request sets with controlled shared-prefix fractions and explicit
  multi-turn structure. Ground the sharing ratios in published traces rather than inventing them —
  the Mooncake traces carry `hash_ids`, so exact prefix-sharing percentages are computable with no
  inference (see [[agentic-kv-trace-datasets]]).

## Confidence / attribution

Prompt text, count, token lengths, generation lengths, and the flat (turn-less) JSON structure were
read directly off `pr14-head:.../request_config/mtbench8/{prompts,request}.json` and `timing.json`
in-session. The first two prompts are verbatim MT-Bench writing-category questions; whether all
eight are verbatim from that set was **not verified** `[unverified]` and does not affect the
conclusion, which rests on shape rather than provenance.

**Promotion candidate (procedural).** Stated without naming this project: *before reusing a shipped
benchmark request set, read its inputs and characterise their shape against the effect you intend to
measure — a set can be a valid regression baseline while being structurally unable to exercise the
mechanism under study, and its name may describe the source corpus rather than how it is driven.*

## Pointers

- `milestones/M2-tiering-cost-model.md` § "What `mtbench8` is, and what it cannot be used for".
- Related: [[agentic-kv-trace-datasets]] (Mooncake `hash_ids`, conversation ~40% / tool&agent ~59%
  prefix-cache ratios), [[check-the-branch-tip-before-baselining]],
  [[negative-control-configs-silently-degrade-to-pass]] (sibling shape: a check that cannot fail).
