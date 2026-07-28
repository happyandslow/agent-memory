---
date: 2026-07-28
project: WaferEngine-staging
tags: [measurement, methodology, reproducibility, timing, bandwidth, m2]
---

# Prove same-source before comparing timings; derive the payload, never assume it

Captured during M2-S0 (pdSeparate `mtbench8` baseline reproduction on real WSE-3,
snapshot `a3a509c`). Two methodology points that generalise well past this milestone.

## 1. A whole-run content hash turns a timing comparison into a controlled experiment

Before comparing any number to a recorded baseline, establish that both runs computed the
**same thing**. pdSeparate's `device_verdict.json` already carries a `trace_sha256` over all
8 requests' prompt ids, prefill top-k bits/ids, and decode sampled ids. Ours matched the
reference exactly, from an **independently compiled artifact** — so every per-token divisor
was provably identical and the remaining deltas were timing and nothing else.

That single check is what let the result be stated crisply: of 242 leaf fields, every
device-side field reproduced to ≤0.02% and **all** deviation was host-side. Without it,
"654.954 vs 654.954" would still have been open to "maybe it generated different tokens".

Corollary worth remembering: **a checked-in golden file is not a gate unless something reads
it.** `launch.py` never opens `golden_token_ids_*.json`; the verdict's own checks are
structural. Assume nothing is enforced until you find the line that enforces it.

## 2. A bandwidth number is only as good as its divisor's provenance

The project had been quoting "~1.3–1.5 GB/s" for host KV egress, derived by dividing a
measured time by an **assumed** payload ("one 256-token chunk ≈ 29–34 MB"). Reading the
receive-loop sizing expression and resolving every symbol against the config gave the exact
figure — **33,554,432 B**, a constant for any prompt ≤256 tokens — and with it a real number,
1.426 GB/s.

The magnitude survived, but the derivation exposed two structural facts the assumption had
hidden: the wire carries **8/7 × `B_tok`** at every `L` (32 emitted layer slots for 28 real
layers), and a further `256/L` below one chunk. Together, 9.75× more bytes than useful KV on
this workload. Any cost model using `B_tok` as the transport size understates it by 14%
permanently.

*General lesson:* when a derived quantity is load-bearing, derive its **numerator and
denominator separately** and label which is measured. A right-magnitude number reached by a
wrong route will keep hiding whatever the wrong route obscured — here, a permanent 14%
padding factor that sits directly in the recompute-vs-offload decision.

## 3. Check what a "0.72 s" style anchor actually spans

The recorded "KV handoff 0.72 s/prompt, of which 69.5 ms disk load + 29.5 ms repack" was
wrong twice over: the two components belong to a **different stage** than the 0.72 s (they
sum to ~0.099 s, decode's own handoff, while the 0.72 s is the orchestrator's npz round
trip), and the 0.72 s **did not reproduce** — we measured 0.058 s twice, 1.3% apart. When a
row reads "X, of which a + b", verify a and b are inside X.

See [[m2-s0-baseline-and-timer-provenance]] for the full findings and the operational notes.
