# You set a large forced_decode_len and the run dies before touching the wafer — 2026-07-31

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained

## Symptom

A `--mode reload` serve aborts host-side, before any wafer time, with:

```
ValueError: request.forced_decode_lens[2] = 1024 exceeds FORCED_MAX=512 compiled into
model_config serve_2x4_8k20k_s2; raise FORCED_MAX and rebuild the store, or lower F
```

## Finding

`FORCED_MAX` is a **compile-time envelope**, not a runtime knob. It lives in the model_config
(`serve_2x4_8k20k_s2.json:89`) and sizes the x-stream token-id **port capacity**:
`first_token_total_wavelets = P_BLOCK_SIZE * FORCED_MAX` (`launch_decode.py:551`), because a
round pushes `F` token-id frames instead of one.

- It is **host-only** — it costs **no PE memory**. Raising it is cheap in the one resource that
  is usually tight.
- 512 → 20,224 moves the port from 0.13 M to 5.18 M wavelets, against an x-stream that already
  carries 20.7 M. It compiled and ran.
- Raising it needs a **new model_config + a decode rebuild** (~4.5 min with prefill reused).

⇒ **Check `FORCED_MAX` before designing any F sweep.** It silently caps the experiment's range,
and the failure only appears at serve time — after the fixture is built and synced.

## Related trap hit in the same sequence

Renaming the model_config to raise `FORCED_MAX` **breaks prefill reuse** —
`--reuse-prefill-from` resolves by the *target* config name, so an artifact sitting at
`serving_cache/<old>/prefill` becomes unreachable. Bridge with a directory named after the new
config. Full detail already recorded.

## Implications / next actions

- [ ] Any future F sweep: read `FORCED_MAX` from the model_config first and size the sweep to it,
      or budget the rebuild up front.

## Pointers

- `topics/reuse-prefill-from-requires-matching-dirname.md`
- `model_config/serve_2x4_8k20k_e9.json` (the raised-ceiling config, committed `942e549`)
