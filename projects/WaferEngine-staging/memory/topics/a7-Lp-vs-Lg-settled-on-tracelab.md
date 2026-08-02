---
summary: A7 (L_g >> L_p) is FALSIFIED on TraceLab — 665k real Claude Code/Codex rounds, uncapped output, L_p = 99.7% of tokens. Supersedes both the Mooncake-based falsification and its withdrawal.
tags: [waferengine-staging, m2, a7, workload, datasets, tracelab, mooncake]
---

# A7 settled: coding agents are prompt-dominant, on a dataset that can actually show otherwise

**A7** = "`L_g ≫ L_p` in the scenarios that matter". It was load-bearing: it was the stated reason
S3b (decode-side KV egress) was promoted from *conditional* to *prerequisite*.

## The arc — three states in one day, keep all three

1. **Falsified on Mooncake** (`L_p` = 97.2 / 97.9% of tokens, 99.9% of requests have `L_p > L_g`).
2. **Withdrawn.** Le pushed back: Mooncake is a *KV-cache paper's* trace, so long prefixes may be
   selection bias. Checking the field settled it — **`output_length` is hard-capped at 2,000** in both
   traces (max exactly 2,000, 1,021 distinct values, 30 requests at max, mean 182/343). A reasoning
   model routinely exceeds that; our own S30 runs generated **19,968 tokens, 10× the entire cap**.
   Mooncake is also Kimi production traffic from before reasoning models were widespread. ⇒ The trace
   is **structurally incapable** of showing long generation. The falsification rested on a capped field
   and was correctly retracted.
3. **Falsified again, properly, on TraceLab.** ⇐ current state.

## The measurement

**TraceLab** (`github.com/uw-syfi/TraceLab`, release v0.0.2 `syfi_coding_trace.jsonl.gz`, 97 MB,
gzip-verified): **665,453 rounds, 8,058 sessions**, real **Claude Code + Codex** usage
(gpt-5.5, claude-opus-4-8, claude-opus-4-7, gpt-5.6-sol).

**First, the cap check that killed Mooncake — TraceLab passes it:** `output_tokens` max **64,000**,
9,570 distinct values, only 6 rounds at max, **6.0% of rounds exceed 2,000** (impossible in Mooncake)
and 2,480 exceed 8,192. Not truncated.

| | Mooncake (capped) | **TraceLab (uncapped)** | our S30 (noise prompts) |
|---|---|---|---|
| `L_p` share of all tokens | 97.2–97.9% | **99.7%** | 17.2% |
| rounds with `L_g > L_p` | 0.1% | **12 / 665,453 = 0.002%** | 19/22 |

Input **mean 171,576 / median 132,092** tokens; output **mean 589 / median 249**.

**Thinking is real but small in aggregate.** 37.8% of all rounds have non-zero
`reasoning_output_tokens` (mean 197, median 42, **max 25,280** — individual rounds can be huge), but
reasoning is only **12.7% of all output tokens**, and output is 0.3% of all tokens.

⇒ **A7 is FALSIFIED.** Coding agents are prompt-dominant — more extremely than Mooncake suggested, on
a dataset that could have shown the opposite and did not.

## What follows, and what does not

- The 99.7% is **prompt** KV, and the host already retains a copy of it (**A6, verified in code**:
  `launch.py:405-431` writes `inj_{i}.npz` and never deletes it). So the reload lane — already measured,
  338.3 ms at `L = 8192` — covers the overwhelming majority of KV by volume.
- **S3b's promotion to prerequisite loses its stated basis.** It is not thereby dead: decode-produced KV
  is still the *only* KV with no host copy, so any cross-turn retention scheme accumulates exactly the
  bytes S3b would move. That is an architecture argument, not a volume argument — **Le's call, not
  mine.** See [[e9-forced-segment-tsc]] for the adjacent work.
- ⚠️ **Scale gap worth its own line:** TraceLab's *mean* input is **171,576 tokens** against our
  compiled `MAX_INPUT_LEN = 8192` and total context ceiling **20,480** — more than an order of
  magnitude. Any claim that this engine addresses coding-agent serving has to confront that first.

## Method note

Two datasets, two opposite artifacts, both fatal if used alone: Mooncake's **output cap** inflates
`L_p` share; our S30's **nonsense prompts** make the model loop to the budget and inflate `L_g` share.
**Before trusting any published trace, check its length fields for a cap** — max value, distinct-value
count, and how many records sit exactly at the max. It cost two wrong conclusions to learn here.

## Last updated

2026-07-31
