---
summary: A meta slot repurposed from pad → meaning, with a second host writer left on the old contract (`qwen3_1p7b-e2e`, PR #14)
tags: [WaferEngine-staging, drained-inbox, 2026-07-31]
---

# A meta slot repurposed from pad → meaning, with a second host writer left on the old contract (`qwen3_1p7b-e2e`, PR #14)

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-31

Source: `memory/inbox/2026-07-31-repurposed-meta-slot-left-a-second-writer-on-the-old-contract.md`

# A meta slot repurposed from pad → meaning, with a second host writer left on the old contract (`qwen3_1p7b-e2e`, PR #14)

Date: 2026-07-31 · Repo: `WaferEngine-staging` · PR: WaferAGI/WaferEngine #14 (`real_qwen3_1p7`), head `d8bdc38`

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## Situation

Reviewing PR #14 before merge. The symptom you would be staring at if you hit this
cold: **`models/qwen3_1p7b-e2e` on its DEFAULT sim config produces wrong decode
numerics with no error and no hang** — the device is told to emit 33 steps through a
port built for 25, attention never sees the prefill KV that is sitting in the cache,
and every decode token is RoPE-rotated for position `step` instead of `n + step`.
Nothing in the failure names the metainfo tile.

## What is wrong

PR #14 repurposes **slot 1 of the KV-ingress metainfo tile from *pad* to *the absolute
prompt length `n`*** (the "P3.2" change). The tile is now `[ceil(n/P_BLOCK_SIZE), n]`
(`src/decode/decode.csl:76-82`, peeled at `:1602-1603`).

`launch.py` defines `_repack_kv_band` **twice**:

| writer | line | slot 1 | |
|---|---|---|---|
| real serving path | `launch.py:3976`, `:3987` | `n_abs` | correct |
| co-resident smoke path | `launch.py:4312`, `:4317` | literal **`0`** | **wrong** |

The smoke copy's own comment names the cause: *"Inlined verbatim from
`qwen3_1p7b-decode/launch.py::_repack_kv_band`"* — a sibling model whose slot 1 **is
still pad**. The inlining copied the older contract along with the layout.

**Reachable on the default path, not an exotic corner.** The bad branch is gated by
`if not kv_transfer:`, and `KV_TRANSFER` is read as `cfg.get("KV_TRANSFER", 0)` at
`launch.py:704 / :3219 / :4137` — it **defaults to 0**. `test_sim_2x2blk.json` has no
`KV_TRANSFER` key at all and is `run_sim.sh:10`'s default. Also affects
`test_sim_2x2_p2048d8192`, `test_sim_2x2_p3072d16384`, `test_sim_2x2_toy`,
`test_sim_2x2blk_m1`.

## Why it stayed hidden — a stale comment describing the old contract

`decode.csl:1587` still reads:

```
const KV_META_LEN: i16 = 2;   // ... slot 0 = prefill, slot 1 = pad.
```

Slot 1 has not been pad since this PR. **This line is very likely why the second
writer was missed.** Fix the comment in the same change as the code.

## Consequences of `input_len_rt = 0` (worked on `test_sim_2x2blk`: P_BLOCK_SIZE 8, MAX_SEQ_LEN 32, PREFILL_LEN 16)

| # | site | intended | actual |
|---|---|---|---|
| 1 | `decode.csl:269` `n_steps = kv_len_per_pe*P − input_len_rt` | 16 → **17 steps** emitted vs a **25**-step port | 32 → **33 steps** — **overruns by 8** |
| 2 | `decode.csl:277-283` `seed_iter` | 2 (prefill KV attended) | **0** — prefix never attended, and the first decode token's `process_kv` writes over prefill KV at cache row 0 |
| 3 | `decode.csl:703-713` RoPE seed | position 16 | position **0** — wrong numerics, no error |
| 4 | `decode.csl:1171` `pos = input_len_rt + step` | 16+step | step — **harmless while `n` is block-aligned** (`16 % 8 == 0` → same owner PE); breaks on a sub-block prompt, i.e. exactly the case P3.2 exists to support |

Consequence 1 is pure arithmetic and does not balance regardless of runtime behaviour —
that is the part to lead with when convincing someone.

## Evidence status — read before quoting

**Static analysis only. NOT reproduced on the simulator.** The evidence chain and the
arithmetic were re-derived independently from source and config values so it can be
checked without a run, but no run confirms it. Confirmation is cheap:
`cd models/qwen3_1p7b-e2e && ./run_sim.sh` (then `rm -rf out_*/simfab_traces` — tens of
GB). Prediction before the fix: 33 steps against a 25-step port, `iter_num` starts at 0,
RoPE seeded at 0. After: 17 / 2 / 16.

## Fix (one line + one comment)

Give the smoke copy the serving copy's signature and slot-1 value, and pass the absolute
length at `launch.py:4335` — it is already in scope (`build_decode` binds `prefill_len`
at `:308` and returns `dict(locals())` at `:2475`, so `dd["prefill_len"]` sits next to
the `dd["prefill_len_per_pe"]` already unpacked at `:4298`). Then fix `decode.csl:1587`.
Worth considering separately: **collapse the two `_repack_kv_band` copies** — they differ
only in payload source and this one field, so this class of drift is structural.

## Scope

- `models/qwen3_1p7b-e2e-pdSeparate/launch_decode.py:183` writes `[prefill_len_per_pe,
  n_abs]` correctly ⇒ **pdSeparate is unaffected**, including everything M2 measures.
- Base commit `fcfc8c1` has no `KV_META_LEN` in `decode.csl` at all ⇒ **new in PR #14**,
  specific to `qwen3_1p7b-e2e`.

## What generalizes

- When a field changes from *pad* to *meaning*, the compiler cannot help — **grep every
  writer, not just the one you are editing**, and update the comment that states the old
  contract in the same commit. Same family as the known decode lesson that widening
  metainfo cascades to every hardcoded width and size-assert.
- **A helper "inlined verbatim" from a sibling model carries that sibling's contract
  version.** The provenance comment that looks like documentation is the bug report.

## Also surfaced by the same review (secondary, not chased)

One `results.json` blob (`e947cec`) is committed under **three** model dirs whose
`request.json` files declare **three different configs** (one a 2×2 geometry), so a
brand-new model ships a PASS verdict and timings it did not produce. Mechanism:
`launch.py:450-452` writes run output straight into the git-tracked
`request_config/<test>/` dir and the per-model `.gitignore`s do not cover
`results.json` / `timing.json` / `device_verdict.json` — so committing them is the
path of least resistance after every device run. Four ignore rules fix it. Related to
[[a-quoted-number-is-not-a-measured-number]] and
[[prove-same-source-before-comparing-timings]], but this is the *why it keeps
happening*.

## Pointers

- Full write-up prepared for the PR author: `docs/analysis/pr14-e2e-kv-meta-slot1-bug.md`
- Topic: `memory/topics/pr14-real-serving-port-contract.md`
- Related: `memory/inbox/2026-07-30-decode-context-ceiling-lives-in-the-elf-and-wraps-silently.md`
  (same `decode.csl:269` line, different failure — i16 wrap at 32,512)
