# MeshRT Attention/FFN dynamic-page-region audit — scope correction

Date: 2026-08-13
Status: drained

## Supersession

The earlier MeshRT capture that classified eight *whole* prefill/decode state
machines answered the wrong question.  It is superseded for pageability scope
by this capture.  The requested unit is the Attention and FFN computation
inside each phase: four paper models × prefill/decode × Attention/FFN = 16
source candidates.

## Frozen inputs and evidence

- Repository: `https://github.com/CongjieHe/meshRT-csl`, branch `che/paper-exp`,
  revision `52a881c4984bd5db9ed25582d609dde888b989a8`, clean clone.
- Audit artifacts: `/tmp/meshrt-attention-ffn-region-audit/README.md` and
  `region_manifest.json`.
- Evidence grade: S (source closure) only.  SDK 2.10 could not start `cslc` in
  the local environment because its Singularity/FUSE/setuid runtime was
  unavailable, and the source repository contains no final ELF/map artifacts.
  Therefore no linked-byte, removable-ownership, fixed-gap, or complete-SRAM
  numbers are claimed.

## Durable conclusion

All 16 complete source regions are `unsupported-current-loader` for direct
injection.  Each has normal calls and/or `@map` lowering, control flow,
collective/fabric DSD operations, queue/route/task callback state, or a
scheduler continuation.  This does **not** reject Attention/FFN paging.

The viable research shape is a fissioned, multi-entry, address-matched compute
region: leaf and branch-free arithmetic entries (projection/GEMV, RoPE,
score/softmax/output, residual; and up/gate/activation/down where applicable)
may become future page material once their closure and ABI are proven.
Resident thunks must retain the scheduler, collectives and reconfiguration,
fabric moves/DSDs, queues/colors/routes, async callbacks/barriers, MoE
dispatch/combine, and the continuation to the next phase.  In MoE decode, FFN
compute is specifically between resident dispatch/reconfiguration and resident
combine/callback thunks; GPT-OSS-120B changes configuration inside its expert
phase.

## Next evidence gate

Build identical B/A region-absent mirrors, obtain final ELF/map/relocation and
complete receiver SRAM deltas, then separately prove a leaf page's pinned
address/DSR ABI and receiver execution.  Do not treat source spans as code or
SRAM bytes.
