# The 4B decoder, re-laid out, outruns the native prefill kernel — 2026-09-07

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## The situation this applies to

You are asking whether a CS-3 can serve prefill at all, or whether the decoder
is only good for decode and prefill has to go elsewhere. Earlier in this
programme the answer was clearly no: forced decode reached 0.43–0.45× of the
dedicated prefill kernel, and everything better was analytical.

## Finding — the answer flipped, and it is measured at every rung

All device-measured, forced production, 2K context, byte-identical or
oracle-gated. **tok/s at 0.85 GHz** (Le's convention as of 2026-09-07; cycles
are the measurement, multiply an old 750 MHz figure by 1.133).

| configuration | cycles/token | tok/s | vs native prefill |
|---|--:|--:|--:|
| native prefill kernel (8,192 and 4×2,048 chunks) | — | 10,544–11,143 | 1× |
| forced decode, rows as stages | 177,539 | 4,786 | 0.43–0.45× |
| forced decode, ATTN \| FFN split | 101,670 | 8,360 | 0.75–0.79× |
| L = 4 (9 rows × 256×128, 4 layers/block) | 48,872 | 17,392 | **1.56–1.65×** |
| L = 2 (18 rows × 256×64) | 27,348 | 31,081 | **2.79–2.95×** |
| L = 1 (36 rows × 256×32, 72 stages) | 17,771 | 47,831 | **4.29–4.54×** |

**The decoder passes the dedicated prefill kernel at L = 4 and is 4.3–4.5×
past it at L = 1.** Ratios are ratios of cycle counts and therefore
clock-independent; only the absolute rates move with the clock.

And it holds across context once the KV stride cap is lifted — L = 1 measured
at four depths fits `cycles/token = 12,225 + 3.626 × context` at R² = 0.99999,
staying **1.41–1.49× native prefill even at 11,508 mean context**.

## Conditions and caveats a future decision must carry

- Native prefill was measured on **chunks** (8,192, and 4 × 2,048), so it is
  the honest baseline for chunked prefill, not for one long sequence.
- The comparison is single-request throughput on one wafer. Batch > 1 raises
  aggregate throughput only — the kernel handles one query position per batch
  element, so it says nothing about a single request's rate.
- **The vanilla-A baseline is tree-dependent and currently unexplained.** A's
  on-chip ceiling was measured at 29,184 on an earlier tree; A no longer
  compiles at that context in the current lineage, and the *unpatched* tree
  fails identically, so footprint grew somewhere between them. This tree's A
  ceiling is 26,112. **Anyone quoting an A number should locate that lineage
  change first** — 29,184 appears in many places and will otherwise propagate
  as current.

## Implications / next actions

- [ ] Find where the B′ lineage added footprint, before any A number is used
      in a comparison.

## Pointers

- `docs/reports/2026-09-04-4b-wide-layer-session-report.md` Rounds 112, 116,
  118, 119
- `demo/qwen3-4b-thin-stage/l4/status.md`, `.../stride-lift/status.md`
