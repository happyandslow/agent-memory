# WaferLLM pageability demo relocated into MeshJIT — 2026-08-31

**Project:** WaferEngine
**Author:** codex
**Status:** captured

## What happened / finding

- Situation: the Attention→FFN pageability demo and its production-kernel and historical-evidence dependencies needed to live under the existing `/home/lexu/MeshJIT` checkout without importing a second Git object database or breaking code-adjacent runbooks.
- The non-Git WaferLLM working tree was copied as one subtree at `/home/lexu/MeshJIT/WaferLLM`; source `.git` was excluded. The parent MeshJIT repository remained the sole destination `.git` at branch `lexu/pageability`, observed HEAD `ba7d8f3a0da5ad61e0f330bd1156ed831b72b80b`.
- The parent MeshJIT `.gitignore` remains unchanged. WaferLLM's original `.gitignore` is preserved inside the nested subtree, and no `.git` exists inside that subtree.
- Active pageability runbooks were relocated to `/home/lexu/MeshJIT/WaferLLM`; frozen JSON/JSONL manifests and evidence were deliberately not path-rewritten because their bytes are part of provenance.
- Validation after migration: rsync mirror dry-run reported zero non-document changes; all 24 copied Markdown files were present with zero broken local links; the frozen execution retained exactly 25 manifest-matching files; both package manifests kept their expected SHA-256 identities; and all eight host-side package/generation tests passed.
- Source HEAD `fd1c2daae37cd68706c03fc8009887ecee9900f8` does not by itself identify the demo because the pageability package was working-tree content. Continue to use `SOURCE_SNAPSHOT.json`, dependency manifests, cloud archives, linked-ELF identities, and CS-3 evidence for backtracking.

## Implications / next actions

- [ ] Treat `/home/lexu/MeshJIT/WaferLLM/pageability-demo/` as the code-adjacent recovery entry point.
- [ ] Do not call the filesystem relocation a new CS-3 validation; source/ABI/config changes still require a fresh complete run.
- [ ] Le must decide separately whether and how to stage or commit the currently uncommitted migration in the existing MeshJIT repository.

## Pointers

- `/home/lexu/MeshJIT/WaferLLM/pageability-demo/docs/MESHJIT_RELOCATION.md`
- `/home/lexu/MeshJIT/WaferLLM/pageability-demo/RECOVERY_RUNBOOK.zh-CN.md`
- `/home/lexu/MeshJIT/WaferLLM/pageability-demo/SOURCE_SNAPSHOT.json`
- `/home/lexu/MeshJIT/WaferLLM/pageability-demo/reference/dependency_manifest.json`
- `projects/WaferEngine/memory/inbox/2026-08-24-waferllm-pageability-demo-code-redistribution.md`
