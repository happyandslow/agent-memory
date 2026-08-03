# Long-polling over a replay-cached transport: reusing the request key turns the retry into a livelock, and that is why an application-level ack is unavoidable

Date: 2026-07-28 · Repo: `nc_service`, branch `lexu/pdsep-kernel-integration` (Task 9, `sd_gateway.py`)

**Project:** nc_service
**Author:** claude
**Status:** drained

## The situation this applies to

You are adding a **long poll** to a request/response transport that already has a
**replay cache** — a dedupe layer that returns the previous reply when it sees the same
request key twice. Here: `serve_core.serve_one`'s `ReplayState`, keyed on the frame `seq`,
whose whole job is to make a dropped-reply retry safe.

The worker cannot always answer immediately (the wafer is mid-round), so it replies
PENDING and expects to be re-polled. The obvious implementation is *"same request, same
key — it is idempotent, that is the point"*.

**That is exactly backwards, and it fails silently.** The replay cache sees the same key,
returns the cached PENDING without ever invoking the handler, and every subsequent poll
gets the same stale PENDING. Not an error, not a timeout — a livelock that looks like a
worker which never finishes.

## The rule

**Every re-poll must carry a FRESH key.** The payload stays byte-identical; only the key
changes. In `sd_gateway.SdSession.advance` that means the caller hands in a starting `seq`,
the poll loop consumes one per attempt, and it reports back the last one used so the
session's numbering stays strictly increasing.

## The part that closes the loop, and that a previous note left half-open

Fresh keys mean the replay cache **can no longer dedupe the repeated request**. So the
dedupe obligation does not disappear — it moves up a layer, and it must be keyed on
something inside the **payload**, not on the transport key.

For us that is the `(request_idx, round_id)` ack the feedback carries: the worker delivers
a verdict only when it matches the batch it is holding, skips it when it matches the last
one it already delivered, and treats anything else as a desync.

These two mechanisms look independent. They are not: **the long poll forces fresh keys,
fresh keys disable transport-level dedup, and that forces application-level dedup.** An
earlier capture in this project recorded the second half ("under long-polling every retry
is a new seq, so the replay cache cannot dedupe it") as a *premise* — stated that way it
reads as a property of the system rather than a choice the implementer must make, and
someone implementing the gateway from it could reasonably have reused the key.

## Cost of getting it wrong, and how it was caught

Silent. No exception, no reply mismatch, no watchdog fire — the transport is behaving
exactly as designed. Only a test that asserts the *keys are distinct across polls* catches
it, and only a mutation (delete the increment, re-run) proves that test is actually
guarding anything. Both exist now:
`test_pending_repolls_with_a_fresh_seq_and_the_same_feedback`, which asserts both halves —
seqs strictly increasing AND payloads byte-identical.

**Promotion candidate (procedural).** Stated without this project: *before layering a long
poll onto a transport that dedupes on a request key, work out which layer owns dedup after
the change. The poll needs fresh keys, fresh keys switch the dedupe layer off, and whatever
idempotency the handler relied on now has to be re-established from the payload. Test that
consecutive polls carry distinct keys and identical bodies — a reused key fails as a
livelock, which no timeout or error path will surface.*

## Pointers

- `waferengine/samples/specdec/sd_gateway.py` — the rule and its reasoning are in the
  module docstring, because this is the kind of thing a later reader "simplifies" away.
- `waferengine/samples/specdec/sd_kernel/rendezvous.py` — the application-level ack dedup
  the fresh keys make necessary.
- Related: [[2026-07-27-inproc-exchange-constrains-verify-seam]] (the half this completes),
  [[2026-07-28-m1-complete-bridge-architecture-index]].
