# Adopting the pdSeparate kernel: the KV contract changes shape, and the two KV transforms are NOT interchangeable

Date: 2026-07-21 · Repo: `nc_service` · Branch: `lexu/pdsep-kernel-adopt` (nothing merged; kernel not ready)

**Project:** nc_service
**Author:** claude
**Status:** captured

## Situation

We are moving the framework onto the kernel form delivered by WaferEngine PR#14
(`qwen3_1p7b-e2e-pdSeparate`) / the PR#12 `csl-kernel` mock bundle. The question
that gates everything: can our existing KV off-chip transform drive this kernel,
or does adopting it change the KV contract? Symptom to watch for if you get this
wrong: attention is garbage because ~half the KV lands in the wrong positions.

## PR#14/#12 is mode-A serving — there is NO internal rewind

The latest PD-separate kernel is **compile-once / load-many, one distinct prompt
per round**. It does not do mode-B spec-dec rewind:
- KV meta tile: only `slot0` (prefill_len) is used; **`slot1` is pad** (`decode.csl`
  writes `slot 0 = prefill, slot 1 = pad`; kernel only reads `kv_meta_buf[0]`).
  Our old `kv_transform.repack_continuation_band` depended on slot1 = accepted
  position A as a continuation gate — **that gate does not exist here**.
- `ht_tail` does emit a spec accept/reject trimmed record, but the accepted count
  is **not fed back to rewind KV** — the KV/continuation side is absent.
- The rewind kernel still lives only in WaferEngine `lexu/decode-rewind`; PR#14/#13
  do not have it. So adopting this kernel is not "add rewind" — it is "the KV
  contract wholesale changed shape."

Contract deltas vs our current framework (mode-B): decode position placement goes
from token-interleaved (`p=seq_local*P+local_py`) to **chunk-major contiguous**;
KV band goes from full/MAX-pad to **VARLEN** (`input_len_override`, `row_u32 = Pw +
C_kv*plen`, no pad); meta slot1 accepted-position → pad; serve loop → compile-once
load-many.

## The decisive finding: our `kv_transform.py` and PR#12 `kv_bridge.py` are not interchangeable

Both do prefill-egress → decode-ingress and share the feature-transpose direction
(prefill row = feature → decode column; V transposed to [pos,feature]). But they
come from **different decode kernels**, so the position placement differs:
- ours (strided): decode `p = seq_local*P + local_py` — a true cross-PE
  round-robin redistribution (from decode.csl `iter_num`).
- PR#12 (chunk-major): keeps prefill's position→PE assignment, only reorders slots
  `chunk*reduce_len + s` contiguously.

**Offline diff (small 2×2 fabric, plen_per_pe=4): both write to the identical cell
positions, but only 96/192 seeded values match — ~50% of KV values land at the
wrong source position.** So feeding PR#12's kernel with our strided transform seeds
half the KV wrong → attention wrong.

**Decision (for the real-kernel path): REPLACE, do not relabel/branch.** The
real-kernel path must use chunk-major `kv_bridge` logic; keep our strided
`kv_transform` only for the mode-B rewind kernel (a different kernel/layout). The
framework must fork these two explicitly. The compare script is in scratchpad
(`kv_xform_compare.py`) and is worth freezing as a regression test.

Also note PR#12 `kv_bridge` is bsz==1 only and rounds `ceil(prompt_len/P)` (allows
non-integer-block prefill); our transform supports `bsz_pf != bsz_dec` and forces
`prefill_len % P == 0`.
