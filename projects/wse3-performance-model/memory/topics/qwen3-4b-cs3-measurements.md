# Qwen3-4B CS-3 measurements

- CS-3 measurements pinned decode step cost, batch scaling, phase breakdown, forced-prefill rates, and stage-cut opportunities. Use raw cycles and 750 MHz calibration unless a specific artifact states otherwise.
- Decode step cost vs context is approximately 680,741 + 16.07 cycles/token, and current forced-decode row timing is ATTN ~127K + FFN ~50K cycles/token.
- 4B bsz>1 required experiment-only scratch fixes; stage pipelining is a stronger multiplier than raw batch scaling. Eight-stage forced prefill measured 7,373 tok/s at 2K and 6,326 tok/s at 8K after tail-colour race handling.
- Softmax is the dominant phase/context slope; exact pass fusion was byte-identical but slower, so the lever is DSD overhead/exp kernel/online softmax rather than naive pass fusion.

## 2026-09-08 maintain update — thin-block / vertical-stacking measurements

Source: `inbox/2026-09-06-thin-block-sublinear.md`, pointing to
`docs/reports/2026-09-04-4b-wide-layer-session-report.md` and named remote
artifacts under `/home/lexu/build/4b-l4/code/bprime-snapshot`.

- Thin 256-wide stage rungs measured on CS-3 show per-layer time is strongly
  sublinear in allocated PE count: full-square A is 7,377 tok/s at ~29K context;
  L=4 is 15,346 tok/s at 16K; L=2 is 27,424 tok/s at 8K; L=1 is 42,203 tok/s
  at 4K before lifting the stride cap. `tok/s × context` stays roughly
  constant, so thinning is a benchmark/context tradeoff rather than a free
  deployment throughput axis.
- The former 127-position K-cache descriptor cap was lifted by replacing the
  i8 strided descriptor in `process_kv` with scalar `kv_cols` stores. The
  patched kernel stayed byte-identical for 1,000 device records on free and
  forced paths, added only ~0.05% cycles/token, and raised the L=1 ceiling from
  4,064 to 12,032 tokens; unpatched CSL fails to compile at `kv_len_per_pe=136`.
- Capacity model now used for the thin rungs: per-PE context bytes =
  `16 × (context ÷ rows) × (L + 2)`. The model predicted 11,520 tokens before
  the measured 12,032 L=1 ceiling; remaining post-lift ceilings for L=2/L=4 and
  stacked variants still need their own compile/measurement.
- Vertical role stacking (ATTN above FFN in one block column) works in sim and
  compiled/measured on silicon with six bands of ATTN 256×128 / FFN 256×64:
  12,201.9 cycles/token at 2K, final-record top-k args/values bitwise equal to
  free reference. The key layout enabler is changing K-pipe fold from cyclic to
  block so the same pipe carries the same contiguous dimension slice across
  unequal band heights.
- Open follow-ups from the capture: diagnose the A1 stall; decide whether to
  build/measure the second stacked lane; scope the 128² two-lane width-axis
  family. A valid capacity sweep must prefill to each tested live context,
  because per-token cost tracks `iter_num`, not `MAX_SEQ_LEN`.

## 2026-09-14 update — corrected fabric constants, per-stage layout C, width axis

Source: `inbox/2026-09-14-layoutc-3p7x-is-one-sync-barrier-not-compute.md`,
`inbox/2026-09-14-fused-block-fits-sparse-cache-and-trace-placement.md`.

- **"13.0 cyc/word CE bulk DSD" is a store-and-forward relay artefact** (a PE that
  receives AND re-emits), not a receive ceiling. Pure receive, and `@fmachs`
  consuming a fabin DSD directly as its streamed operand ("moving is computing",
  compiles and runs on WSE-3, not used in production decode.csl), measure
  **~1.17 cyc/word at N≥128** (simfab; R3 pattern; 384 words ≈ 451 cyc). Keep
  13 only for actual CE relays. Double-buffered async receive is the *slowest*
  strategy at these sizes.
- **Scatter placement of collective participants costs a fixed ~+24 cyc**, not a
  per-hop multiple (simfab, same 16 participants contiguous vs 1-in-4 over 8×8;
  +6 % at L=16, +0.7 % at L=256). A reduce hop is dominated by the receiving
  participant's instruction; pass-through routing is ~2 cyc/hop. Third
  independent confirmation (with the height ladder and the width data) that the
  kernel is per-participant-latency bound, not chain-length bound.
- **Per-layer per-token slots, 256×256 blocks, 2K (4b-wide-layer phase-TSC):**
  ATTN 11,886 (QKV ≈3,452 + attn+O ≈8,434), FFN 5,802; T_attn/T_ffn 2.05 →
  ≈2.7 at 8K. Blocks alternate (one idle); pipelining them measured 1.47×/1.40×.
- **Layout C per-stage, CS-3 (`docs/reports/2026-09-14-tall-per-stage-timing.md`):**
  at 128-wide, attn+O 0.91–0.96× of the 256-wide slot, QKV 1.22–1.35×, FFN 1.51×;
  the 3.7× is 46.6 % one `round_barrier` (35,536 cyc, context-independent) —
  see the inbox note. **Width axis: a narrow block costs context, not time.**
- Per-PE MAC counts do not predict time here in either axis; do not use them.
