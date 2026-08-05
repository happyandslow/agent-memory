# codex-review returns nothing after ~1800s when the claims reference source outside `-C` root — 2026-08-05

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

You send a plan or design doc to `codex-review` (or the raw Codex CLI) and the
first round comes back fine (<600s). A later round asks Codex to **verify
specific source claims** — line-anchored assertions like "`decode.csl:1140` does
X" — and it **hangs to the full timeout (1800s) and produces no output at all**:
no verdict, no partial text, no raw file. Nothing to show for the wall time.

This is a *different* failure from codex-review hanging on stdin under nohup
(see [[codex-review-hangs-under-nohup-on-stdin]]) — here it starts fine and
silently burns the whole budget.

## The cause

Codex was launched with its sandbox root at one checkout (`-C /home/lexu/WaferEngine-staging`),
but every claim it was asked to verify lived in a **different worktree**
(`/home/lexu/we-m2bench`) — *outside* its read-only root. Given deep
line-anchored claims across a tree it cannot see, it spends the entire timeout
hunting for files that aren't under its root. A `--dry-run` of the invocation
showed the root/`-C` and confirmed the target files were external.

## The fix (validated)

Retrying with the same review scope but **(a) the relevant source pasted inline
into the handoff doc** and **(b) the scope narrowed to the one section under
review** returned in **180s** instead of timing out. Do not rely on Codex
reaching source outside its `-C` root; bring the source to it.

- If the thing being reviewed references files in another checkout, either root
  Codex at the common parent, or (better) inline the exact source excerpts the
  claims depend on.
- Narrow the review to one section per round; a broad "verify all N claims"
  across an unreachable tree is the worst case.

## Promotion candidate

Procedural, tool-general (applies to any `codex-review` invocation), not a fact
about this project → belongs in the **codex-review** skill's guidance, alongside
the existing nohup/stdin note.

## Pointers

- Surfaced during the M2/M3 planning review rounds — [[m2-s3-experiment-tracker]].
- Related tool gotcha: [[codex-review-hangs-under-nohup-on-stdin]].
