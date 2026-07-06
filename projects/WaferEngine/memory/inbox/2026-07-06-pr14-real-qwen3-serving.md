# PR #14 "Real Qwen3 1.7B Serving" — compile-once / serve-many — 2026-07-06

**Project:** WaferEngine
**Author:** claude
**Status:** captured   <!-- captured | drained -->

PR https://github.com/WaferAGI/WaferEngine/pull/14 (open) by Congjie He,
branch `real_qwen3_1p7` → `main`, 33 files +776/−713, empty PR body.
Turns the Qwen3-1.7B prefill+decode kernels into a genuine
compile-once / serve-many serving path. Three connected features, each with
how it's implemented:

## What happened / finding

### 1. Config split: model_config (baked) vs request_config (runtime)
- **What:** serving params separated so ONE binary serves many requests.
  `model_config/*.json` keeps only binary-baked params (arch, placement,
  capacity ceilings `MAX_SEQ_LEN`/`NUM_ROUNDS`/`bsz`/`TOP_K`, decode policy
  temp/top_p/seed). Per-request payload (`PREFILL_LEN`, `PREFILL_LENS`) moved
  OUT into a new `request_config/*.json` dir.
- **How:** new `load_config(config, request)` in `launch.py:~2779` loads model
  cfg then `cfg.update(json.load(request))` overlays request on top. If
  `--request` omitted, auto-derives sibling `request_config/<same-name>.json`
  (`config_path.parent.parent / "request_config" / config_path.name`); a legacy
  monolithic cfg with request keys inline still loads (no sibling → no overlay).
  `launch.py`/`launch_sim.py`/`launch_device.py` all gain `--request`.
  `launch_device.py` also STAGES the request file to the worker
  (`shutil.copy2` into `staging_dir/request_config/<name>`) and appends
  `--request request_config/<name>` to the `cs_python launch.py` run_cmd so the
  worker's `load_config` overlays it.

### 2. Dropped the compile-time "bake" KV path (KV_TRANSFER=0 removed)
- **What:** old `KV_TRANSFER=0` mode (prefill length baked in as a compile-time
  seed) deleted throughout the CSL. Only runtime variable-prefill remains; one
  artifact serves any prefill up to the compiled max.
- **How:** in `decode.csl` removed `param prefill_len_per_pe` and its branches;
  `prefill_max_per_pe` (= `kv_len_per_pe - 1`) now sizes KV-ingress
  tile/DSDs/offsets, and `prefill_len_per_pe_rt` is ALWAYS extracted at runtime
  from the KV-ingress phase-0 metainfo tile each round. Host pads each round's
  KV to `prefill_max_per_pe` rows. Dead `KV_TRANSFER` branches also pruned from
  `comm_pe.csl`, `demux.csl`, `mux.csl`, `decode_strip.csl`, `prefill.csl`.
  Confirms `[[dynamic-kv-load]]`: the bake alternative is now GONE, not just
  unused.

### 3. Decode loop runtime-terminated by per-round budget / EOS
- **What:** round count is no longer compiled in; each round ends via a STOP
  flood, so variable-length + multi-round + EOS serving all work on one binary.
- **How:** `ht_head.csl` main task ALWAYS reads the per-round budget N off the
  token path (bsz-wide header, slot 0 = N) into `n_steps`, then loops
  `ht_step < n_steps + 1`. The extra terminator step (`ht_step == n_steps`) has
  the diag PE write `embed_buf[0] = STOP_SENTINEL_F16` (-65504.0) and flood it
  down the X path, then `break`. Downstream is identical to a natural EOS flood
  (blocks detect at `decode.csl:~1747`, forward to strip, break; strip resets
  `strip_iter` per round). Matching updates in `ht_tail.csl`, `decode.csl`,
  `decode_strip.csl`.

New fixtures cover 3 serving shapes across sim+device:
`2x2block_eos`, `2x2block_kv_varlen`, `2x4block_kv_varlen` (model_config +
request_config pair each).

## Implications / next actions

- [ ] On merge, update topic `[[dynamic-kv-load]]`: KV_TRANSFER=0 bake path is
      DELETED (was "unused/Option B chosen"); document the model/request config
      split as the serving contract.
- [ ] Note for future decode work: round count / EOS is a RUNTIME budget in the
      token-path header, not a compiled param — don't reintroduce compile-time
      round assumptions.

## Pointers

- PR #14, branch `real_qwen3_1p7`, commit 8a4f591
- `models/qwen3_1p7b-decode/launch.py` (`load_config`), `launch_device.py`
  (staging), `src/decode.csl`, `src/ht_head.csl`
- `models/qwen3_1p7b-decode/{model_config,request_config}/`
- Related topic: `memory/topics/dynamic-kv-load.md`
