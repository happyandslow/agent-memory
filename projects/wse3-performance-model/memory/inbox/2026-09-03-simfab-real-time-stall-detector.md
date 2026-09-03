# simfab aborts with "received length (0 bytes) … kernel stall" when the host does not service the device for ~90 s — a sim artifact, not a kernel bug — 2026-09-03

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

A two-process (or socket-driven) simfab run dies at the first
`runtime.receive` with `terminate called … the received length (0 bytes) is not
expected (N bytes), could be a kernel stall` (rc 134/139), while the identical
layout fed back-to-back from one process runs fine, and replaying the exact
same frames offline also runs fine. You are about to conclude the kernel or
the data path is broken.

## What happened / finding

- Reproduced with **no socket at all**: B standalone + a bare `time.sleep(90)`
  before the first `send` → same 0-byte stall. The cause is the wall-clock gap
  during which the host does not pump the SDK runtime (blocked in a Python
  socket recv waiting for the other simfab, ~30 s/step in sim). Real CS-3 has
  no such detector and produces a frame in ~ms — the same two-process lockstep
  ran 4,096 tokens byte-exact on hardware.
- What did NOT matter (each tested): blocking vs nonblock `send`, KV sent
  before/after `accept`, priming depth (1 frame is enough), data content.
- Validation recipe that works in simfab: dump wafer A's real frames from a
  standalone run (`PP_DUMP_Z`) and replay them into B standalone
  (`PP_REPLAY_Z`) — exercises the seam and the checker without two live sims.
- Also learned on the way: SdkLayout host streams attach only to single-PE
  ports (multi-PE ports need a 1×P mux/demux column); the shipped
  `demux.csl` already re-arms per frame (`next_cycle`), so per-step host X
  injection needs only a ready-barrier bypass, not a loop change.

## Implications / next actions

- [ ] Promotion candidate (procedural): add to `cerebras-debugging` — "0-byte
      receive after a long host stall in simfab = detector, verify with a bare
      sleep before blaming the kernel".

## Pointers

- `wse3-performance-model/demo/4b-pp-demo/sim/logs/b_sleep.log` (the bare-sleep
  repro), `sim/results/token_gates.txt`, `code/src/z_mux.csl`.
