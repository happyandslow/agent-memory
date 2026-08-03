---
summary: Integrating a vendored kernel — every quantity you re-derive on your side is the drift you came to delete
tags: [nc_service, drained-inbox, 2026-07-28]
---

# Integrating a vendored kernel: every quantity you re-derive on your side is the drift you came to delete

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-28

Source: `memory/inbox/2026-07-28-take-scalars-from-the-kernel-not-your-own-derivation.md`

# Integrating a vendored kernel: every quantity you re-derive on your side is the drift you came to delete

Date: 2026-07-28 · Repo: `nc_service`, branch `lexu/pdsep-kernel-integration` (Tasks 5–7 of the sd-pdSeparate integration plan)

**Project:** nc_service
**Author:** claude
**Status:** captured

## The situation this applies to

You are wiring nc_service into the vendored `qwen3_1p7b-sd-pdSeparate` kernel and you hit a
step that reads like plain arithmetic: *"derive the serve scalars (`C_kv`, `kv_len_per_pe`,
`kv_cols`, …) from the model config so the host side can size its buffers."* It looks like
five lines of multiplication, so you write them.

**That step is the `model_adapter/` failure mode wearing a different hat** — the 4,377-line
reimplementation this whole integration exists to retire. The symptom when it goes wrong is
not a crash: the padding rule upstream changes by one, your copy does not, and KV lands at
shifted positions with attention quietly wrong.

The same trap has at least three separate doors in this kernel. Each time, the kernel already
publishes the thing you were about to recompute.

## Door 1 — geometry: the kernel persists the whole `sc` dict

`C_kv` is **not** `n_kv_heads * head_dim // p_block`. The real definition is

    C_kv = Pw * max_layers_per_block * kv_cols          # launch_decode.py:1474
    kv_cols = (n_kv_heads_PADDED * head_dim_shard) // P_BLOCK_SIZE

i.e. the product of ~50 lines of padding/sharding arithmetic (padded head count, 28 layers
distributed over 8 blocks). Re-deriving it means shadowing all of that.

**You do not have to.** `launch_decode.py:2427-2444` already serialises the entire `sc` dict
to `serve_meta.json` — its own comment says *"a reload needs no layout"* — and
`artifact_cache.read_serve_meta` reads it back. The real path is a file read, zero derivation.

Consequence for the design: split the API by *provenance*, not by convenience.
`read_serve_meta(cache_dir)` for the real path (delegates to the kernel's `artifact_cache`);
a separate `fake_serve_scalars(cfg, **overrides)` for the no-wafer path, whose synthesised
values carry an explicit `_synthetic` / `_synthetic_keys` marker so nothing downstream can
mistake them for compiled output. A synthetic `C_kv` is defensible **only** because both sides
of the assertion it feeds are ours: `serve_loop` checks each band against
`P_BLOCK_SIZE * (Pw*8 + C_kv*kv_rows)` and the band comes from our own `_repack_kv_band`. The
contract is self-consistency, not physical fidelity.

When a synthetic constant is unavoidable, encode the **relation** rather than the number:
derive `c_kv = pw * max_layers_per_block * kv_cols` from synthetic factors instead of writing
`C_kv = 4`. The identity stays visible, it tracks a changed `Pw`, and `kv_cols` /
`max_layers_per_block` land in `sc` — which is exactly what the *real*
`_repack_kv_band_builder(sc)` reads later.

## Door 2 — types: hand the kernel back its own `TargetFeedback`

`serve_loop:248` calls `target.verify(batch).validate(len(batch.steps))`. A duck-typed
feedback object with the right two fields passes every unit test and dies there. Construct the
kernel's own `TargetFeedback`; you get its bounds check on your numbers for free. Same reason
`batch_to_ref` must be tested against the **real** `host.specdec_protocol.DraftBatch` — a duck
type cannot catch an upstream field rename.

The one place to deliberately *not* reuse kernel types is the GPU side. `host.*` also defines
the device ABI (`pack_metadata`, `MetaCommand`, `DeviceResume`), so importing it on the target
host re-couples the verifier to the very ABI the RPC protocol exists to decouple. Guard it
with a subprocess test that points `WE_SD_PDSEP_DIR` at a nonexistent path, imports the
module, and asserts no `host.*` in `sys.modules` — a code-review convention will not hold.

## Door 3 — the seam only shows up when the real loop runs

Two constraints that only surfaced once the genuine `serve_loop` was driven against a fake
device, neither discoverable by reading:

- **`cfg` must carry BOTH `PREFILL_LEN` and `PREFILL_LENS`.** `serve_loop:109` is
  `cfg.get("PREFILL_LENS", [cfg["PREFILL_LEN"]] * n)` — Python evaluates the default argument
  eagerly, so the singular key is read unconditionally even when the plural is supplied.
  `KeyError: 'PREFILL_LEN'` on a config that looks complete. (Upstream latent bug; for us just
  "pass both", but it costs an hour if unwritten.)
- **`FakeRuntime` is not a fake `SdkRuntime` — it is `SdkRuntime` + the wafer.** The real
  runtime only pushes bytes; parsing the 8-word metadata and deciding how many records to
  return is the CSL kernel's behaviour. The host has no other observable seam for device
  behaviour, so the fold is necessary — but say so, or the next reader hunts for the
  corresponding code in the real runtime and it does not exist. Also: `receive` must write
  **in place** into the caller's `out` (`serve_loop` passes an `np.empty`); returning a new
  array silently yields uninitialised records.

## Why not port the real `_repack_kv_band` into the fake path

It is pure numpy (`np` + `repeat_metadata_rows`), so it is tempting. It lives in
`launch_decode.py`, which imports the Cerebras SDK at module top level (line 38) — so
`import launch_decode` fails on a dev box. Keep the fake as an explicit **stub**, not a port:
sizes match on both LOAD and RESUME paths and the metadata tile position matches; only the KV
*content* is stubbed to zero. A port would drift; a stub cannot pretend to be authoritative.
When KV semantics are genuinely needed, take a real `serve_meta.json` rather than growing the
stub.

## Promotion candidate

**Procedural, not project-specific.** The general rule: *when integrating against a vendored
component, prefer reading a value the component already publishes over recomputing it, even
when the recomputation looks trivial — and when you must synthesise, encode the relation and
mark the value synthetic.* Applies to any vendored-kernel or vendored-SDK integration, not
just this one. Worth folding into an integration skill if it recurs.

## Implications / next actions

- [ ] The plan's `derive_serve_scalars` step is superseded by `read_serve_meta` — the plan file
      was corrected in-session; confirm it stayed corrected.
- [ ] `fake_device.py` must stay test-only. The plan's Task 8 puts
      `make_fake_serve_runner` in `handlers.py`, which would make production code import the
      fake; move it into `fake_device.py` and leave `handlers.py` only the injected
      `serve_runner` parameter.

## Pointers

- Kernel (read-only): `git -C /home/lexu/WaferEngine-staging show cb49130f:models/qwen3_1p7b-sd-pdSeparate/<path>` (tag `pr-sd`) — `host/artifact_cache.py`, `host/specdec_runtime.py`, `host/specdec_protocol.py`, `launch_decode.py:1474` / `:2427-2444`.
- `waferengine/samples/specdec/sd_kernel/{kernel_env,bridge_target,fake_device,targets}.py`
- [[pdsep-kernel-adoption]] — the KV-contract half of the same "do not reimplement it" argument (`kv_bridge` vs our `kv_transform`).
- `memory/inbox/2026-07-27-why-patch-the-target-not-the-launcher.md` — why the seam is `target.verify()` at all.
