# Cerebras-draft <-> NVIDIA-verify bridging: what is still open, and what the M2 measurement closed

Date: 2026-08-02 · Repo: `nc_service` (branch `lexu/pdsep-kernel-integration`)

**Project:** nc_service
**Author:** claude
**Status:** captured

## Why this note

Audit of the bridging task's open items and of whether prior conclusions had actually
reached ContextBase and agent-memory. One item had been answered by measurement but never
written back to the collaboration doc, so the doc still asked SGLang a question we could
already answer ourselves.

## The tracking doc is the collaboration page, not the 2026-06-13 sync

Two ContextBase pages carry "Cerebras draft + NVIDIA verify" in their scope and they are
NOT interchangeable:

- **`Draft distribution on the wire: what SGLang would need to change (proto side-by-side)`**
  (`auqlHBw1Sg`, owner Le Xu) -- the live tracking doc for the *interop / protocol* task.
  Section 6 is the open-questions list. **This is the one to send.**
- `2026-06-13 Cerebras Draft + NVIDIA Verify Progress Sync` (`hagNcRNc2e`, owner Luo Mai,
  last touched 2026-06-16) -- about the draft *model* (layer count, FFN ratio, acceptance,
  KV policy), not the bridge. Stale by ~7 weeks. Do not update it as if it were ours.

A number in that older doc is worth flagging rather than quietly contradicting: it puts a
K=16 draft proposal at **4.57 ms** from a claimed 3500 tok/s. Our measured device forward
span at k=16 is **12.72 ms**. Different kernels -- that doc describes a *20-layer* reshaped
draft, ours is the 28-layer `qwen3_1p7b-sd-pdSeparate`. Not a contradiction, but anyone
comparing the two without noticing the layer count will think one of them is wrong.

## What the M2 measurement closed (was NOT synced; now is)

Section 6 item 2 asked SGLang "is `draft_len=16` acceptable given the accept-rate /
latency tradeoff on your side?" -- but our half of that question was answered on
2026-07-29 and never written back. Now recorded in the doc:

**Our answer: yes, and 16 is actively our preferred point.** k=4 vs k=16, same artifact, no
recompile, 61 clean rounds each: the round costs +9.13 ms at k=16 and essentially ALL of it
is device time (host overhead +0.46, transport +0.39, wire +0.14). Fixed per-round cost is
~11.3 ms regardless of k, so 4x the tokens amortises it: per draft token 5.20 -> 1.87 ms
end to end (2.8x cheaper); at 25/32 acceptance, 198 -> 451 tok/s.

Also added, because it pre-empts the obvious next ask: **`MAX_DRAFT_LEN == 16` is a hard
kernel assertion** (`launch_decode.py:258`), not a config default. k=32 needs WaferEngine
kernel work, and extrapolation says it only buys ~1.5x over k=16.

## Still genuinely open -- all need an SGLang-side answer

1. **Concurrency shape (the real blocker).** Their `batch_advance` fans out with
   `join_all`; `InFlightGuard` only guards the same `request_id`. We are strictly
   one-exchange-in-flight end to end (`ExchangePump`, the kernel's sequential `serve_loop`,
   our `Queue(maxsize=1)`). **Any batch size > 1 collides before any distribution work
   matters.** This has been open since 2026-07-28 and is the item to push on.
2. Does `tree_speculative_sampling_target_only` consume `draft_probs` when non-zero?
   Unanswerable from outside; if it ignores them, the change is a new kernel, not a
   populated tensor.
3. Is distribution-preserving sampling wanted at all? Their call.
4. Multi-request lifecycle: long-lived pool vs per-request session model.

## Sync state after this audit

- ContextBase `auqlHBw1Sg`: draft_len answered, MAX_DRAFT_LEN ceiling added, status line
  updated to "5 of 6 awaiting SGLang". **Editing gotcha: a markdown TABLE inside a numbered
  list item truncated the document** -- items 3-5 of section 6 vanished on save and had to
  be restored. Keep tables out of list items in ContextBase; use prose.
- agent-memory: the stale open item in
  [[2026-07-28-m1-complete-bridge-architecture-index]] ("blocked on SGLang: batch size and
  draft_len 4 vs 16") is now half-resolved -- only batch size remains.
- M2 latency work itself was already synced (2026-07-29 inbox note + ContextBase
  *M2 delivered*).

## Pointers

- ContextBase tracking doc: https://context.ed-aisys.com/doc/draft-distribution-on-the-wire-what-sglang-would-need-to-change-proto-side-by-side-auqlHBw1Sg
- Related: [[2026-07-28-sglang-already-speaks-our-protocol]],
  [[2026-07-28-m1-complete-bridge-architecture-index]],
  [[2026-07-29-m2-device-bringup-and-the-ingress-blocker]]
