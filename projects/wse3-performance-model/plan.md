# WSE-3 Performance Model Plan

Human-maintained roadmap and durable progress narrative.

Agents may propose edits, but should not overwrite this mechanically. Generated/current status belongs in `tracking/status.md`.

## Goals

- Track all WSE-3 measurements together with the exact implementations and run
  conditions that produced them.
- Analyze measured results and extract appropriate component-level abstractions.
- Build and validate composable performance models for compute, storage, and
  communication.

## Milestones

- [x] Create the project workspace and register it in agent-memory.
- [x] Establish the provenance structure linking implementations,
  measurements, analyses, models, and validation.
- [ ] Add the first real WSE-3 implementation and reproducible measurement.
- [ ] Define the first component breakdown from measured data.
- [ ] Build and validate the first compute/storage/communication model.

## Decisions

| Date | Decision | Rationale | Link |
| --- | --- | --- | --- |
| 2026-08-27 | Use real WSE-3 measurements as the foundation of every model. | Keeps abstractions auditable and prevents estimates from being mistaken for hardware evidence. | `/home/lexu/wse3-performance-model/README.md` |
| 2026-08-27 | Organize evidence as implementation -> measurement -> analysis -> model -> validation. | Gives every model parameter and claim an explicit provenance path. | `/home/lexu/wse3-performance-model/README.md` |

## Narrative progress log

### 2026-08-27

- Created the project workspace scaffold and shared agent-memory project.
- Recorded initial goals, evidence rules, and the first three milestones.


### 2026-09-07 — maintain pass drained active modeling backlog

- Drained 41 captured inbox notes from 2026-08-27..2026-09-05 into seven topic packets. The project now has durable memory for automation/Git safety, Wavel provider contracts, Qwen3-4B SRAM/capacity levers, CS-3 measurements, trace/KV economics, two-wafer PP, and CS-3/simfab operational gotchas.
- Current evidence has moved beyond the original scaffold: Qwen3-4B SRAM breakdowns, context-cost measurements, trace-demand studies, and two-wafer PP hop timings are now recorded as source-linked topic memory. Treat individual rates as measured under their named artifacts/configs and verify live repo state before reusing them.

### 2026-09-08 — maintain pass drained thin-block/stacking capture

- Drained the 2026-09-06 thin-block capture into `memory/topics/qwen3-4b-cs3-measurements.md`: L=4/L=2/L=1 thin-stage rungs, KV stride-cap lift, calibrated context-capacity model, and vertical ATTN/FFN stacking evidence are now source-linked topic memory.
- Current open modeling questions from that capture are the A1 stall, whether to build/measure the second stacked lane, and the scoped 128² two-lane width-axis family.
