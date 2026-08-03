# WaferEngine-staging Weekly Progress — M2 Prefix-Reuse Study

```text
Metadata
Project: WaferEngine-staging
Page Type: Log
Status: Active
Owner: Le Xu
Last Updated: 2026-08-03
Summary: Weekly synthesis of the measured M2 resume strategies, corrected Lane B contract, performance-model implications, and the M1 cursor.
Tags: M2, KV reuse, force decode, KV reload, prefill, WSE-3, performance model
Related Links: https://context.ed-aisys.com/doc/m2-experiment-register-index-results-three-lane-design-X3DIdKV2s4
```

## Executive summary

This week turned the M2 three-lane study from a single crossover claim into a more careful performance model:

- **Lane A — force-decode/recompute:** the steady token interval grows with absolute sequence position, but only gradually. Most of the large prefix-dependent `F=1` span is startup/readiness and pipeline fill, not the compute cost of one steady forced token.
- **Lane B — full target-KV reload:** the measured H2D path has a roughly 46 ms floor, followed by a payload-dominated region reaching 3.186 GB/s aggregate. Reloading a complete 8,192-token target KV costs 338.266 ms.
- **Lane C — re-prefill on the prefill card:** the current screening composition is slower than Lane B in both 8,192-context cases tested. This is a screening result, not yet an exact pdSeparate implementation.
- **Most important correction:** current Lane B reloads the **complete target KV**. It performs no forced reconstruction. The next free-decode token is common to Lane A and Lane B and is excluded from the comparison.
- Therefore the earlier **~700-token A/B crossing is not the current policy boundary**. It belongs to the older E10 delta-reload fixture and must be recomputed under the full-target-KV contract.

## Key measured results

### Lane A: force-decode is position-dependent, but startup dominates short spans

Observed end-to-end forced-decode spans:

| Starting prefix | `F=1` span | `F=256` span |
| ---: | ---: | ---: |
| 256 | 22.0 ms | 40.9 ms |
| 1,024 | 26.4 ms | 46.4 ms |
| 4,096 | 110.4 ms | 125.3 ms |
| 8,192 | 224.2 ms | 248.0 ms |

The stable marginal interval obtained from the longer `F=256→512` segment is:

| Prefix | Marginal forced-token cost |
| ---: | ---: |
| 256 | 74.15 µs/token |
| 1,024 | 76.64 µs/token |
| 4,096 | 89.47 µs/token |
| 8,192 | 108.68 µs/token |

The fitted steady interval is:

```text
II(q) = a + bq
a = 71.745198 µs
b = 0.004093307 µs/position
```

For a forced span starting after prefix `P`:

```text
T_steady(P,F) = Σ[j=1..F-1] II(P+j)
```

The full observed model uses a **prefix-specific anchor**, rather than treating `F=1` as a universal compute offset:

```text
D(P,F) = D(P,256) + Σ[q=P+256..P+F-1] II(q),  F ≥ 256
```

Takeaway: forced-token compute does become more expensive at long positions, but the large prefix effect in short observed spans comes mainly from readiness/initialization and pipeline fill. Timing conversions use the WSE TSC at **0.85 GHz**.

### Lane B: reload has a floor and then a clean payload regime

The six measured ingress anchors show a hockey-stick shape:

| Complete KV length | Measured ingress span |
| ---: | ---: |
| 256 | 46.150 ms |
| 512 | 46.236 ms |
| 1,024 | 56.141 ms |
| 2,048 | 85.684 ms |
| 4,096 | 169.891 ms |
| 8,192 | 338.266 ms |

- A roughly **46 ms fixed floor** dominates the smallest payloads.
- The large-payload region is almost perfectly linear.
- Saturated aggregate throughput approaches **3.186 GB/s**.
- A complete **8,192-token target KV reload costs 338.266 ms**.

Under the corrected current contract:

```text
B_full(S,H,L_new) = I(P_target)
P_target = S + H + L_new
```

There is no force-decode term in Lane B. If `G(P_target)` denotes the next free-decode step, it is common after either resume lane and is excluded from both sides.

### Lane C: current screening result is negative

At total target context 8,192:

| History / new context | Resident-prefill compute | Lane C composed estimate | Lane B full reload |
| --- | ---: | ---: | ---: |
| 7,936 / 256 | 292.935 ms | 654.8 ms | 338.266 ms |
| 7,168 / 1,024 | 409.636 ms | 929.7 ms | 338.266 ms |

The current Lane C composition loses in both cases. However, it combines measured S6a prefill compute with transport evidence rather than measuring the exact pdSeparate implementation end to end. The exact port is therefore optional confirmation, not evidence already in hand.

## Key takeaways

1. **Do not use one universal “forced token cost.”** Separate prefix-dependent startup/readiness, pipeline fill, and the position-dependent steady interval.
2. **Do not subtract `F=1` as a universal initialization constant.** Use measured prefix anchors and add steady intervals beyond the anchor.
3. **Lane B semantics determine the boundary.** Full-target reload and delta reload are different mechanisms; formulas and crossing experiments cannot be mixed between them.
4. **The old ~700-token crossing remains valid only for the E10 delta-reload fixture.** It is not yet a policy boundary for the current full-target-KV Lane B.
5. **Current Lane C is not competitive in the screened 8,192-context cases.** Transport optimization alone cannot erase the measured prefill-compute gap.
6. **Report raw observations beside model-derived conclusions.** The experiment supports a workload- and implementation-dependent segmented policy, not a universal threshold.

## Next actions

### M2 closeout

Treat M2 as one closeout work item:

- reconcile the register, equations, and crossing plot with full-target-KV Lane B;
- finish the E14 startup/short-`F` measurement and obtain a clean repeat where needed;
- complete the E11 cross-card Lane C cost synthesis;
- build E13 decode egress only if the policy claim requires full eviction round-trip latency;
- keep E12b gated and treat the exact E12a port as optional confirmation.

### M1 cursor

M1-S0 and M1-S1 are complete. The remaining dependency chain is:

1. **M1-S2:** host per-slot `valid_len`; retain and extend correctly as the active slot set changes.
2. **M1-S3:** prefix hits, skip-prefill, LRU replacement, miss rebuild, and partial-hit truncation.
3. **M1-S4:** requests-per-bank capacity curve near the PE SRAM limit and slot-addressing overhead.
4. **M1-S5:** end-to-end full-hit, partial-hit, miss, and eviction verification against the teacher-forced oracle.

## Evidence and scope

- Primary study register: [M2 Experiment Register](https://context.ed-aisys.com/doc/m2-experiment-register-index-results-three-lane-design-X3DIdKV2s4)
- Weekly slides: [2026-08-02.pptx](./2026-08-02.pptx)
- M1 source of truth: `/home/lexu/WaferEngine-staging/milestones/M1-intra-pe-reuse.md`
- TSC conversion used here: 0.85 GHz.
- No current result includes a measured decode-to-host eviction path; full offload round-trip remains unpriced.
