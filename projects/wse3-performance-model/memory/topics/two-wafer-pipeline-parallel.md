# Two-wafer pipeline-parallel decode

- The 2026-09-03 two-wafer PP demo measured a per-hop price around 170-175 us; about 135 us is SDK stream floor, not tens of milliseconds.
- TSC calibration from the closed-loop run gives ~750 MHz. Prior 0.85/1.1 GHz converted rates should be relabeled as cycle counts before cross-artifact comparison.
- Transport/host stream knobs appear exhausted for this path; future work should price class-P2 hops and decide whether multi-wafer PP is worthwhile given stage period and capacity needs.
