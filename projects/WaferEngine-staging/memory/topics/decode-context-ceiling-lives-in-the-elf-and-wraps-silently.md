---
summary: How long a sequence the pr14 decode can actually hold — and the wall that wraps silently — 2026-07-30
tags: [WaferEngine-staging, drained-inbox, 2026-07-30]
---

# How long a sequence the pr14 decode can actually hold — and the wall that wraps silently — 2026-07-30

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-30

Source: `memory/inbox/2026-07-30-decode-context-ceiling-lives-in-the-elf-and-wraps-silently.md`

# How long a sequence the pr14 decode can actually hold — and the wall that wraps silently — 2026-07-30

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are planning a sweep that pushes context past a few thousand tokens (an
`f(pos)` cost curve, a capacity study, a long-prompt workload) and you need to
know: what does the compiled artifact hold, what does a recompile buy, and where
does it actually break?

Also relevant if you are about to quote one of the two sequence-length limits the
durable docs carry — because neither binds on this line any more.

## What the compiled artifact holds: 20,480

```
MAX_SEQ_LEN(decode) = MAX_OUTPUT_LEN = 20,480
```

**Not** `MAX_INPUT_LEN + MAX_OUTPUT_LEN`. The `8k` in the config name never
reaches decode at all: the orchestrator sends prefill ← `MAX_INPUT_LEN` and
decode ← `MAX_OUTPUT_LEN` (`launch.py:303-308`). `kv_len_per_pe =
MAX_SEQ_LEN / P_BLOCK_SIZE = 80` is baked into the ELF, so **context capacity is
a property of the artifact, not a runtime parameter**.

| range | needs |
|---|---|
| 256 … **20,480** | nothing — the current M2 artifact. A sweep to 16,384 needs **no recompile** |
| 20,480 … **32,512** | decode-only recompile (~4.5 min), +3,948 B/PE. With an 8k prompt the generation budget goes 12,288 → **24,320** |
| ≥ **32,768** | hard wall |

Best value if more room is wanted: keep `MAX_INPUT_LEN 8192` (prefill artifact
untouched — the one already device-validated) and lift `MAX_OUTPUT_LEN` to
32,512 = 127 × 256.

## The wall at 32,768 — three things, two of them silent, none guarded

They coincide only because `P_BLOCK_SIZE = 256`; change that and they separate.

| where | why | how it fails |
|---|---|---|
| `decode.csl:1140` | `.stride = @as(i8, kv_len_per_pe)` — the memory-DSD stride field is **8-bit signed** and `kv_len_per_pe` is comptime ⇒ needs ≤ 127 | likely a **compile error** (the one that fires first, and loudly) |
| `decode.csl:269` | `n_steps = kv_len_per_pe * P_BLOCK_SIZE - input_len_rt`, both operands i16 — and that product **is** `MAX_SEQ_LEN` | **silent wrap** to −32,768 |
| `decode.csl:1129-1130` | absolute position `pos` is i16 | **silent wrap** |

`launch_decode.py` asserts divisibility and prefill range but **never asserts
`max_seq_len ≤ 32767`**. Same family as the prefill `kv_mux batch:u16` overflow,
just sitting at 32,768 instead of 1,170. A one-line guard is worth adding
whether or not anyone goes there.

**And: this 20,480 artifact has never been exercised past ~3,407 tokens**
(`mtbench8` round 6: 25 prompt + 3,382 generated). A sweep to 16,384 runs it 5×
further than it has ever been — treat first-run failures at depth as expected,
not as a regression.

**SRAM is not the decode-side binder.** The PEs whose footprint grows with
context have ~25 KB headroom; the tight ones — HT_head `W_E_tile` and HT_tail
`lm_head_tile`, 19,008 B each — **do not grow with context** at all.

## Two documented constraints that do not bind on this line

Both are carried in the durable docs and appear in ≥7 files here, so they get
re-quoted. *[code-derived from the pr14 tree, not device-verified.]*

- **"pdSeparate `kv_mux batch:u16` overflows at ≳1,170 tokens"** — structurally
  fixed. The varlen colmux splits the quantity that used to overflow into a
  **comptime** `kv_seg_len = Pw · max_layers · kv_cols · reduce_len = 8192` and a
  **runtime segment count**; `max_n_chunks` cancels out, so the surviving u16
  counts *segments*, not wavelets. That is ~8192× looser ⇒ ~16.7M tokens.
- **"single-pass prefill caps at ~512 tokens"** — that was the staging 2×2 /
  7-layer layout. On pr14 `CHUNK_SIZE = 256` gives `chunk_len_per_pe = 1`, so the
  quadratic score/mask term is a verified constant (2 elements) and the mechanism
  is gone. pr14 prefill's real wall is **HT_head per-PE SRAM**: two `we_buf` at
  18,994 B each = 37.1 KB.

## Implications / next actions

- [ ] Add `assert max_seq_len <= 32767` to `launch_decode.py` (after the M2-S2
      merge, so it does not disturb the fingerprint gate mid-flight).
- [ ] When the maintain pass next touches [[kv-cache-policy-tradeoffs]],
      [[pr14-real-serving-port-contract]] and `project.md`, scope the two
      constraints above to the staging line rather than deleting them — both are
      still true where they came from.

## Pointers

- `models/qwen3_1p7b-e2e-pdSeparate` on the pr14 line; worktree
  `/home/lexu/we-m2bench` (line numbers are working-tree, and drift vs `a3a509c`
  in the six files M2-S1/S2 touched).
- `milestones/M2-tiering-cost-model.md` § S3a; `milestones/M3-idle-pe-tier.md`.
- Related: [[e2e-pdSeparate-device-validation]], [[s6a-prefill-warm-start]].
