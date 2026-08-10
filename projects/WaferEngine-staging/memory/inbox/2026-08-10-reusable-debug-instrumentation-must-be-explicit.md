# Reusable debug instrumentation must be explicit and default-off — 2026-08-10

**Project:** WaferEngine-staging  
**Author:** human  
**Status:** captured

## Situation

- Temporary, purely diagnostic code should be removed after each debugging task.
- Instrumentation that has continuing verification value may remain only behind an explicit, well-named, default-off flag.
- Unrelated runtime modes or test configurations must not implicitly enable retained instrumentation.

## Required behavior

- Ordinary simulator and device runs carry no debug-only behavior or payload by default.
- Device entry points reject simulator-only debug flags before layout/runtime setup.
- A disabled verifier reports `SKIPPED`; it must never imply that the omitted verification passed.
- Tests cover both the default-off path and the explicitly enabled path, including fail-closed behavior when required evidence is absent or malformed.

## Application

- Apply this rule during each implementation-step cleanup and review.
- For M1/S3, the retained full-logit verification path is explicitly opt-in; the formal device gate remains a separate required acceptance gate beginning with S3.7.

## Current pointers

- `models/qwen3_1p7b-decode/launch.py`
- `models/qwen3_1p7b-decode/layout.py`
- `models/qwen3_1p7b-decode/launch_sim.py`
- `models/qwen3_1p7b-decode/launch_verify.py`
