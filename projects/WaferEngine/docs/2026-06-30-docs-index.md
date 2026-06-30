# 2026-06-30 WaferEngine Docs Index

Last updated: 2026-06-30

Date-scoped write-ups and generated artifacts.

Layout convention:

```text
docs/
  YYYY-MM-DD/
    YYYY-MM-DD-<artifact-or-note>.md
    <related-generated-files>
```

Keep all files produced for the same investigation/session under the same date directory so Obsidian and git history stay navigable.

## Entries

- `2026-06-30/2026-06-30-specdec-dual-kernels-design.md` — DESIGN: run the real
  Qwen3-1.7B prefill + decode kernels behind `samples/specdec` as the spec-dec
  DRAFT model; sequential in-order deploy, cold-start decode, real weights both
  kernels; on-chip round op = iter_num rollback + correction inject + RoPE
  position table.
- `2026-06-28/` — PE-SRAM per-PE resource breakdown tool (design, plan, discovery
  write-up, generated slides/pdf).
