---
summary: Before designing a protocol change for the GPU verifier, check the counterpart repo — SGLang already vendored our proto AND our Rust control plane
tags: [nc_service, drained-inbox, 2026-07-28]
---

# Before designing a protocol change for the GPU verifier, check the counterpart repo: SGLang already vendored our proto AND our Rust control plane

This topic was created by the 2026-08-03 maintain pass from a dated inbox capture. Keep it as the durable, topic-scoped home for the finding; the original capture is marked drained.

## Drained capture — 2026-07-28

Source: `memory/inbox/2026-07-28-sglang-already-speaks-our-protocol.md`

# Before designing a protocol change for the GPU verifier, check the counterpart repo: SGLang already vendored our proto AND our Rust control plane

Date: 2026-07-28 · Repo: `nc_service` (branch `lexu/pdsep-kernel-integration`) ⇄ `lausannel/sglang-remote-spec@remote-draft-grpc-tp-broadcast`

**Project:** nc_service
**Author:** claude
**Status:** captured

## The situation this applies to

You are planning the GPU/verifier side of the spec-dec loop and are about to design
proto additions (draft distribution `q`, top-K logits) so a real target model can do
Leviathan-style rejection sampling. Reading only `nc_service` will tell you the GPU side
is a **transport benchmark with hardcoded ids** — `verify_service.rs` literally does
`let _response = proxy.advance(...)` and discards it, `mock_verify_host.expected_accounting`
checks only `base_version+1` / `base_len+len(emitted_ids)` / `len(draft_ids)==k`, and no
ML dependency exists in `Cargo.toml`.

**That picture is a year out of date the moment you look at the counterpart repo.** Do
that first; it changes what the work even is.

## What is actually true (verified, 2026-07-28)

`lausannel/sglang-remote-spec@remote-draft-grpc-tp-broadcast` implements
`--speculative-algorithm REMOTE_STANDALONE`: SGLang hosts the `DraftControl` gRPC server
alongside its HTTP API, and its docs give the exact command to drive **our**
`waferengine/samples/specdec/driver_main.py` as the drafting service.

- **The protos are byte-identical.** `sha256(draft.proto)` matches across
  `nc_service/proto/`, `nc_service/waferengine/samples/specdec/proto/`, and
  `sglang/rust/nc-draft-client/proto/`. It is now a **three-way** contract.
- **They ported our Rust control plane.** `draft_command_proxy.rs` keeps our
  `advance_with_timeout` / pending-oneshot / registry-push shape (`Uuid`→`AtomicU64`,
  `pub`→`pub(crate)`); `verify_control.rs` matches `src/verify_control/server.rs`
  symbol-for-symbol plus a `wait_for_draft_service`.
- **They validate our responses.** `lib.rs::extract_draft_ids` enforces EIGHT conditions
  against a local `ReqState{round, version, committed_len}` ledger: request_id,
  committed_version, committed_len, proposal presence, proposal.round_id,
  proposal.base_version, proposal.base_len, and the draft-id count. (An earlier
  draft of this note said "seven" -- it omitted the presence check.)
- **Prefill is implemented exactly as our own prior decision doc prescribed**
  (`accepted=0, base_len=0, emitted_ids=prompt, reason="prefill"`), independently
  confirming that "no wire change for prefill" conclusion.

## The finding that changes the plan: it is an ALGORITHM difference, not a missing field

`q`/top-K are not absent because nobody plumbed them. **The receiver does not want them.**

SGLang's `eagle_info.py::verify()` has two branches and neither consumes a draft
distribution:
- greedy (`sampling_info.is_all_greedy`) — `argmax(target logits)` vs the draft token;
- sampling — `tree_speculative_sampling_target_only(...)` with, immediately above it,
  `draft_probs = torch.zeros(target_probs.shape, ...)`. **Zeroed unconditionally, for
  every speculative algorithm on that path.** The kernel's own name says `_target_only`.

So: our WSE-3 kernel is built on the Leviathan assumption (it computes `q` on-chip as part
of the record width whether or not anyone reads it); SGLang is built on target-only
threshold verification. Landing `q` on the wire is ~20 mechanical lines across three proto
copies — but it buys nothing until SGLang **changes acceptance algorithms**, which is a
research/product decision, not plumbing. Negotiate the algorithm, not the field.

**Correction to an earlier reading of mine.** I claimed `topk_p=torch.ones_like(...)` in
`remote_standalone_worker_v2.py` meant the acceptance test was being fed a fabricated q and
therefore degraded. **Wrong — retracted.** `topk_p` never appears inside `verify()`; it
lives on `EagleDraftInput` and drives *next*-draft tree construction, which the remote path
does not do. Filling it with ones is inert bookkeeping. I only caught this by grepping the
verify function body instead of trusting the field name.

## The more urgent incompatibility, which has nothing to do with distributions

**Concurrency shape.** SGLang's hosted path `batch_advance` fans out with `join_all` — one
`advance` per request in the batch, concurrently — and `InFlightGuard` only blocks re-entry
for the *same* `request_id`, not across requests. nc_service is strictly one-exchange-in-flight
end to end: `ExchangePump` ("strictly one exchange in flight at a time"), the kernel's
`serve_loop` (single-request sequential), our rendezvous (`Queue(maxsize=1)`). **Any batch
size > 1 collides before any distribution work matters.** Also open: they require
`k == --speculative-num-steps` (docs example 16); the WSE-3 kernel ships `draft_len: 4`
(`MAX_DRAFT_LEN: 16`).

## The verification technique worth reusing (procedural)

Do not conclude wire compatibility by reading both sides. **Replay the counterpart's exact
request-construction and ledger transitions through your own responder and assert their
checks.** Concretely: reconstructed SGLang's `build_prefill_request` / `build_decode_request`
shapes and `ReqState` transitions in ~60 lines of Python, fed them to nc_service's
`translate.build_response`, and asserted all eight of *their* `extract_draft_ids` conditions
over prefill + 5 decode rounds. Green. That replay is now a permanent test
(`sglang_shapes.py` + `test_sglang_shapes.py`), not a throwaway script. That is evidence; a side-by-side read is not.

## Implications / next actions

- Milestone 1 needs **zero** protocol change. Deliverable: `Proposal.draft_ids` stops being
  a passthrough echo / stub placeholder and becomes real tokens from the
  `qwen3_1p7b-sd-pdSeparate` kernel; tested against `mock_verify_host.py`, not a live SGLang.
- [ ] Get an SGLang-side answer on batch size (concurrency) and on `draft_len` 4 vs 16 —
      both block interop and neither depends on the distribution question.
- [ ] Open: does `tree_speculative_sampling_target_only` consume `draft_probs` at all when
      non-zero? Unanswerable from outside; if it ignores them, the change is a new kernel,
      not a populated tensor.
- The `verify_target/` package I had planned is largely premature: SGLang *is* the target and
  already verifies. What is actually wanted is a scriptable verdict source for
  `mock_verify_host.py`.

## Pointers

- ContextBase: *Draft distribution on the wire: what SGLang would need to change
  (proto side-by-side)* — the collaboration doc, with the TODAY/PROPOSED proto diff and the
  six concrete steps the GPU service would take.
- ContextBase: *SpecDec verify↔draft protocol: prefill vs decode — does the wire need to
  change? (No)* — the prior decision this independently confirms.
- `waferengine/samples/specdec/sd_kernel/wire.py` — module docstring now records that the
  distribution stops at the gateway, so nobody reads its presence as "wired end to end".
- Related: [[2026-07-27-why-patch-the-target-not-the-launcher]],
  [[2026-07-27-inproc-exchange-constrains-verify-seam]].
