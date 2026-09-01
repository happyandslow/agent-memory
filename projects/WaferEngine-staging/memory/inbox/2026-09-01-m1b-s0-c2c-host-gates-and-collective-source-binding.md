# M1b-S0 C2c host gates and collective source binding — 2026-09-01

**Project:** WaferEngine-staging
**Author:** codex
**Status:** captured

## What happened / finding

### Durable contract

Collective arithmetic order must be bound to both the implementation function
and its routing source.  `comm_pe.csl` defines the receive sequence by fabric
color, while `route_calc.csl` maps each color to a physical left/right sender
for the current PE parity.  Floating-point reduction is order-sensitive, so a
host oracle that binds only the reduction function but not the color-to-route
mapping can silently retain a stale physical receive order after routing
changes.  `route_calc.csl` is production routing code, not a test harness.

### C2c ownership and review

Claude Code hardened only:

- `models/qwen3_1p7b-decode-ragged-batch/tests/s0_fullscale_streaming_reference.py`
  at SHA256
  `a96bbf19473e13a27e4d78200bb722b2bbb351545743bc4c020faa7417edeb67`;
- `models/qwen3_1p7b-decode-ragged-batch/tests/test_s0_fullscale_streaming_reference.py`
  at SHA256
  `f9d1cf660448969782e3f9bc37e47fed0a96f6dc182bb95d9decf11689ae1e17`.

The validator now rejects attempts to relabel and fully re-sign nested
layer/final/result certificates as PASS, tolerance-approved, or unknown
statuses, as well as schema lookalikes and source-binding drift.  The root
reviewer independently passed the focused mutation gate and the complete
streaming harness file (50/50) before authorizing execution.

Production inputs stayed frozen at:

- `src/decode.csl`:
  `32147faa05533f5c2a166f249ac4fa0000fa2ebbb5baf18a0b5c174923429f40`;
- `launch.py`:
  `056060747a4448757990676db339b7d3e2a4c2c827730b28676aa1845dc7b391`.

### Accepted host evidence

Claude Code owned the accepted foreground execution:

- complete ragged test directory: 529/529 passed, pytest RC 0, 131.32 s wall,
  4,932,536 KiB peak RSS;
- independent actual cap-2048 read-only dry-plan gate: 1/1 passed, pytest RC
  0, 34.27 s wall, 4,925,148 KiB peak RSS.

The cap record produced a 28-layer dry plan for positions `(256, 512)`, 428
selected logical tensors, 3,910,921,728 selected logical bytes, and 117,449,216
streamed bytes per layer.  Full execution remains fail-closed with
`BLOCKED_PENDING_INDEPENDENT_REVIEW`; no output persisted and pre/post source
hashes were identical.

Do not treat an orphaned partial pytest log as evidence.  One prior attempt
stopped at 51% without a terminal summary or literal return code and was
discarded.  Also do not expand abbreviated hash prefixes into invented full
hashes; re-derive the complete SHA256 from the frozen file and source contract.

## Implications / next actions

These gates prove host planning and bounded tiny multi-layer state transitions,
not full 28-layer arithmetic or device correctness.  The numerical boundary
remains `BLOCKED_LOCAL_DSR_FMAC`.  No CS-3 correctness result, full-scale
NumPy/device comparison, tolerance approval, or equal-position performance A/B
follows from this evidence.

- [ ] Resolve or explicitly model the local DSR/FMAC arithmetic boundary.
- [ ] Run full-scale NumPy-versus-CS-3 correctness only after that boundary and
  its gates receive independent review.
- [ ] Keep the equal-position performance A/B blocked until correctness is
  frozen.

## Pointers

- `WaferEngine-staging/docs/analysis/2026-08-30-m1b-s0-part1-execution-log.md`
- `WaferEngine-staging/models/qwen3_1p7b-decode-ragged-batch/tests/s0_fullscale_streaming_reference.py`
- `WaferEngine-staging/models/qwen3_1p7b-decode-ragged-batch/tests/test_s0_fullscale_streaming_reference.py`
