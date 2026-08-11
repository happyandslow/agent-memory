---
summary: Retained verification/debug instrumentation is allowed only when explicit, default-off, fail-closed, and rejected on unsupported device entry points.
tags: [WaferEngine-staging, instrumentation, verification, debug, device-gate, fail-closed, drained-inbox, 2026-08-10]
---

# Explicit default-off debug instrumentation — 2026-08-10

This topic was created by the 2026-08-11 maintain pass from `memory/inbox/2026-08-10-reusable-debug-instrumentation-must-be-explicit.md`.

Temporary, purely diagnostic code should be removed after each debugging task. Instrumentation that has continuing verification value may remain only behind an explicit, well-named, default-off flag.

## Required behavior

- Ordinary simulator and device runs carry no debug-only behavior or payload by default.
- Device entry points reject simulator-only debug flags before layout/runtime setup.
- Unrelated runtime modes or test configurations must not implicitly enable retained instrumentation.
- A disabled verifier reports `SKIPPED`; it must never imply that omitted verification passed.
- Tests cover both the default-off path and the explicitly enabled path, including fail-closed behavior when required evidence is absent or malformed.

## M1/S3 application

For M1/S3, the retained full-logit verification path is explicitly opt-in. The formal acceptance gate remains separate: every implementation step beginning with S3.7 needs real-device evidence before it is treated as complete.

## Current pointers

- `models/qwen3_1p7b-decode/launch.py`
- `models/qwen3_1p7b-decode/layout.py`
- `models/qwen3_1p7b-decode/launch_sim.py`
- `models/qwen3_1p7b-decode/launch_verify.py`
- Related device-gate topic: `memory/topics/m1-s37-prefix-reuse-device-gates.md`.
