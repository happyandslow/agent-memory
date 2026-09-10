# CS-3 has a real csl-kernel bundle distinct from GitHub main — 2026-09-10

**Project:** nc_service
**Author:** codex
**Status:** captured; read-only inspection, no migration yet

## Location and version

Le supplied the actual deployment path:
`/home/eidf217/eidf217/congjiehe/workspace/nc_service/waferengine/csl-kernel`.
It exists on CS-3 and is **different from the mock delivery on GitHub main**.
The server checkout HEAD is `bcc7891`, but the real delivery is represented by
modified README/manifest, removed mock files, and an untracked `serving/` tree.
Preserve these server-side changes; do not overwrite this checkout during sync.

The real layout is `serving/{launch_device.py,launch.py,launch_prefill.py,
launch_decode.py,host/,model_config/,request_config/,serving_cache/}`. There is
no `pd_serving/` package in this deployed version. The public launch_device entry
uses reload; legacy compile helpers remain in the phase launcher source.

## Artifact inventory verified on disk

Cache root: `<csl-kernel>/serving/serving_cache/serve_2x4_8k20k/`.

- `prefill/`: 1,233 files, 3,375,648,128 bytes; `sim.elf.zst` is
  3,338,209,200 bytes; 408 `executables/*.elf`.
- `decode/`: 870 files, 3,307,184,290 bytes; `sim.elf.zst` is
  3,296,554,196 bytes; 286 `executables/*.elf`.
- `tokenizer/`: tokenizer.json and generation_config.json, 11,422,893 bytes.
- Both phases have `serve_meta.json` and actual `sim_port_map.json`.
- Compressed artifacts have Zstandard magic; sampled executable headers have
  ELF magic `7f454c46`. Presence/format were checked, not a full checksum audit
  or a fresh device run. The cache also has build_manifest.json.
- Bundle manifest says `kind=real`, source e2e-pdSeparate `efa954d` plus
  uncommitted optimizations, envelope hash
  `c5955904d2fd271df1f0390d20c7a795f3a72720`. Binaries are git-ignored delivery.

## Historical evidence and its limits

`serving/request_config/smoke4/` contains device_verdict.json, device_trace.npz,
results.json and timing.json. Verdict says PASS, cached_reload, real WSE-3;
prefill and decode each completed 4 requests with compile_s=0.0. Reported load
times are 144.02s and 149.877s. These are historical stored measurements, not
this session's timing or a fresh execution. The smoke4 checks verify target,
round counts and trace bookkeeping; do not promote them to a new SD/rewind or
HF numerical correctness claim. README separately claims an older mtbench8
golden comparison; that comparison was not independently re-run here.

## SD compatibility changes the migration plan

This real bundle is ordinary e2e PD serving, not the SD batch/feedback runtime:

- `launch_decode.py:_serve_loop` (lines 2435–2906 in this server snapshot) sends
  the full per-request KV and first-token seed, then drains generation to
  termination before rearming for another prompt.
- Its KV metadata is `[ceil(prefix_len/P), prefix_len]` packed as two u16 values,
  rather than the SD eight-u32 LOAD_PREFIX/RESUME metadata.
- Decode serve_meta has `south_wavelets_per_step=2` (token ID + q) and no
  `max_draft_len`. Searching the decode host loop and host modules found no
  rewind / accepted_count / TargetFeedback / DraftBatch / LOAD_PREFIX / RESUME
  implementation. This establishes that the supplied host interface cannot
  directly perform the required SD feedback; it is not a binary disassembly.

Discuss migration against this **actual server delivery**, rather than completing
the stale GitHub mock API. A path change alone is insufficient. Options still
need agreement: adapt this delivery layout to the already-compiled rewind-capable
SD artifact pair, or obtain a matching SD-capable version of the new bundle.
Do not silently substitute full-prefix recomputation for the requested SD path.

## Subsequent scope clarification from Le

Le now requests: first assess binary-adoption changes; then migrate the kernel
integration to the intended repository's main implementation **without requiring
artifacts, retaining the original source-build approach**; after migration discuss
local GPU verifier setup, run the combined system, and only afterwards discuss
kernel-repository packaging. Do not treat the earlier suggested binary-reuse route
as an agreed implementation decision. The exact URL/kernel directory meant by
“this repo's main” was requested and is still pending at this checkpoint.

Concrete assessment is in
`nc_service/waferengine/samples/specdec/BINARY_ADOPTION_ASSESSMENT.md`.
The current SD service already reloads artifacts but its mandatory cache preflight
prevents a source-build bring-up with no existing serve_meta. Source-build and
binary-reload should produce the same SD runtime descriptor/contract; binary mode
additionally needs source-free manifest/digest/ABI validation. Generic gRPC and
transport need no rewrite just for binary delivery. No migration implementation
has started.

Read-only follow-up resolved an important candidate: both local WaferEngine
checkouts have origin `happyandslow/WaferEngine`. Remote main was verified with
ls-remote as `b136ab64b3f5575c72fb722fb972ef5c77f4c9fe`; its
`models/qwen3_1p7b-sd-pdSeparate` subtree's 54 files are byte-identical to the
nc_service vendored SD tree. If Le means that repo/module, no rewind algorithm
port is needed; source dependency and no-cache build bring-up are the migration.
The local WaferEngine main ref fcfc8c1 is stale, while WaferEngine-staging main
already points at b136ab64. Neither refs nor checkouts were modified.

## Ongoing test

Legacy baseline `wsjob-3inuefcthypuly8sujupvy` remained QUEUED at inspection.
Its 21,600s guard is still live (deadline 2026-09-10 17:48:54 UTC); no compile
or device execution has occurred in it. Its automatic legacy follow-up was
stopped earlier. No new job, kernel change, migration, or GPU setup was performed
for this inspection.
