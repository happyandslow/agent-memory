# M3 Multi-Row On-Chip KV Offload — Full Weekly Report (2026-08-24)

Audience: the agent that orchestrates/edits the weekly deck
(`meetings/2026-08-24-src/m3_multirow_weekly.pptx`, spec `deck.json`), and any
reader needing the complete record. Every number below is a real WSE-3
measurement (EPCC CS-3, SDK 2.10/1.13.2) unless explicitly labeled
projection. Cycles are authoritative; µs at 0.85 GHz (project decision, Le
2026-08-23); token-equivalents use the clock-free decode anchor 720,445 cyc.

## 0. Figure inventory (slide ↔ source)

| deck slide | figure file | source of truth |
|---|---|---|
| 2 (goal recap) | `figures/recap_e10d.png` | M2 E10D, `agent-memory/.../assets/2026-07-31-e10-ab-boundary/` |
| 3 (implementation) | `figures/v4_vs_v5.png` | **editable**: `WaferEngine-staging/docs/diagrams/m3-multirow-v4-vs-v5.excalidraw` (SVG/PNG derived) |
| 5 (same-law fit) | `figures/fig_samelaw.png` | `figures/fig_samelaw.py` (data inline, from the two device matrices) |
| 6 (v4 equation + topology) | `figures/fig_v4_model_topology.png` | `figures/fig_v4_model_topology.py`; topology crop derives from the editable slide-3 Excalidraw source |
| 7 (router vs CE) | `figures/fig_router_vs_ce.png` | `figures/fig_router_vs_ce.py`; coefficients from v3/v4/v5 device fits |
| 8 (tier tradeoff) | `figures/tier_tradeoff.png` | `agent-memory/.../assets/2026-08-24-m3-tier-tradeoff/fig_tier_tradeoff.py` |

Slide 4 carries its results table directly in `deck.json`; slides 6--7 are
generated from the fitted coefficients recorded below. All numbers cross-check against
`column_cycle_demo_multirow_v5/results/PREREGISTRATION-multirow.md`
(the authoritative tracking doc, work repo, branch
`lexu/staging/m3-on-chip-kv-offload-study`).

## 1. Goal and milestone position (slide 2)

- M1 (done): in-PE KV reuse — tier 0, KV resident in compute-PE SRAM.
- M2 (done): priced resume two ways, all device-measured. Lane A recompute =
  77.4 µs/token (E10D two-point: 768 tok → 57.32 ms, 1280 → 96.96 ms);
  Lane B host reload = E5 ingress I(H): 46.1 / 46.24 / 56.14 / 85.69 /
  169.89 / 338.27 ms at H = 256..8192, plus a measured L_new=256 delta of
  19.05–20.17 ms that cancels across lanes (E10 cancellation, ratios
  0.97–1.00). Crossing H* = 744 tokens (E10; flip confirmed head-to-head in
  E10D).
- M3 (this line): can idle on-chip PEs hold parked KV as a middle tier?
  Single-row park/reload protocol was device-proven earlier (51 runs; the
  coefficients below). Multi-row is REQUIRED for capacity: one storage PE
  usable SRAM ≈ 44 KB ≈ 11K u32 words; a band needs bh·E ≤ 11K, so with
  N=256, lpb=4: L=1024 (E=64) needs R=2, L=8192 (E=512) needs R≈12. This
  week: build multi-row BOTH candidate ways, measure both, fit both, and
  place the tier on the M2 tradeoff chart.

## 2. Implementations (slide 3)

Common core (v3, device-proven): one borrowed color (1 = decode
reduce_1st_color_0, IQ3/OQ3). Park = nearest-first funnel (each PE injects
its E-word block then opens its door N→S via CE rewrite); P0 ends park with
a NO_POP broadcast SWITCH_ADV sweep (advances every compute PE to its
reload-TAKE switch position + terminates at storage as the tail). Storage
gates reload on a two-predicate join (exact word count AND sweep tail),
flips its route RAMP→N, and emits per owner: E data words + a TURN control
wavelet (router advance flips that owner TAKE→FORWARD), then one fence
(task mode). dsd mode = owner-side bulk fabin-DSD receive (Exp-B): TURN CE
taps suppressed (ce_ignore — a microthread-claimed queue delivers no
control-task activations), no fence; read-completion is the end event.

**v4 GO-chain** (`column_cycle_demo_multirow_v4`): R bands top-down, band k
↔ storage row k (far band ↔ shallow row), R sequential epochs. Epoch
hand-off rides a dedicated GO color (9): tap-and-forward southward
(route N → RAMP+S — single rx, tx bitmask); the band top emits GO(epoch+1)
after its own completion, which is a causal fence on the protocol color.
At each GO tap, PEs re-program roles (participant / transit / done) by
DIRECT switch-position byte writes: byte = in_sel<<5 | out_bits
(S→RAMP = 0x50, S→N = 0x48), pos1 = reg0[7:0], pos2/pos3 = reg1[7:0]/[15:8]
— a workaround for a tile_config library bug (`set_rxtx_switch_pos` writes
tx bit 3 (N) instead of bit 4 (RAMP); register-dump proven against painted
ground truth). Storage rows are painted switchless (endpoint
advance-immunity); transit positions are created at runtime. A go_head
helper PE above P0 hosts the host GO(0). Known cross-color hazard class
(GO is NOT ordered behind other colors) was found and fixed in sim:
gather-route claims moved to export time; row-0 self-export is a
two-predicate join. First-ever v4 silicon this week — everything works at
256 PEs.

**v5 cascade** (`column_cycle_demo_multirow_v5`): compute column and
column↔storage interface are BYTE-IDENTICAL to v3 (`cmp` = 0). Row 0 keeps
the nearest band (owners N−1..N−bh) and store-and-forwards every deeper
word to row 1 on a strip-internal hop color; each deeper row keeps its
band, forwards the rest; the deepest keeps all. After (sweep tail AND full
stream validated), row 0 sends one STRIP_TAIL word (0xD05A50AC) down the
same hop color — same OQ FIFO ⇒ causal end-of-stream marker. Reload
returns up mirrored hop colors: each row plays its own pre-formatted block
(owner<<16 | 0x8000|seq, owners descending) BEFORE relaying its deeper
neighbour — task atomicity + per-OQ FIFO give the global owner order — and
row 0 synthesizes all TURNs (one per completed E-block, ce_ignore=dsd) and
the fence. Every strip route is static (rx one input, tx one direction):
no switch positions, no runtime rewrites, no cross-color ordering hazards
by construction (source-contract tests assert this). Hop-color budget caps
R ≤ 8 (2·(R−1) colors from id 10; routable 0–23); guard in launch.py.

## 3. Device experiments and results (slide 4)

Protocol: preregistered matrices
(`PREREGISTRATION-multirow.md`, hypotheses written BEFORE runs), one-case
validation before each batch, detached nohup+setsid driving, per-run wsjob
ids + source md5s in the result JSONs. v5 matrix: R∈{1,2,4} × E∈{4,64,512}
task + E∈{64,512} dsd, n=3 → 45 runs (sources commit c50b94b). v4 matrix:
R∈{1,2,4} × E∈{64,512} × {task,dsd}, n=3 → 36 runs (sources commit
b03bd6c; per-file meta says "2ffe1f6" — placeholder, correct is b03bd6c).
**81/81 first-attempt OK, zero infra failures, every cell 0-cycle spread.**
v4 metric = epoch_sum of per-band band-top spans (excludes inter-epoch GO
gaps, bounded ~2·bh cyc each); v5/v3 metric = P0 full-cycle TSC.

Full-cycle cycles (mean of n=3):

Slide 4 presents the benchmark axes in model-facing units rather than the
internal `N/E/R` notation. The fixed compute-column height is `N=256` PEs.
At `lpb=4`, `E=64` u32 words per compute PE represents a 1,024-token KV
history and `E=512` represents 8,192 tokens. `R` is the number of 1×256
storage rows. The current capacity label is explicitly **nominal analytical
sizing, not compile-fit evidence**: 42 KiB per storage PE gives 672 logical
KV-token equivalents per row/block, so `R=1/2/4` exposes 672/1,344/2,688
token-equivalents. Consequently, 1,024 tokens nominally needs two rows and
8,192 tokens needs about thirteen. These demos verify movement and do not
retain the full payload, so capacity-undersized cells remain valid movement
measurements but are not deployable storage profiles.

task | E | v3 | v5 R=1 | v5 R=2 | v5 R=4 | v4 R=1 | v4 R=2 | v4 R=4
---|---|---|---|---|---|---|---|---
 | 4 | 63,157 | 63,609 | 101,153 | 117,080 | – | – | –
 | 64 | 1,388,470 | 1,420,244 | 1,675,327 | 1,812,526 | 1,535,920 | 1,544,946 | 1,550,855
 | 512 | 11,366,325 | 11,497,424 | 13,465,018 | 14,609,701 | 12,545,967 | 12,612,336 | 12,646,916

dsd | E | v3(ExpB) | v5 R=1 | v5 R=2 | v5 R=4 | v4 R=1 | v4 R=2 | v4 R=4
---|---|---|---|---|---|---|---|---
 | 64 | 927,706 | 945,596 | 1,485,535 | 1,687,073 | 1,078,305 | 1,088,467 | 1,096,654
 | 512 | 7,350,234 | 7,482,812 | 10,669,498 | 12,343,610 | 8,542,434 | 8,619,349 | 8,675,026

Row-0 park spans (v5 task; the c_fwd fit input): R=1: 726,106 / 5,772,378
(E=64/512); R=2: 973,125 / 7,739,972; R=4: 1,114,084 / 8,884,196.

## 4. Performance models — terms, fitting, results (slides 5–6)

Verdicts on the preregistered hypotheses (all productive):
- H1 FALSIFIED: v5 R=1 sits +0.72/+2.29/+1.15% (task E=4/64/512) and
  +1.93/+1.80% (dsd) above the v3 anchors — the cascade's per-word branches
  do not compile out. Lesson: every implementation carries its OWN
  degenerate-case baseline; never diff against another implementation's
  anchors. (v4's R=1 is +8–11% above v3 for the same reason, larger.)
- H2 FALSIFIED IN FORM: v4's multi-row overhead is not a per-epoch
  constant; it is ALSO linear in forwarded words — just router-priced.
- H3 CONFIRMED (E≥64): both designs' Δ vs their own R=1 is linear in
  fwd_words = (N − N/R)·E, slopes R- and E-consistent.

Fitted models (`perf_model.py`, three predictors, selftest over 39 device
anchors: v3 0.89% / v5 0.83% / v4 0.23% max error; valid E≥64, E=4 sits in
the floor regime — v5 E=4 cells run +22k/+30k above the linear law):

```
v3: t = (245.4·N + 326) + (E−4)·N·(86.3 | 56.0) + 2·(D−1)·2.0
v5: t = (70,561 | 70,076) + (E−4)·N·(87.87 | 57.00) + (30.7 | 47.0)·fwd + [dsd R>1: 157k]
v4: t = (61,058 | 78,676) + (E−4)·N·(96.00 | 65.08) + (1.06 | 1.29)·fwd
        (pairs are task | dsd; N=256 floors, scale ∝N when extrapolating)
```

Fit methods per coefficient:
- v5 floor/marginal: exact 2-point solve on its own R=1 cells (E=64,512).
- tax_v5 = 30.7 (task) / 47.0 (dsd): slope of Δ vs fwd_words across
  R∈{2,4}, E∈{64,512}; task intercepts ≤10k cyc; dsd intercepts 153k/162k
  ⇒ the extra as-built constant ≈157k (strip rows emit their own block
  before relaying; exposed when owners are fast; strip emit spans are
  backpressure-coupled, 40→120 cyc/word with row depth — same caveat class
  as v3's emit span).
- c_fwd_word = 75.4 ± 0.9: park-span decomposition
  (span − kept_rate·kept)/fwd, four cells agree (74.1/74.5/75.7/75.9);
  ABOVE the preregistered [45,70] band — forwarding costs a full extra
  data-task dispatch, not an emit-loop increment.
- c_relay_word ≈ 28.8: from tax_dsd = (c_fwd−44.2)+(c_relay−13.0);
  cross-check: implied tax_task = 31.2 vs measured 30.7 (1.6% agreement
  across modes).
- v4 floor/marginal: 2-point solve on v4's R=1; tax_v4 = LSQ over 8
  deltas, residuals ≤0.25% of cycle.

Headline (slide 5 figure): **same law, Δ = tax × fwd_words; the
coefficient is the mechanism** — v4 router transit 1.06/1.29 cyc/word vs
v5 CE store-and-forward 30.7/47.0, i.e. 25–35× apart. The CE-vs-router
dichotomy is now measured four independent ways (43.3 park receive, 75.4
receive+forward, 13.0 emit loop, ~1.1 router transit) — the design rule
for any future on-chip transfer mechanism.

Design decision guidance: v5 wins R=1 (premium +1.6 cyc/word vs v4's
+9.6); v4 wins every R≥2 cell (dsd E=512 R=4: 30% faster). Real
deployments need R≥2 (capacity math) ⇒ v4-style router transit is the
deployment mechanism; v5 remains the minimum-intrusion option. Obvious
hybrid: v4's transit + v5's static compute column (~1.6 baseline + ~1.1
tax) would dominate both — open design question.

### Slide 6: v4 equation, fit, and topology

Slide 6 intentionally keeps only v4 because it wins every measured `R>=2`
cell. It presents the model form before substituting numbers:

```
C_v4(N,E,R,m) = C_floor[m]
              + (E-4) N C_owner[m]
              + W_fwd(N,E,R) C_router[m]
W_fwd = (N-N/R) E,    m in {task, owner-DSD}
```

The fitted coefficients for `N=256`, `E>=64` are:

| coefficient | task | owner DSD | interpretation |
|---|---:|---:|---|
| `C_floor` | 61,058 | 78,676 | launch/control and role setup |
| `C_owner` | 96.00 | 65.08 | ordinary endpoint path, cycles/payload-word |
| `C_router` | 1.06 | 1.29 | router-only multi-row tax, cycles/forwarded-word |

The right panel shows the corresponding v4 GO-chain topology at `R=2`:
one band is done, the next band participates, storage row 0 is transit, and
storage row 1 is the active endpoint. The additional words stay in router
routes; they are not consumed and re-emitted by the transit PE's CE. The v4
metric is still `epoch_sum` and excludes the small inter-epoch GO gaps.

### Slide 7: router-only versus CE processing

“Router-only” has an exact meaning here: a wavelet enters a fabric switch and
leaves through another directional output without a RAMP output, IQ/task
activation, CE execution, or local-memory copy/re-emission. It is not free:
it occupies fabric links and can backpressure. The measured terms are:

- distance pipeline latency: `t_hop_router≈2.0 cycles/hop` per direction,
  giving full-cycle `2(D-1)t_hop_router` (`+28` raw cycles at `D=8`, `+124`
  at `D=32` relative to `D=1`);
- v4 multi-row forwarded-word tax: `1.06/1.29 cycles/word` in task/DSD.

CE per-word processing is much larger: storage emit loop `13.0`, reload relay
about `28.8`, park receive `43.3`, and receive+validate+forward `75.4±0.9`
cycles/word. These are pipelined stages, so throughput is governed by the
binding maximum rather than an unconditional sum. The isolated demo blocks
compute at the round boundary; it does not yet measure concurrent decode/CE
interference.

Placement therefore has two qualitatively different effects. Extra pure
router hops add the small distance term in the measured range. A topology
that forces transit data into a storage CE changes the mechanism class and
pays tens of cycles per forwarded word.

## 5. Tier tradeoff (slide 8)

Resume span decomposes as transfer(H) + Δ(L_new), where Δ is
lane-independent (E10 cancellation) and ≈19.6 ms at L_new=256. The three
transfer options at H=256..8192:
- A recompute: 77.4 µs × (H+L_new) → 40..650 ms.
- B host ingress: I(H) = 46..338 ms.
- C on-chip strip reload (measured share = full − park, v5 R=1 dsd):
  219,773 cyc @E=64 and 1,710,717 @E=512 ⇒ 13.0 cyc/word ⇒ **0.06–2.0 ms**
  (per-block columns transfer in parallel; multi-row adds v4-tax ≤1.3
  cyc/word).

Consequences (all visible in the figure):
1. C is 46–170× below B's I(H) and beats A for essentially any parked
   history; the old H*=744 crossing demotes to a fallback rule for
   UN-parked history.
2. C's curve is flat at the Δ floor ⇒ resume latency is now
   Δ-dominated (transfer is 0.3–9% of C's span; Amdahl: zeroing it saves
   ≤10%). The next resume-latency lever is the delta/restart path
   (77.4 µs/token forced-decode, per-request fixed work, or prefetch
   overlap), not the transfer.
3. Tier economics: a swap cycle costs ≈ L/692 token-equivalents as-built
   (v4-dsd marginal 65.08 × 16 words/token = 1,041 cyc/token of context);
   projected L/~3000 after the storage-side DSD rungs (park receive 43.3
   and emit 13.0 are still CE-per-word; the owner side is already DSD'd —
   projection assumes residual marginal ~15 cyc/word, between as-built and
   the 39×-under-used wire).
4. Tier table: T0 in-PE resident (free, scarcest SRAM) → T1 on-chip strip
   (this study; deterministic, host-free, per-column-scalable; capacity
   R×~11K words/column) → T2a recompute (tiny/un-parked history only) →
   T2b DRAM (capacity overflow; shared edge IO + host).

Caveats stated with the claim: Δ floor is L_new=256-specific (scales at
77.4 µs/token; L_new→1 shrinks it); throughput view still wants the
storage-DSD rung even though latency doesn't; not yet measured: concurrent
decode interference (demo runs isolated; real Mode-L shares colors 1–4 in
round gaps — end-of-protocol color reconfig safety is the original M3
requirement), the per-scenario round-gap fit, and a directly-measured
prefill-recompute curve for T2a at large L.

## 6. Data/provenance pointers

- Tracking doc (predictions + verdicts + consolidated record):
  `models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo_multirow_v5/results/PREREGISTRATION-multirow.md`
- Matrices: `.../column_cycle_demo_multirow_v5/results/2026-08-23-multirow/`
  (45 JSONs), `.../column_cycle_demo_multirow_v4/results/2026-08-23-v4-matrix/`
  (36 JSONs) — wsjob ids and source md5s inside.
- Models: `.../column_cycle_demo_multirow_v5/perf_model.py`
  (`--selftest`, `--predict-multirow R`).
- ContextBase: "M3 park/reload as-built performance model" page (📐),
  sections 2026-08-23 ×2 + 2026-08-24 consolidated record.
- Diagrams (editable): `docs/diagrams/m3-multirow-v4-vs-v5.excalidraw`,
  `docs/diagrams/m3-go-chain-coverage.excalidraw`,
  `docs/diagrams/m3-multirow-band-epochs.excalidraw`.
- M2 inputs reused: `milestones/M2-experiment-register.md` (E5/E9/E10/E10D),
  `agent-memory/.../assets/2026-07-31-e10-ab-boundary/`.
