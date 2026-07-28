# Rebasing onto PR #14: the files that merge *cleanly* are where the breakage hides

Date: 2026-07-28 · Repo: `WaferEngine-staging` · `lexu/staging/kv-feature` vs upstream PR #14 head `a3a509c`

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You are sizing the rebase of `kv-feature` onto PR #14 and you run a trial three-way merge to
find out what it costs. The conflict list comes back small and you start planning around it.

**The conflict list is the cheap half.** The expensive half is the set of files git merged
without complaint, because our work and PR #14's work touched *different lines of the same
contract*. Two such breaks were found by inspecting the merged tree, and one of them is
invisible to every simulation config this repo owns.

## The conflict surface (measured on a trial merge, 2026-07-28)

Seven files, 18 hunks, ~650 lines — and the shape is informative:

| file | hunks | lines |
|---|---:|---:|
| `decode/launch.py` | 6 | 457 |
| `decode/src/ht_tail.csl` | 3 | 53 |
| `decode/src/decode.csl` | 2 | 34 |
| `decode/src/ht_head.csl` | 1 | 24 |
| `prefill/launch.py` | 3 | 52 |
| `prefill/src/ht_head.csl` | 2 | 21 |
| `prefill/model_config/test_sim_2x4_kv_varlen.json` | 1 | 8 |

Two things worth carrying forward. First, **the entire M1-S1 slot-addressing seam produces
zero conflicts** — the piece nobody upstream is building is also the piece that costs nothing
to carry. Second, the recurring source of friction is thematic: PR #14's repeated move is
*deleting* compile-time switches (`kv_stream_ingress` in decode, `kv_egress` in prefill,
paths now unconditional), and our retain code sits inside exactly those conditionals. We add
conditionality precisely where they removed it.

Budget the rebase in days, not weeks — but budget it *after* the two items below, not before.

## Break 1 — a renamed symbol survives as a dangling import (verified in the merged tree)

PR #14 renames `numpy_oracle_logits` → `numpy_decode_oracle`. `oracle_fp16.py` auto-merges
with **no conflict**. The merged `launch.py` then carries both import lines:

    57: from oracle_fp16 import numpy_oracle_logits, numpy_oracle_retain_step0   # ours, now dangling
    59: from oracle_fp16 import numpy_decode_oracle                              # PR #14's

and the merged `oracle_fp16.py` no longer defines the old name. Git did its job; the result
does not import. Sweep for the whole class after any merge — symbols the other side renamed
that our call sites still reference — rather than trusting a clean merge status.

## Break 2 — a protocol split across two files can merge *half* [unverified]

S6b widened the decode round header to a 2-wavelet `[N, F]`. The sender is in `ht_head`, the
receiver in `ht_tail`; both files conflict, so both get hand-resolved, independently. Taking
the widened header at one end and not the other is a wavelet-count mismatch — the classic
silent CSL desync, no compile error.

What makes this worse than usual: **`bsz = 2` in every config we own**, which is claimed to
make a half-merge produce plausible-looking output rather than an obvious failure. That half
is reasoning from the code, not an observed run — treat it as the reason to add an explicit
check, not as a measured fact. Concretely: after resolving, assert the sender's emitted
wavelet count equals the receiver's expected extent, and add at least one config where a
mismatch cannot cancel.

Related guard in the same area, also reasoning-only: PR #14 adds an `n_steps + 1` terminator
step to both `ht_head` and `ht_tail` loops. Tracing both counts, the S6b balance survives —
`ht_head` floods `NEG_INF` and breaks **without draining a token**, and `ht_tail`'s
pre-existing `tail_step < n_steps - 1` gate already excludes the terminator from emitting — so
N−F emits still meet N−F drains. But branch **order** in the merged `ht_head` matters: if our
`ht_step < forced_decode_len` branch precedes the terminator check, then `F > N` swallows the
terminator entirely (no flood, no break) and the diagonal PE blocks forever on a
`pre_embed_x` the host never sends. `F == N` is safe. Put the terminator check first *and*
assert `F <= N` host-side.

## The generalisable rule

A three-way merge reconciles *lines*. It cannot reconcile a **contract that lives in more
than one file** — a symbol name and its call sites, a wavelet count and its reader, a struct
width and its consumers. After every conflict resolution on a protocol change, verify the
contract end-to-end rather than verifying that the merge succeeded. "Zero conflicts" on a
file is evidence about text, not about meaning.

## Promotion candidate

**Procedural.** The rule above ("git merges lines, not cross-file contracts — after resolving,
verify the contract at both ends") is not WaferEngine-specific and would be cheap to carry in
a skill. It is distinct from what [[git-branch-status-verification]] covers (that note is
about *stale status claims* and squash-merge ancestry, not merge correctness).

## Attribution / confidence

The conflict counts and the dangling-import break are **code-verified against an actual trial
merge** in-session. The `bsz = 2` blind-spot claim and the terminator branch-order hazard are
**derived from reading the merged sources, not run** — marked `[unverified]` above. Nothing
here was confirmed by Le; the rebase itself remains a deferred decision (see
[[pr14-real-serving-port-contract]]).

## Implications / next actions

- [ ] Before the rebase: enumerate PR #14's renamed symbols and grep our call sites; the
      dangling-import class will not show as a conflict.
- [ ] Re-run the trial merge at the then-current tip — PR #14 moves (it went `b9ff52b` →
      `a3a509c` while this repo's docs still pinned the old one). These counts expire.

## Pointers

- [[pr14-real-serving-port-contract]] — the contract itself and the deferred adopt-vs-port decision; also records that PR #14 still has **no** keyed retain / KV store, so nothing of M0/M1 is redundant.
- [[git-branch-status-verification]] — the adjacent but different failure (stale status prose, squash-merge ancestry).
- `memory/inbox/2026-07-28-check-the-branch-tip-before-baselining.md` — the same PR's tip moving under a recorded baseline.
