---
summary: M0/S6a-prefill warm-start (START_CHUNKS prefix reuse) — verified byte-identical in sim and on WSE-3; three defects found (odd-extent fabric deadlock, hardcoded chunk slot, host start_chunk assumptions); real-scale prefill reuse measured and strongly sub-linear; decode retain saves by skipping steps, not by making a decode step cheaper.
tags: [waferengine-staging, qwen3, prefill, kv-reuse, warm-start, s6a, csl, wse-3, capacity, verification]
---

# S6a-prefill — warm-start prefix reuse: bring-up, defects, limits, performance

> Curated learnings from the first end-to-end bring-up of prefill warm-start
> (M0/S6a-prefill, 2026-07-19). **Plan/state live in the in-repo durable docs**
> (`milestones/M0-reuse-foundation.md § S6a`, `PROGRESS.md`) — those win on conflict.
> Companion to the decode-side note [[s6a-decode-kv-retain]]; this is the same
> reuse idea expressed in a different counter, as predicted by the 2026-07-13
> abstraction design.

## What warm-start is

`START_CHUNKS`: a child request reuses a resident CHUNK_SIZE-aligned prefix of a
parent request and streams/computes only the suffix chunks. Standalone
`qwen3_1p7b-prefill`, branch `lexu/staging/s6a-inner-pe-kv-route-a`.

As of 2026-07-19 it is **verified end-to-end in sim AND on real WSE-3**. Before this
session it had never actually executed — a fabric-level deadlock masked everything
downstream, so no correctness result about warm-start existed at all.

## Three independent defects (all fixed; see repo for commit state)

### D1 — odd-extent `fabin → fabout` `@mov16` never completes (WSE-3)

The block x-chain relays downstream columns' payloads with an async fabric→fabric
`@mov16`. **When its extent is ODD the async completion callback never fires** — the PE
stalls forever, every column east of it starves, and the block deadlocks. Silent: no
compile error, no warning.

- Forward extent is `(P_BLOCK_SIZE - 1 - local_px) * recv_extent`, so **`recv_extent`
  must be EVEN** for every column's extent to be even.
- Widening the metainfo tail 2→3 made `recv_extent = tile + metainfo_len` odd (8+3=11)
  → deadlock. Fix: pad the tail so the per-column payload is even
  (`metainfo_len = 4` = 3 real + 1 pad).
- **Isolated reproducer** (`models/xchain_repro/`, one row of 8 PEs): every ODD per-PE
  payload K ∈ {5,7,9,11,13,15} deadlocks; every EVEN K ∈ {6,8,…,20,32} completes —
  including K=32, which forwards 4× the failing payload. That **rules out queue depth
  definitively**.
- Full-kernel confirmation: `metainfo_len` 2 → PASS, 3 → deadlock, 4 → PASS (sim);
  4 → PASS on the appliance (device run 5.4 s, byte-identical). An earlier
  `metainfo_len=3` appliance job that ran **3.5 h** is, against a 5.4 s baseline, a
  genuine deadlock rather than slowness.
- Promoted to its own skill: `csl-odd-extent-fabric-forward-hang`.

### D2 — `ht_head.csl` `send_own` head-chunk branch hardcoded chunk slot 0

The branch carrying per-request metainfo (`current_prefill_chunk == start_chunk`) read
`X_tile[0]` / `X_tile[HEAD_TILE]` — **chunk slot 0** — instead of the request's first
chunk. Correct only while `start_chunk` was always 0. With `start_chunk=1` the block
received the embedding of the zero-padded slot, so the recomputed suffix chunk's K
**and** V were both wrong. Fix: base both assemble copies at
`current_prefill_chunk * OWN_LEN` (+ `HEAD_TILE` for bcol1).

### D3 — host harness assumed `start_chunk == 0` in two places

- `build_request_stream` reset the RNG then drew only `stream_chunks` chunks → a warm
  round got the **prefix's** tokens placed at **suffix** positions. Fix: draw the full
  `req_n_chunks`, then slice `[start_chunk:]`.
- `launch.py` serve loop reused the pre-built `token_buf_u32` whenever
  `req_len == prefill_len`. That cache key was valid when the stream depended only on
  length; with warm-start two same-length requests need different streams, so the
  shortcut **silently dropped `start_chunks[_req]`** and ran the request cold. Fix: add
  `start_chunks[_req] == 0` to the cache key.

### Transferable pattern

Introducing one new per-request variable (`start_chunk`) invalidated several independent
places that implicitly encoded its old constant value — and **none of them raised an
error**. When adding a per-request dimension, go looking for every shortcut, cache key,
and hardcoded index that assumed the old default.

## Verification — and why the gate is not sufficient alone

| | sim | real WSE-3 |
|---|---|---|
| cold baseline (`START_CHUNKS` all 0) | PASS byte-identical | PASS byte-identical |
| warm-start `[0,1,1]` | **PASS byte-identical** | **PASS byte-identical** |
| warm-start at L=512 (3 requests) | — | **PASS byte-identical** |

Gate semantics: a same-length warm round must reproduce the cold round's KV
**byte-for-byte** (reused prefix untouched + suffix recomputed from identical tokens).
This is a **differential test** — cold and warm take different code paths and must agree.

**It is not sufficient on its own: a warm-start that never engages also passes**, which
is exactly how the second half of D3 hid. Any future reuse gate needs a positive check
that the reuse path actually ran.

## Capacity — prefill and decode hit DIFFERENT walls

Compile-only probes on the mock 2×4 shape (dim=64):

| kernel | largest that compiles | first failure | root cause |
|---|---|---|---|
| prefill | `MAX_SEQ_LEN = 2048` (256 chunks) | 4096 | `ran out of PE memory for data (.bss)` **and** task table |
| decode | `MAX_SEQ_LEN = 512` | 1024 | **DSD `.stride` field is `i8`** (`decode.csl:1163`) |

Decode's wall is an **ISA field width, not memory**: the KV traversal stride is
`kv_len_per_pe = MAX_SEQ_LEN / P_BLOCK_SIZE`, which must fit in i8 →
`MAX_SEQ_LEN ≤ 127 × 8 = 1016`. Lifting it needs a **different KV access/layout so the
stride stays small** — a type widening will not do it.

**Do not conflate this with the ~512 figure in
[[e2e-pdSeparate-device-validation]]**: that one is a *prefill SRAM/PE-memory* limit on
the real-dim 2×2/7-layer layout. The numbers collide by coincidence; the mechanisms are
unrelated.

Note the quadratic attention buffer is quadratic in
`chunk_len_per_pe = CHUNK_SIZE / P_BLOCK_SIZE`, **not** in `MAX_SEQ_LEN`; with
`chunk_len_per_pe = 1` it stays negligible and sequence length costs only linear
per-chunk banks.

## Prefix-reuse saving scales sub-linearly — real-scale result now recorded

### 2026-07-20 real-scale WSE-3 grid

Drained from `memory/inbox/2026-07-19-prefill-prefix-reuse-real-scale-perf.md`. This is the first **real-scale** prefill-side prefix-reuse (`START_CHUNKS`) measurement: Qwen3-1.7B real dims, 512 × 1024 = **524,288 PEs**, `PREFILL_LEN = MAX_SEQ_LEN = 8192`, `CHUNK_SIZE = 256` (32 chunks), three 8192-token requests with `START_CHUNKS=[0,k,k]`. The TSC span is the last request's pure device forward window: start when first tokens land on device, end after logits emit; host stream construction and post-processing are outside it. `n=1` per point.

| k | reuse | span_cycles | forward latency | per-request throughput | vs k=0 |
|---:|---:|---:|---:|---:|---:|
| 0 | 0% | 1,101,615,635 | 1001.47 ms | 8,180.0 tok/s | — |
| 8 | 25% | 1,016,462,831 | 924.06 ms | 8,865.3 tok/s | +8.4% |
| 16 | 50% | 850,635,411 | 773.30 ms | 10,593.5 tok/s | +29.5% |
| 24 | 75% | 604,117,559 | 549.20 ms | 14,916.3 tok/s | **+82.3%** |

Saving vs reuse fraction: 25% reuse saves **7.7%**, 50% saves **22.8%**, 75% saves **45.2%**. The curve is strongly sub-linear in hit fraction and falls short of the simple `(k/n)^2` approximation at high reuse; fixed per-request work that cannot be skipped puts a floor under latency.

Useful marginal-cost model from skipped 8-chunk bands:

| skipped chunks | saving | per chunk |
|---|---:|---:|
| 0–7 | 85.2M cycles | 10.64M |
| 8–15 | 165.8M cycles | 20.73M |
| 16–23 | 246.5M cycles | 30.81M |

Linear fit: `cost(chunk c) ≈ 6.2M + 1.26M·c` cycles. The last chunk costs about 45M cycles, ~7× the first. Mechanism: the reused prefix is the cheap beginning of the request; the recomputed suffix is the expensive, longer-context part.

Correctness held at every point: `KV round 1 vs round 0` and `round 2 vs round 0` were **BYTE-IDENTICAL PASS**, tokens `all-equal=True`.

Decision consequence: prefix reuse's value needs a **position-weighted** model, not a linear hit-rate model. The current `R* = Δ·BW/B_tok` framing lacks a term for where the reused span sits.

### Decode addendum from the same capture

The earlier “decode reuse benefit is unmeasurable” conclusion is retracted. Retain does **not** make an equal-work decode step cheaper: when both arms do the same number of decode steps over the same context, reuse is only ~0.02% slower (fixed bookkeeping cost). Its benefit is **not re-executing decode steps that already ran**.

Read that null result narrowly — the equal-work grid is blind **twice over**. Besides equal decode work by construction, the arms' only real difference (this round re-prefilled the prefix vs inherited it) falls **outside** decode's TSC window, which starts after KV injection. The no-reuse arm genuinely pays a fresh prefill every round; that metric cannot see it. So ~0.02% licenses “a retained step is not a cheaper step”, and nothing stronger.

Correct real-scale comparison at `MAX_SEQ_LEN=1024`, `L=D=256`:

| arm | round 0 | round 1 | total decode |
|---|---:|---:|---:|
| no-reuse (`DECODE_LENS=[256,512]`, `RETAIN=[0,0]`) | 127.7M | 262,928,666 | 390.6M |
| reuse (`DECODE_LENS=[256,256]`, `RETAIN=[0,1]`, `RETAINED=[0,-1]`) | 127.7M | 127,696,962 | 255.4M |

Round 1 is **−51.4%** and total decode is **−34.6%**, matching the step-count prediction. Decode's TSC already starts after KV injection, so it is the correct compute metric; do not add a prefill-phase timer for this question. The large host→device KV-volume drop in the standalone harness is not a serving benefit and should not be quoted.

### Sequence-length scaling and operational pitfall

- Compile-only capacity at real scale: prefill compiles at 16,384 (64 chunks) and fails at 32,768 due to an `i16` overflow, not memory. Decode compiles at 4096; the mock-scale `MAX_SEQ_LEN ≤ 1016` bound came from `P_BLOCK_SIZE=8` and does not bind at real scale.
- One completed cold prefill point at L=16,384: **3144.94 ms**, 5,209.6 tok/s. Doubling L from 8192 more than triples latency (**×3.14**), confirming per-token cost grows with sequence length.
- Open: k>0 points at L=16,384 and the decode L=4096 pair were resubmitted after cluster recovery and were still in flight as of the capture.
- Device `out_*` artifact dirs do **not** persist back to the login node. The captured stdout is the result; every device batch must tee per-point logs to local disk, or the measurement is lost and requires a full recompile. Also keep remote `~` literal in paths destined for the remote shell; accidental local expansion causes fast `cd` failures that look like cluster faults.

## Earlier mock-scale observation — now mechanism-only background

**Caveat first:** the 10-point device grid was run on the **mock** config (256–512 PEs,
dim=64, vocab=64), not the real `test_device_*` configs (262k–524k PEs, dim=2048,
28 layers, vocab=151936). These numbers characterise the *mechanism*, not the model.

Also, the three `L=2048` rows are **invalid**: `PREFILL_LEN` was 2048, so
`req_len == prefill_len` triggered D3's cache shortcut and no reuse happened (all four
spans agreed to within 0.0001% — that flatness is what exposed the bug).

Valid rows (L=512 and L=1024, 3 requests, `START_CHUNKS=[0,k,k]`):

| reuse k/n | saving (L=512) | saving (L=1024) | (k/n)² |
|---:|---:|---:|---:|
| 50% | 23.3% | 24.1% | 25% |
| 75% | 48.5% | 52.0% | 56% |

**Saving tracks (k/n)², not k/n.** Mechanism: a chunk's cost grows with its position (it
attends over all preceding chunks), so total cost ≈ n²/2 and skipping the first k saves
≈ k²/2. **The reused prefix chunks are the cheap ones; the recomputed suffix is the
expensive part.**

If this holds at real scale it means **prefill-side prefix reuse has strong diminishing
returns** — a large saving needs a large reuse *fraction*, and 50% reuse buys only about
a quarter of the time. This is the most decision-relevant observation of the session and
**must be re-measured on the real-dim configs before it is used for anything.**

See also: [[s6a-decode-kv-retain]], [[kv-cache-policy-tradeoffs]],
[[standalone-vs-integrated-kernel-parity]], [[e2e-pdSeparate-device-validation]].

Source/drain note: `memory/inbox/2026-07-19-s6a-prefill-warm-start-bringup.md`.
