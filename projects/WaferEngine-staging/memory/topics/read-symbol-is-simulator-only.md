---
summary: read_symbol is simulator-only in Cerebras SDK 2.10 — usable under memcpy_required=False but never on a real CS-3; the no-memcpy device path is create_output_stream.
tags: [waferengine-staging, cerebras-sdk, sdklayout, host-device, closed-path]
---

# `read_symbol` is simulator-only — closed for device runs

> Investigated 2026-07-31 on SDK **2.10** (`/home/lexu/Cerebras-SDK-2.10.0`, resolved by container
> probe). Question asked: *can `read_symbol` be used under `memcpy_required=False`, so we can pull a
> value off the device without introducing the memcpy channel?*

## Answer

**Two separate questions, and only the second one binds.**

1. **Compatible with `memcpy_required=False`? YES.** The SDK's own SdkLayout tutorials call it exactly
   that way — `sdklayout-01-introduction/run.py:53,63`, `sdklayout-02-routing/run.py:90,103`,
   `sdklayout-03-ports-and-connections/run.py:140,151` all construct
   `SdkRuntime(compile_artifacts, platform, memcpy_required=False)` and then call `runtime.read_symbol(...)`.
   So the memcpy channel is genuinely not required for it.

2. **Works on real hardware? NO — and this is fatal.** The official API reference is explicit:
   > `read_symbol(x, y, symbol_name, dtype='uint8') -> numpy.ndarray`
   > **"Read the value of a symbol on a specific PE. This method is only supported in the simulator."**
   > — `Cerebras_Docs/api-docs/sdkruntime-api.md:808-809`

   Corroborated independently twice more in the same KB: `CSL_Host_Device_Communication_Guide.md:520`
   ("Read symbol from a specific PE (simulator only)") and its API table at `:811`
   ("`runner.read_symbol(x, y, name, dtype)` | Read PE symbol (**sim only**)").

⇒ **Three sources agree. The path is closed for anything on a real CS-3**, and since this project's rule
is that all performance work runs on the wafer and never simfab, it is closed for our purposes entirely.
The `memcpy_required` question was the wrong axis to worry about.

## What to use instead — and it still avoids the memcpy channel

`layout.create_output_stream(port)` under `memcpy_required=False`. Demonstrated end-to-end in
`sdklayout-04-h2d-d2h/run.py:73,86` (two input streams + one output stream, no memcpy), and it is
already the mechanism this repo uses for the decode logits stream.

⚠️ **Cost note that changes the plan.** An output stream needs a **device-side port plus a `fabout` DSD
writing into it** — so it is *not* a host-only change. Any plan of the form "confirm `read_symbol`
works, then just write the host side and take one 4.5-minute decode rebuild" does not survive: the
rebuild cost is the same, but the edit spans the kernel too.

## Not validated on device, deliberately

A standalone device job could test whether "simulator only" is stale. **Not run** — it would spend a
CS-3 slot to probe a path that three documentation sources close and for which a known-good alternative
already exists in this very repo. Recorded as a decision, not an oversight.


## What it actually cost

This was not academic. E9's force-decode timing was **built once on this assumption** — the pair of
timestamps sat in `export var`s on a block PE, deliberately, because that PE has no free color or
output queue and a `read_symbol` readback needs no fabric at all. The reasoning was sound; the
mechanism does not exist on hardware. The work was rewritten to measure on `ht_tail` instead, which
already owns a drained per-round burst. See [[e9-forced-segment-tsc]].

**Rule of thumb this earns:** on this project, "how do I get a value off the device?" has exactly one
answer on real hardware — **an output stream/port that something already drains**. Reach for an
existing drained path before designing a new one, and never for `read_symbol`.

## Why this is not a skill

It is one lookup away in the official API reference. The `csl-*` / `cerebras-sdk-*` skill family exists
for behaviour that is *undocumented or contradicts* the docs (silent hangs, misleading TypeErrors,
binding quirks). This is documented and behaves as documented, so it belongs in project memory as a
closed question — not in the skill set.

## Last updated

2026-07-31
