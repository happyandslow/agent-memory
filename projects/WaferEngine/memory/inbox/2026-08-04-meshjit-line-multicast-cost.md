---
topic: pe-sram-memory-breakdown
tags: [waferengine, wse3, meshjit, multicast, tsc, prefill, sram]
date: 2026-08-04
status: drained
---

> **Status: drained** (2026-08-06 maintain pass) into the new topic
> `memory/topics/meshjit-code-relocation.md` §§ Hardware multicast cost / Real c512 function sizes
> / Exact-body function-use / Decision.

# MeshJIT physical line multicast cost and real-c512 function-use profile

Follow-on to the PR #14 SRAM profile and address-matched branch-relocation pass. This session did
not modify prefill. It measured (1) opaque function bytes broadcast by one WSE-3 router color to a
line of receivers and (2) exact-body use time for five phase functions inside the real Qwen3-1.7B
c512 graph.

## Hardware multicast result

Repo: `/home/lexu/MeshJIT/broadcast-timing/`. Physical CS-3, 0.85 GHz, full-fabric compile. The
algorithm is a single-color router line: holder `RAMP->EAST`; interior `WEST->{RAMP,EAST}`; endpoint
`WEST->RAMP`. The holder injects once. It is not sequential unicast, software relay, or a tree.
Receivers pre-arm async `@mov32` slot writes before the holder kick.

Timing uses the SDK bandwidth-test sync/tic/toc module. The sync broadcast is itself a wave, not a
simultaneous event. Each PE records its local 48-bit TSC in the sync completion task; host applies
`ref -= px+py` and reports `max(receiver_toc-ref) - (holder_tic-ref)`. This removes arbitrary TSC
offsets/reference-wave propagation, but intentionally leaves data propagation in the result.

Physical endpoint cycles (`shortest / median`; N<=256 has 200 repetitions, N=512 has 50):

| K | N=1 | N=16 | N=64 | N=256 | N=512 |
|---:|---:|---:|---:|---:|---:|
| 64 B | 39 / 62 | 53 / 77 | 101 / 125 | 293 / 318 | 549 / 574 |
| 256 B | 93 / 150 | 107 / 168 | 155 / 214 | 347 / 406 | 603 / 662 |
| 1 KiB | 309 / 358 | 323 / 372 | 371 / 420 | 563 / 612 | 819 / 868 |
| 2 KiB | 597 / 646 | 655* / 660 | 659 / 708 | 851 / 900 | 1107 / 1156 |

`*` The rare low dispatch mode was not sampled at 2 KiB/N=16; the fit predicts 611 cycles and the
same mode was observed at the other extents, including N=512.

The lower envelope is exact for all tested K (their u32 extents are divisible by eight):

```text
T_shortest(N,K_bytes) = 20 + 9*K/32 + (N-1) cycles.
```

Interpretation: serialization is paid once and the multicast wavefront advances one router hop per
cycle. It is pipelined hardware multicast, not `N*K`. At production row width N=512: 1 KiB is
819/868 cycles = 0.964/1.021 us; 2 KiB is 1107/1156 cycles = 1.302/1.360 us
(shortest/median). Completion-task dispatch creates a repeatable second mode, usually +49 cycles
for 1--2 KiB. Keep both minimum and median.

Raw JSON/CSV/plot and method: `~/MeshJIT/broadcast-timing/results/`, `RESULTS.md`.
ContextBase log: https://context.ed-aisys.com/doc/2026-08-04-result-meshjit-physical-multicast-cost-real-c512-use-time-7LlgIfgzCe

## Real function sizes (corrected)

Source is PR #14 commit `a8ab2a5073674ebaf3b661316ecdb5e06044f472`, real c512 configuration:
512x1024 compute block, P=256, sequence 8192, chunk 512. Tight PE `.text` is 30,664 B.

- Fourteen compute-core functions total **14,168 B**, not the old candidate page's 14,372 B.
- Five independent phase candidates: qk_norm 1936, silu 1768, rmsnorm 1532, matmul 876, rope
  776 B; total 6,888 B. One shared 1,936-B slot gives a theoretical gross saving of **4,952 B**.
- Nine attention-group functions total 7,280 B. They have call/dependency coupling and are not yet
  independently swappable; do not count this saving until closure/multi-slot placement is solved.
- The old `FUNC` dump's 31,688-B sum includes the separate 1,024-B task table. Non-stub FUNC sum
  equals `.text` exactly at 30,664 B.

Evidence: `/home/lexu/we-sram-profile/models/qwen3_1p7b-prefill/out_device_8k_c512_whole_tile_flash/executables/prefill-11.elf`,
`/home/lexu/we-sram-profile/prefill_text_funcs.txt`.

## Exact-body function-use result

Isolated profiler: `/home/lexu/MeshJIT/function-use-profile/`; CS-3 job
`wsjob-vuwqrxhrcxkzb2qetccra9` succeeded. It instrumented one representative PE at logical
(511,0) in a four-layer block during a full seq-8192 c512 request. Every count matched the state
machine; each interval subtracts an 18-cycle back-to-back TSC read.

| Function | Calls | Average cycles | Total cycles | Total @0.85 GHz |
|---|---:|---:|---:|---:|
| rmsnorm_kernel | 128 | 3549.13 | 454,289 | 534.46 us |
| qk_norm | 64 | 925.50 | 59,232 | 69.68 us |
| rope_kernel | 128 | 576.25 | 73,760 | 86.78 us |
| silu_chunk | 192 | 855.00 | 164,160 | 193.13 us |
| matmul_compute | 65,792 | 1148.19 | 75,541,967 | 88.873 ms |

Authoritative full-request device forward span: 430,044,189 cycles = 505.934 ms at 0.85 GHz.
Host `run` was 7.047 s; retain it only for end-to-end budget comparison.

With fixed payload buckets on the measured N=512 line, load/one-body-call is already >1 for
qk_norm, rope, and silu (1.20--1.51x median), so never fetch per leaf invocation. Matmul only wins
because one loaded body is reused for 257 step/final calls per projection.

## Full-block extrapolation and decision

Unmeasured 2-D hypothesis: a hardware comb over 512x1024 has longest route
`511+1023=1534` hops. Assuming branch fan-out preserves line throughput:

```text
1 KiB: 1842 / 1891 cycles = 2.167 / 2.225 us
2 KiB: 2130 / 2179 cycles = 2.506 / 2.564 us
          shortest / median
```

The real five-function phase order with one shared slot causes nine loads per layer-chunk:
rmsnorm x2, matmul x4, qk_norm/rope/silu x1. Over 4 layers x 16 chunks, extrapolated load cost is
1.335--1.368 ms. That is 0.264--0.270% of device forward, ~0.019% of the 7.047-s host run, and ~1.5%
of these five exact bodies' total time.

Decision/recommendation: **hardware router multicast + phase-granularity reuse is promising for the
five independent kernels; per-leaf fetch is not.** Next go/no-go is a measured 512x1024 2-D comb,
including coexistence with production traffic. Do not treat the 2-D numbers as measured.

Production resource caveat: experiment uses color 6 plus IQ5/OQ5. Color 6 is stage-free in the
qk_norm/rope/swiglu snapshots, but production already binds all 8 input and output queues. A real
integration needs drained repaint/rebind/fence; there is no globally free dedicated queue pair.

Function-timing caveat: exact body, not end-to-end phase. `matmul_compute` excludes async fabric
wait in later task-unblock paths and mixes MAC-step with final-cast calls. Only one PE was profiled;
no uninstrumented A/B baseline was run.

## Next

1. Build and TSC-measure one-color 2-D comb on a production-size rectangle; verify max Manhattan
   path model and row-branch contention.
2. Audit a concrete production repaint/rebind schedule and its fence cost.
3. Prototype the five-kernel shared address-matched slot at real phase transitions.
4. Treat attention as a closure-placement problem, not nine independent functions.

Related: [[pe-sram-memory-breakdown]], `2026-08-04-meshjit-branch-relocation.md`.
