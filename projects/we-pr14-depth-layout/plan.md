# we-pr14-depth-layout Plan

Human-maintained roadmap and durable progress narrative. This is the canonical home for project
goals, milestones, decisions, and next actions. Generated/current status belongs in
`tracking/status.md`.

## Goals

- Increase Qwen3-1.7B standalone-decode pipeline depth (toward one layer per stage) to unlock
  decode-side pipelined prefill, while keeping the 8,192-token KV capacity on the PR14 line.
- Quantify the depth-vs-cost tradeoff honestly on real CS-3: throughput, max context, and per-PE
  SRAM, separating device-authoritative measurements from sim-only completion checks and from
  arithmetic upper bounds.

## Milestones

- [x] Device-size compile of a one-layer-per-stage `64 x 256` rectangular decode layout (28 stages)
      that fits (44,794 / 49,152 B tightest decode PE, 8.9% free).
- [x] Device profile of decode throughput + max context for baseline `256 x 256` vs `64 x 256`.
- [ ] Real-CS-3 correctness + throughput validation of the `64 x 256` layout.
- [ ] Fit a `128 x 128` one-layer layout by changing HT geometry + adding `256 <-> 128` hidden
      redistribution (config-only cannot fit — HT embedding wall).
- [ ] Implement and measure an actual pipelined-prefill run to replace the depth upper bound.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-08-06 | Report the deeper-layout pipelined-prefill product (per-stage tok/s x n_stages) only as an upper bound, never as achieved throughput. | The product assumes every stage accepts independent prefill tokens at the steady-state decode interval with no fill/drain/dependency/collective/IO bottleneck. | `memory/topics/decode-pipeline-depth-layout.md` |
| 2026-08-06 | Treat CS-3 device (1.13.2) artifacts/measurements as authoritative over local SDK-2.10 sim. | Sim and device artifacts are not byte-identical; sim smoke tests validate completion/routing only. | `memory/topics/decode-pipeline-depth-layout.md` |

## Next actions

- [ ] Test the `64 x 256` layout for correctness and throughput on a real CS-3.
- [ ] Evaluate `128 x 128` decode blocks with a changed HT geometry and explicit `256 <-> 128`
      hidden-vector redistribution; changing only the config cannot fit.
- [ ] Investigate changing HT geometry/size to relieve embedding SRAM pressure.
- [ ] If one-layer layouts remain unsuitable, evaluate the `128 x 256`, 16-stage fallback
      (twelve 2-layer blocks + four 1-layer blocks).
- [ ] Validate the decode-derived pipeline-prefill upper bound with an actual multi-token
      pipelined-prefill implementation before reporting it as achieved.

## Narrative progress log

### 2026-08-06

- Scaffolded this project during the maintain pass and drained two dated depth-layout captures into
  `memory/topics/decode-pipeline-depth-layout.md`:
  `projects/WaferEngine/memory/inbox/2026-08-06-qwen3-1p7b-decode-pipeline-depth-profile.md`
  (CS-3 throughput/max-context/prefill profile) and
  `projects/WaferEngine-staging/memory/inbox/2026-08-05-decode-one-layer-rectangular-layout-sram.md`
  (layout/SRAM feasibility). Headline: the one-layer `64 x 256` layout fits but costs 22.6–24.5%
  decode throughput and 42.52% max context vs the 8-stage `256 x 256` baseline; the square
  `128 x 128` fails first on HT embedding SRAM (75,968 B/HT-head PE > 49,152 B).
