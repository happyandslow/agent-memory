# WaferLLM Attention/FFN pageability code snapshot — 2026-08-24

**Project:** WaferEngine / WaferLLM MeshJIT
**Author:** codex
**Status:** captured

## Git identity

- Repository checkout: `/home/lexu/WaferLLM`
- Origin: `git@github.com:happyandslow/WaferLLM.git`
- Branch: `attn-ffn-pageability`
- Commit: `b9f5d43a581f70d905e16bcf1959dc8979101194`
- Subject: `attention ffn pageability validation initial snapshot`
- Commit timestamp: `2026-08-24T16:40:33+00:00`
- Parent: `fd1c2daae37cd68706c03fc8009887ecee9900f8`
- Root tree: `bfc80e15d3a891d0231111d3de6311e186c05020`
- `MeshJit-Decode` subtree: `34791b5deef1743c2989098f41f66b804aa2dc82`
- `MeshJit-Decode/attention-ffn-phase1` subtree: `10e055b0282f3fe03063231f3d5905df218ab2b1`
- `MeshJit-Decode/attention-ffn-runtime-validation` subtree: `20d128baabf9c2ba4f68ad06463a361c93e827c2`

The commit adds 5,996 paths relative to its parent, including 126 binary paths. Its largest scopes are `attention-ffn-phase1` (4,666 paths) and `attention-ffn-runtime-validation` (1,141 paths), plus the earlier GEMV/vecmat/RoPE/mirror pageability lineage. This is a source/evidence snapshot; the presence of historical artifacts in the commit does not upgrade their recorded REVISE/FAIL/PASS dispositions.

## Recovery and remote status

At `2026-08-24T16:43:44Z`, the branch had no configured upstream, no local `origin/attn-ffn-pageability` tracking ref, and a direct `git ls-remote --heads origin refs/heads/attn-ffn-pageability` query returned no remote branch. Therefore the snapshot was local-only at the observation time. The commit hash is sufficient for recovery only while an object database containing it is available; push or another repository copy is still required for off-machine recovery.

To inspect the exact committed snapshot without moving an existing branch:

```bash
cd /home/lexu/WaferLLM
git switch --detach b9f5d43a581f70d905e16bcf1959dc8979101194
```

To create a new recovery branch from the snapshot:

```bash
git switch -c <recovery-branch> b9f5d43a581f70d905e16bcf1959dc8979101194
```

## Commit boundary versus working tree

The commit is the authoritative boundary. At the observation time, the following roots were untracked and are **not** part of `b9f5d43a…`:

- `/home/lexu/WaferLLM/.archive-work/`
- `/home/lexu/WaferLLM/pageability-audits/`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/.gitignore`

The validation `.gitignore` was created during post-commit cleanup to exclude rebuildable `.sim_*_out`, `local_out`, Python/test caches, and downloaded `cs_*.tar.gz` archives. Do not infer that this cleanup rule is contained in the snapshot commit.

## Validation result bound to this snapshot

The canonical correctness result carried by the snapshot is `p256-map-e2e-20260824-v5`: validation-only `B_U04_corrected` versus `D_dynamic`, 19/19 raw-f16 checkpoints plus Final Z bit-exact on real CS-3, mismatch count 0, final audit `PASS_P256_MAP_MAX_SHARED_SLOT_E2E`. This claim remains scoped to the frozen bsz1 Route-A/Policy-P/F4 construction and one Attention→FFN layer; it is not a production-baseline equivalence, 32-layer execution, SRAM-saving, latency, or throughput claim.

## Pointers

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/p256-map-e2e/README.md`
- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-runtime-validation/p256-map-e2e/evidence/p256-map-e2e-20260824-v5/e2e_audit.json`
- `projects/WaferEngine/memory/inbox/2026-08-24-meshjit-p256-shared-slot-e2e-pass.md`
- `projects/WaferEngine/memory/topics/meshjit-code-relocation.md`
- `https://context.ed-aisys.com/doc/2026-08-24-session-p256-shared-slot-validation-and-max-reduction-localization-OYpotFI2Ld`
