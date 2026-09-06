---
title: MeshRT paper-result provenance gaps at meshrt 5d47163
project: WaferEngine-staging
author: codex
status: captured
date: 2026-08-25
---

## Situation

While reconciling SOSP26 MeshRT section 6 with the public `meshrt` branch at commit `5d47163b6586824a9fce5ff045bff67d9f0f6552`, the repository did not provide an end-to-end multi-wafer runner or raw result bundle that regenerates `MeshRT/Benchmark/*.json`.

## Durable finding

- Model launchers run one component/configuration at a time. `benchmark_device.py` may schedule independent configurations on several wafers, but it is not a distributed model execution.
- Consolidated benchmark JSONs compose full-model estimates from component device-TSC measurements and explicitly exclude inter-wafer hidden-state transfer and host transport.
- The paper's Qwen3.5-35B decode system throughput of 63,274 tokens/s is absent from the current formal result matrix; the matching per-user point is present, but the current JSON reports 17,058.763 tokens/s system throughput. The paper calls 63,274 a compact projection, while the repository says the compact path is not adopted and contains no corresponding implementation/result record.
- The paper labels Qwen3.5-35B as FP8, whereas the current implementation documents packed GPTQ-int4 routed-expert weights with BF16 execution. This must be reconciled before claiming code-to-paper reproducibility.

## Implication

For a reproducible paper artifact, preserve raw device records/job identifiers, add the composition script or manifest that generates every published table cell, document each wafer placement, and resolve the Qwen3.5-35B compact-result and precision-label drift.
