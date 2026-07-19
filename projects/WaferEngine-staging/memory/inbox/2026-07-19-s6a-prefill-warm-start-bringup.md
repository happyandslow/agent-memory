# S6a-prefill warm-start bring-up — three defects, capacity limits, mock-scale perf

Date: 2026-07-19 · Repo: `WaferEngine-staging` · Branch: `lexu/staging/s6a-inner-pe-kv-route-a` (nothing committed)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained   <!-- captured | drained; curated into memory/topics/s6a-prefill-warm-start.md 2026-07-19 -->

Warm-start (`START_CHUNKS`: a child request reuses a resident CHUNK_SIZE-aligned prefix and
streams/computes only the suffix chunks) is now **verified end-to-end in sim AND on real WSE-3**.
Before this session it had never actually executed: a fabric-level deadlock masked everything
downstream, so no correctness result about warm-start existed.

## 1. Three independent defects (all found, all fixed, none committed)

### D1 — odd-extent `fabin → fabout` `@mov16` never completes (WSE-3)
The block x-chain relays downstream columns' payloads with an async fabric→fabric mov. **When its
extent is ODD the async completion callback never fires** — the PE stalls forever, every column east
of it starves, and the whole block deadlocks. Silent: no compile error, no warning.

- Forward extent is `(P_BLOCK_SIZE - 1 - local_px) * recv_extent`, so **`recv_extent` must be EVEN**
  for every column's extent to be even.
- Widening the metainfo tail 2→3 made `recv_extent = tile + metainfo_len` odd (8+3=11) → deadlock.
- Fix: pad the metainfo tail so the per-column payload is even (`metainfo_len = 4` = 3 real + 1 pad).
- **Verified by an isolated standalone reproducer** (`models/xchain_repro/`, one row of 8 PEs):
  every ODD per-PE payload K ∈ {5,7,9,11,13,15} deadlocks; every EVEN K ∈ {6,8,…,20,32} completes —
  including K=32, which forwards 4× the failing payload. That rules out queue depth definitively.
- Promoted to its own skill: `csl-odd-extent-fabric-forward-hang`.

Full-kernel confirmation: `metainfo_len` 2 → PASS, 3 → deadlock, 4 → PASS (sim); 4 → PASS on the
appliance (device run 5.4 s, byte-identical). The earlier `metainfo_len=3` appliance job that ran
**3.5 h** is, against that 5.4 s baseline, a genuine deadlock rather than slowness.

### D2 — `ht_head.csl` `send_own` head-chunk branch hardcoded chunk slot 0
The branch that carries the per-request metainfo (`current_prefill_chunk == start_chunk`) read
`X_tile[0]` / `X_tile[HEAD_TILE]` — i.e. **chunk slot 0** — instead of the request's first chunk.
Correct only while `start_chunk` was always 0. With `start_chunk=1` the block received the embedding
of the zero-padded slot, so the recomputed suffix chunk's K **and** V were both wrong.
Fix: base the two assemble copies at `current_prefill_chunk * OWN_LEN` (+ `HEAD_TILE` for bcol1).

### D3 — host harness: two places silently assumed `start_chunk == 0`
- `build_request_stream` reset the RNG then drew only `stream_chunks` chunks → a warm round got the
  **prefix's** tokens placed at **suffix** positions. Fix: draw the full `req_n_chunks`, then slice
  `[start_chunk:]`.
- `launch.py` serve loop reused the pre-built `token_buf_u32` whenever `req_len == prefill_len`. That
  cache key was valid when the stream depended only on length; with warm-start two same-length
  requests need different streams, so the shortcut **silently dropped `start_chunks[_req]`** and ran
  the request cold. Fix: add `start_chunks[_req] == 0` to the cache key.

**Pattern worth remembering:** introducing one new per-request variable (`start_chunk`) invalidated
several independent places that implicitly assumed its old constant value — and *none* of them
raised an error. When adding a per-request dimension, go looking for every shortcut that encoded the
old default.

## 2. Verification status

| | sim | real WSE-3 |
|---|---|---|
| cold baseline (`START_CHUNKS` all 0) | PASS byte-identical | PASS byte-identical |
| warm-start `[0,1,1]` | **PASS byte-identical** | **PASS byte-identical** |
| warm-start at L=512 (3 requests) | — | **PASS byte-identical** |

Gate semantics: a same-length warm round must reproduce the cold round's KV **byte-for-byte**
(reused prefix untouched + suffix recomputed from identical tokens). This is a differential test —
cold and warm take different code paths and must agree. Note it is NOT sufficient on its own:
a warm-start that never engages also passes, which is exactly how D3's second half hid.

## 3. Capacity limits — prefill and decode hit DIFFERENT walls

Compile-only probes on the mock 2×4 shape (dim=64):

| kernel | largest that compiles | first failure | root cause |
|---|---|---|---|
| prefill | `MAX_SEQ_LEN = 2048` (256 chunks) | 4096 | `ran out of PE memory for data (.bss)` **and** task table |
| decode | `MAX_SEQ_LEN = 512` | 1024 | **DSD `.stride` field is `i8`** (`decode.csl:1163`) |

Decode's wall is an **ISA field width**, not memory: the KV traversal stride is `kv_len_per_pe =
MAX_SEQ_LEN / P_BLOCK_SIZE`, which must fit in i8 → `MAX_SEQ_LEN ≤ 127 × 8 = 1016`. Lifting it needs
a different KV access/layout so the stride is small — **not** a type widening. This is a distinct
constraint from the `~512` figure recorded for the real-dim 2×2/7-layer layout and should not be
conflated with it.

Note the quadratic attention buffer is quadratic in `chunk_len_per_pe = CHUNK_SIZE / P_BLOCK_SIZE`,
**not** in `MAX_SEQ_LEN`; with `chunk_len_per_pe = 1` it stays negligible and sequence length costs
only linear per-chunk banks.

## 4. Performance — MOCK SCALE ONLY, not a performance result

A 10-point device grid was run, but on the **mock** config (256–512 PEs, dim=64, vocab=64) rather
than the real `test_device_*` configs (**262k–524k PEs, dim=2048, 28 layers, vocab=151936**). These
numbers characterise the mechanism, **not** the model. Treat as a lower bound / direction only.

Also, the three `L=2048` rows are **invalid**: `PREFILL_LEN` was set to 2048, so `req_len ==
prefill_len` triggered D3's cache shortcut and no reuse happened (all four spans agreed to within
0.0001% — that flatness is what exposed the bug).

Valid rows (L=512 and L=1024, 3 requests, `START_CHUNKS=[0,k,k]`):

| reuse k/n | measured saving (L=512) | measured saving (L=1024) | (k/n)² |
|---:|---:|---:|---:|
| 50% | 23.3% | 24.1% | 25% |
| 75% | 48.5% | 52.0% | 56% |

**Saving tracks (k/n)², not k/n.** Mechanism: a chunk's cost grows with its position (it attends
over all preceding chunks), so cost ≈ n²/2 and skipping the first k saves ≈ k²/2. **The reused
prefix chunks are the cheap ones; the recomputed suffix is the expensive part.** If this holds at
real scale it means prefill-side prefix reuse has strong diminishing returns — a large saving needs
a large reuse *fraction*, and 50% reuse buys only about a quarter of the time.

This is the single most decision-relevant observation of the session and **must be re-measured on
the real-dim configs before it is used for anything.**

## 5. Open / next

- Re-run both kernels at **real scale** (`test_device_2x4_kv_varlen`, `test_device_2x4block_kv_varlen`,
  524,288 PEs) to confirm they pass on device, then redo the reuse experiment there.
- Decode reuse already has knobs — `RETAIN_ROUNDS` / `RETAINED_LENS`, with `repeat` and `chain`
  (growing-context) semantics — so no new test entry point is needed.
- Nothing is committed; the working tree carries all fixes pending review.
