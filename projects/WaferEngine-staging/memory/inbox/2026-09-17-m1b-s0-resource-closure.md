# M1b-S0 closure: distinguish linked resources from device timing — 2026-09-17

**Project:** WaferEngine-staging
**Author:** codex
**Status:** drained

## What happened / finding

- When resuming S0 from older memory, do not treat the Part 2/3 performance sweep or the resource report as still pending. S0 is COMPLETE on 2026-09-17 after the production resource gate supplemented the accepted Part 1-3 host/simulator/CS-3 evidence. S1 and M1-S4 remain open.
- Final production-ingress CS-3 validation covers equal-position byte-exact vs the frozen main baseline, ragged `[256,512]` and swapped `[512,256]` full-scale NumPy bf16 values, peer isolation, two-round rearm, and row wrap. The full Qwen3-1.7B geometry uses seeded synthetic tensors, not pretrained-weight accuracy evidence.
- Final frozen equal-position CS-3 timed-decode medians: 665,008 -> 680,457 cycles/token, +2.323%, n=12/10 successful runs, 502 failures excluded. This supersedes the intermediate Part 1 +2.36% number; it does not measure metadata/ingress latency.
- Local SDK 2.10 full-geometry WSE-3 compile-only, identical config/request, 286 distinct PE ELFs per side: decode-role maximum shared data 11,704 -> 11,752 B (+48); maximum `.text` 28,200 -> 29,592 B (+1,392). Other role maxima unchanged. No new simulator execution or CS-3 run. Do not claim identity with historical appliance binaries.
- Avoid two resource-accounting traps: numeric ELF suffixes are not stable coordinate IDs, and all SHF_ALLOC sections include MMIO/config, so their sum is not physical SRAM consumption/headroom. Compare independent role extrema, record witness ELFs, and keep task reservation (1,024 B) separate from occupancy. Named-state +40 B is not the full linked delta.
- Source state verified: branch `lexu/staging/m1b-s0-inner-batch-cb`, HEAD `5bb850489936cfb5f613292694b7fa45296dd693`, index empty; Part 2/3 source remains uncommitted and unchanged. Historical main baseline is `b136ab64b3f5575c72fb722fb972ef5c77f4c9fe`, not a fresh remote-tip assertion. No Git mutation or external sync was performed.

## Implications / next actions

- [ ] Start S1 only after separate contract/gate approval. S0 has static membership; no EOS lifecycle, continuation, admission/replacement, fixed-slot planner, or pipeline-context scheduling.
- M1-S4 closes only after S0/S1 are jointly re-verified with S5/K0 fixed-slot integration. Keep C1-M's measured negative result scoped to C1-M.
- Resource-report method is reusable, but no new skill is installed or proposed in this scoped closure; shared-data pool guidance already exists.

## Pointers

- `/home/lexu/WaferEngine-staging/docs/analysis/2026-09-17-m1b-s0-production-resource-report.md`
- `/home/lexu/WaferEngine-staging/docs/analysis/2026-09-03-m1b-s0-part23-validation-results.md`
- `/home/lexu/WaferEngine-staging/.s0-artifacts/m1b-s0-resource-report-20260917T094031Z/report/provenance.json`
- `memory/topics/m1b-decode-continuous-batching.md`
