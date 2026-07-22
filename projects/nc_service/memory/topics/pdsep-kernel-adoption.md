---
summary: Adopting PR#14 / PR#12 pdSeparate kernel changes the KV contract: mode-A serving only, chunk-major varlen KV bridge, no internal rewind; compiled reload artifacts are full 23 GB sim.elf images, not lightweight ELFs.
tags: [nc-service, waferengine, pdSeparate, kv-contract, csl-kernel, cs3, sdklauncher]
---

# pdSeparate kernel adoption notes

Curated from `memory/inbox/2026-07-21-pdsep-kv-contract-adopt.md` and `memory/inbox/2026-07-21-cs3-elf-extract-reload-scale.md`.

## KV contract changed: replace, do not relabel

The WaferEngine PR#14 / PR#12 `qwen3_1p7b-e2e-pdSeparate` kernel is **mode-A serving**: compile once / load many, one distinct prompt per round. It has no mode-B spec-dec rewind. Its KV meta uses only slot 0 (`prefill_len`); slot 1 is pad. The old mode-B continuation contract that used slot 1 as accepted position A does not exist in this kernel.

The transform also changes shape:

- existing nc_service mode-B transform: token-interleaved / strided decode placement, `p = seq_local*P + local_py`;
- PR#12 bridge: chunk-major contiguous placement that preserves prefill position→PE assignment and only reorders slots.

An offline diff on a small 2×2 fabric put writes in the same cells but only 96/192 seeded values matched; using the old strided transform with the new pdSeparate kernel would seed roughly half the KV from the wrong source position. Decision: the real-kernel mode-A path must use chunk-major `kv_bridge` logic; keep `kv_transform.py` for the mode-B rewind kernel only. Freeze the compare script (`kv_xform_compare.py`) as a regression test if this work continues.

## Compile artifact / reload reality

`launch_device.py` compile-only with `dl=[]` compiles both phases and downloads nothing; the ELF remains on the ephemeral worker. `download_artifact` cannot fetch run-time-created tarballs because it resolves against the uploaded staging snapshot. The working post-job path is:

```bash
csctl log-export <jobid> -b -c -p <dir>
```

`-b` is required for binaries / `executables/*.elf`; `-c` alone has metadata but no ELF. Use a long unzip timeout.

Reload is not lightweight. The SDK `SdkCompileArtifacts(...).add_port_mapping(...)` API exists in full `cs_python`, not the login-node `csl` client env. Flattened per-region ELFs are 1×1-fabric and cannot load on the appliance. The loadable whole-device image is `sim.elf`, about **23 GB per phase** (46 GB for prefill+decode), and mock weights are baked into it. Do not put this in the bundle git. Do R0–R5 validation on-cluster; keep the bundle at stub ELF plus real `port_map.json`.

The extracted `sim_port_map.json` remains useful: port/LVDS layout is structural and weight-independent, so it can be reused for the real-weight compile.

## Operational note

Prefer the persistent `ssh CS-3-cmd` ControlMaster for long artifact/compile sessions; repeated fresh gateway hops through `cs3-ssh.sh CS-3` were flaky, while the resident channel survived the session.

See also: [[specdec-cs3-roadmap]], [[specdec-modeb-drive-path]].
