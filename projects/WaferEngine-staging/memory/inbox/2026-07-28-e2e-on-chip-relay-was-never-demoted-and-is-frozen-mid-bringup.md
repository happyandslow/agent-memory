# The recorded "PR #14 killed the e2e on-chip KV relay" conclusion is wrong — and what is actually true is a diagnosed, frozen bring-up

Date: 2026-07-28 · Repo: `WaferEngine-staging` · `qwen3_1p7b-e2e` at `main` vs upstream PR #14 head `a3a509c`

**Project:** WaferEngine-staging
**Author:** claude
**Status:** drained

## The situation this applies to

You are weighing whether to adopt PR #14, and you consult the `PROGRESS.md` "Failed
approaches" entry recording that **PR #14 demoted the on-chip relay to inert filler, not
config-revivable**. Read straight, that entry says adopting PR #14 costs you the on-chip
KV path in `e2e` and forces host-mediated KV — a real tradeoff to weigh against everything
else.

**That tradeoff does not exist.** The entry appears to be a model mix-up, and the direction
of the correction is the convenient one: adoption is *less* costly than recorded, not more.

## The correction (verified by direct diff)

In `qwen3_1p7b-e2e`, at `main`, before PR #14:

- three `KV_TRANSFER: 1` configs already shipped — `test_sim_1x2blk_kv`,
  `test_sim_2x2blk_kv`, `test_device_2x2blk_kv`;
- `build_relay` is **identical** `main` → PR #14 apart from a Unicode arrow and one space of
  indentation, `transit_rp`'s SOUTH→NORTH wiring of colors 17/21 verbatim the same;
- `src/relay.csl` **still exists** in `e2e` at PR #14.

So neither half of the recorded claim holds for `e2e`: the relay was never demoted by PR #14,
and it was already config-revivable on `main`.

The model it *is* true of is **`qwen3_1p7b-e2e-pdSeparate`**: `src/relay.csl` is present on
`main` and absent at PR #14, and its `launch_decode.py` never mentions `build_relay` or
`kv_transfer`. Agent-memory already carries that fact correctly
([[standalone-vs-integrated-kernel-parity]] records pdSeparate's KV plumbing as *replaced*) —
the error is only in the work repo's durable prose, which makes it easy to keep re-reading.

## What PR #14 actually contributes here — and why it is stalled

PR #14's contribution to `e2e` is the **pipeline**, not the seam: six new KV CSL files,
`kv_transform` work in `prefill.csl`, a `STAGE_A_DIAG` env gate, and an on-chip bit-exact
self-check. `e2e/launch.py` grows 3054 → 4552 lines.

And it is **frozen at a well-diagnosed failure**, which is the more useful half of this note:

- the self-check reports `FAIL (256 bad, first=(0,0,0,0,0,'K'))`;
- the first bad element is at the **diagonal, north-most decode PE — the one position that
  needs no transpose at all**, which is why the diagnosis is a systematic
  offset/packing/delivery bug rather than a layout bug;
- the handoff doc **explicitly retracts** the tempting "add K pair-interleave" fix and
  forbids further layout changes without bit-exact evidence first;
- `e2e/launch.py` was last touched 8 commits before the tip; the author moved on to pdSeparate
  serving, then speculative decoding, then 4B.

Anyone picking up on-chip KV transfer in `e2e` inherits a partly-built pipeline plus a
non-obvious diagnosis, not a blank sheet — and should not spend the first day rediscovering
that the interleave fix is wrong.

## Implications / next actions

- [ ] Correct the `PROGRESS.md` "Failed approaches" entry — **re-read its exact wording first**;
      this capture asserts the claim is wrong about `e2e`, not that the sentence has been read
      recently. No durable doc was edited in the session this came from.
- [ ] Where the entry's conclusion was used as an input (any "adopting PR #14 means
      host-mediated e2e" reasoning), re-check the conclusion.

## Attribution / confidence

Code-verified in-session by direct diff of `main` vs `a3a509c` for `build_relay`,
`src/relay.csl`, and the `KV_TRANSFER: 1` config list, in both `e2e` and `e2e-pdSeparate`.
Originally surfaced by a peer analysis agent, then independently checked because it
contradicted both a written record and this session's own earlier claim (which had it as
PR #14 *reviving* the path — also wrong; it was never dead). **Not confirmed by Le.**

## Pointers

- [[standalone-vs-integrated-kernel-parity]] — has the pdSeparate replacement recorded correctly; the `e2e` relay colors 17/21 seam and the `kickoff_relay` correction live here too.
- [[pr14-real-serving-port-contract]] — the adopt-vs-port decision this feeds.
- [[e2e-kernel-dataflow-and-topology]] — the relay's place in the e2e topology.
