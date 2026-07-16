# KV-management abstraction across the three decode variants — 2026-07-13

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained   <!-- captured | drained -->

> Details of the pre-S6 KV-management-abstraction design session (GOALS §7 item).
> Decisions + links already live in the durable docs (source of truth):
> `milestones/M0-reuse-foundation.md § S6` + Verification log 2026-07-13; `GOALS.md §7`
> (abstraction item = answered); `PROGRESS.md` cursor. This note holds the evidence detail.
> Related: [[standalone-vs-integrated-kernel-parity]], [[pr14-real-serving-port-contract]],
> [[e2e-kernel-dataflow-and-topology]], [[kv-cache-policy-tradeoffs]].

## What happened / finding

Design-only session, five read-only subagent digs on staging HEAD + direct `diff`/`wc`
verification (no appliance run; cluster down). Question: is the KV compute/lifecycle across the
three decode variants (standalone `qwen3_1p7b-decode` / e2e / pdSeparate) shared enough to factor
into a reusable CSL module (transport stays per-variant), and where should S6's retain logic land?

**1. "KV compute basically the same" — CONFIRMED, but it's two lineages, not three variants.**
- After naming normalization, every KV-touching compute fn is identical: `process_kv` (append at
  `iter_num`, owner-gate `local_py==step%P_BLOCK_SIZE`, `iter_num+=1`) is **byte-identical modulo
  naming** (standalone `decode.csl:1121` ≈ e2e `:968`); attention reads (`score_matvec_mult`/
  `output_matvec_mult`), `iter_num_bank`/`step_bank` load+store, `set_layer`, RoPE apply+advance,
  cache allocation — all identical modulo naming. No KV-*semantic* difference in the compute core.
- **Direct diff:** e2e vs pdSeparate `decode.csl` differ by **83 lines, all a WIP TSC profiler**;
  compute (incl. the on-wafer `kv_ingress_phase` north-shift receiver) is byte-identical. So the
  e2e-vs-pdSeparate KV difference is **entirely off-chip** (host feeder `kv_adaptor`/`kv_demux` vs
  on-wafer relay wiring), NOT a decode-kernel difference. This *refines* (does not falsify) GOALS
  §2.3's system-level "on-chip relay vs host-DRAM bridge" framing — it's true at system level,
  just not a decode-kernel-level distinction. **Standalone is the sole divergent lineage** (own
  naming `kv_cols`/`kv_len_per_pe`/`attn_per_pe`; own multi-round lifecycle; fp32 softmax + fast
  rsqrt vs integrated bf16).

**2. Divergences beyond naming (all KV-neutral for retain except lifecycle-presence).**
Numerics (softmax f32 vs bf16; score-alpha precision; RMSNorm/QK-Norm fast-rsqrt Newton vs
soft-float `1.0/sqrt`; `recip_f32` helper standalone-only); GQA head-dim-pad (`attn_per_pe`≠
`dim_per_pe` in standalone, collapsed in integrated — low KV-relevance, cache keys off
`kv_cols`==`kv_dim_per_pe`); bank-seed site (integrated inlines in `init_task`, standalone factors
into `round_reset`); on-device vs host `n_steps` sourcing; EOS/result-header/re-arm tasks.
**No `KV_TRANSFER`/`kv_stream_ingress` branch in the compute body** in either kernel — transport
mode branches live only in lifecycle glue.

**3. Retain migration to integrated is NOT mechanical (Q3/Q4).**
- Retain touches **counters+RoPE only, never `kv_ingress_*`** → west-shift vs north-shift ingress
  is irrelevant to retain *logic*. BUT retain's *precondition* — a **runtime-variable** prefill/
  cached length — is absent in integrated (compile-time `prefill_len_per_pe`), and integrated has
  **no `round_reset`, no multi-round loop, no re-arm** (grep-confirmed in CSL comptime binds AND
  the host launcher: no `NUM_ROUNDS`, no round loop).
- ⇒ Retain has **nowhere to attach** in integrated until the whole multi-round lifecycle is ported;
  that port = **S4/S5 (cluster-gated)** + a handful of [DIRECT] retain lines on top. So "abstract
  now so all three inherit retain for free" is **unavailable**. Migration cost ≈ the lifecycle
  port, dominant cost is scaffolding not KV logic.

**4. Prefill retain = the SAME mechanism (dig 5), feasibility MODERATE.**
Prefill has a persistent **non-zeroed** `[layer][chunk]` `K_cache_bank`/`V_cache_bank`
(`prefill.csl:776-777`), a multi-round serve loop (`launch.py:1491`), and a counter-only
`enter_request` reset (`:1537-1566`). So prefill retain = "gate the `current_chunk` rewind on a
resident slab" — the same idea as decode's "gate the `iter_num` rewind". Blockers: a `start_chunk`
warm-start path + host stream-skip + `CHUNK_SIZE` alignment (no inverse transform / cross-PE move /
RoPE re-derive — freqs are chunk-banked at global positions, prefix-stable). **Corrects an earlier
"prefill is egress-only, irrelevant to retain" characterization** — egress is a separate
copy-to-host, orthogonal to the resident cache.

**5. Force-decode = the M0/M2 boundary.**
`decode`'s native op is *sampling*; `prefill`'s is *processing known tokens*. So:
- Realistic multi-turn (new user turn = new input tokens) needs **force-decode** (feed a known
  token instead of the sampled one through decode's existing `process_kv` append — an input-token
  override, the M2 *mechanism*, not a cache change).
- Pure retain (S6a) covers only decode-side **degenerate** cases (resume interrupted generation;
  exact-whole-prefix repeat) PLUS the *real* prefill shared-prefix **fanout** (prefill needs no
  force-decode).
- decode already HAS the append primitive; no new cache primitive needed.
- The Option-A hybrid (reuse `L_prefix` in decode, compute `L_new` in prefill, inject at offset)
  needs **ingress-at-offset + offset RoPE in prefill** (transport extension) + an `R*` call (M2);
  on WSE force-decode-in-place usually wins, so generally not built.

## Implications / next actions

- [x] Decisions recorded in durable docs: S6-standalone-first + seam-isolated (abstract-later,
  extraction deferred to S4/S5); S6 = **S6a (Route A, retain-only, decode+prefill — do first)** +
  **S6b (Route B, optional, +force-decode on decode)**; GOALS §7 abstraction item = answered.
- [ ] Next: co-plan S6a sub-steps (decode `round_reset` counter-gate + host stop re-ship; prefill
  `start_chunk` warm-start + host stream-skip), then implement on sim (≤16×16), verify vs oracle.
- Seam-isolation discipline for S6a-decode (makes S4/S5 migration mechanical): retain enters as
  **data** into one `round_reset`; read retained length via **one runtime-capable accessor** (not
  the `prefill_len_per_pe_rt` global); touch **only counters/RoPE, never `kv_ingress_*`**.

## Pointers

- `milestones/M0-reuse-foundation.md § S6` (S6a/S6b) + Verification log 2026-07-13 — source of truth.
- `GOALS.md §7` abstraction item (answered) + `PROGRESS.md` 2026-07-13 session log.
- Kernels: standalone `models/qwen3_1p7b-decode/src/decode.csl`, `models/qwen3_1p7b-prefill/src/prefill.csl`;
  integrated `models/qwen3_1p7b-e2e/src/decode/decode.csl` (≡ pdSeparate modulo TSC profiler).
- Refines topic [[standalone-vs-integrated-kernel-parity]] (see its 2026-07-13 Updates).
