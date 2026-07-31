---
summary: --reuse-prefill-from only accepts a store whose directory NAME equals the TARGET model_config name; renaming a config forces a bridge directory.
tags: [waferengine-staging, cerebras, build, operational-gotcha]
---

# `--reuse-prefill-from` keys on the directory NAME, not on the artifact

Hit 2026-07-31 while rebuilding decode for M2-E9 under a new model_config
(`serve_2x4_8k20k_s2` → `serve_2x4_8k20k_e9`, only `FORCED_MAX` differs). Cost three failed launches,
all host-side — **no wafer time** — but ~40 minutes of turnaround.

## The rule

`_resolve_reuse_store` (`launch_device.py:281-292`) tries exactly two paths, and **both bake the TARGET
config name into the lookup**:

```python
if path.name == model_config and (path / "prefill").is_dir():   # 1: the dir must be NAMED after it
    return path
candidate = path / model_config                                  # 2: or contain a dir named after it
if (candidate / "prefill").is_dir():
    return candidate
raise FileNotFoundError(...)
```

So a prefill artifact that physically exists at `serving_cache/serve_2x4_8k20k_s2/prefill` is
**unreachable** when building config `serve_2x4_8k20k_e9`, no matter which of the two paths you pass:

- `--reuse-prefill-from .../serving_cache` → looks for `serving_cache/serve_2x4_8k20k_e9` ✗
- `--reuse-prefill-from .../serving_cache/serve_2x4_8k20k_s2` → `path.name` is `..._s2` ≠ `..._e9` ✗

⇒ **Renaming a model_config always breaks prefill reuse**, even when the prefill artifact is provably
valid for the new config.

## The fix — a bridge directory named after the new config

```bash
mkdir -p $L/e9_reuse/serve_2x4_8k20k_e9
ln -s $L/serving_cache/serve_2x4_8k20k_s2/prefill $L/e9_reuse/serve_2x4_8k20k_e9/prefill
# then: --reuse-prefill-from $L/e9_reuse/serve_2x4_8k20k_e9      (hits branch 1)
```

A symlink is enough — `_reuse_prefill_phase` does `shutil.copytree`, which reads through it. No need to
duplicate the ~3.3 GB artifact.

## When reuse is legitimate at all

Only when the new config changes **nothing prefill reads**. For E9 that held: the sole difference was
`FORCED_MAX`, which is host-only and sizes the *decode* x-stream token-id port
(`first_token_total_wavelets = P_BLOCK_SIZE * FORCED_MAX`, `launch_decode.py:551`); prefill never reads
it.

⚠️ **The freshness gate cannot check this for you.** The build manifest is written with the fingerprint
of the *current* tree + *new* config and asserts the store matches — while the prefill half was compiled
earlier, from whatever the tree was then. Safe here because prefill sources had not changed; **it would
silently serve a stale prefill binary if they had.** That is why `--reuse-prefill-from` is an explicit
flag and not automatic: the caller warrants that prefill sources are unchanged.

## Last updated

2026-07-31
