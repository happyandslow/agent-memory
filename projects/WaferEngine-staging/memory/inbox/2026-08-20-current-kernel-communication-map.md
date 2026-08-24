# Current kernel communication map — 2026-08-20

**Project:** WaferEngine-staging
**Author:** codex
**Status:** drained 2026-08-21 into `memory/topics/qwen3-decode-prefill-communication-map.md` and `plan.md`

## What happened / finding

- When a task needs current CSL source links for `qwen3_1p7b-decode` or `qwen3_1p7b-prefill` communication, do not use the older walkthrough documents as line-number authority. At least two prefill anchors had moved after source changes (`start_kv_egress` and `enter_request`).
- `memory/topics/qwen3-decode-prefill-communication-map.md` is the source-linked index inspected against the local tree on 2026-08-20. It maps the active P-1 through P-8 patterns and plumbing paths to current CSL entry points, with editable decode/prefill overview diagrams.

## Implications / next actions

- [ ] When an active kernel changes, refresh this source-link index and regenerate any affected per-kernel walkthrough/state-machine diagrams before relying on them for implementation tracing.

## Pointers

- `projects/WaferEngine-staging/memory/topics/qwen3-decode-prefill-communication-map.md`
- `projects/WaferEngine-staging/assets/kernel-algo/qwen3_1p7b-{decode,prefill}.communication-map.excalidraw`
