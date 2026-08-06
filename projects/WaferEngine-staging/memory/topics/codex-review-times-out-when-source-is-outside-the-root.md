---
summary: codex-review starts fine then hangs to its full ~1800s timeout with no output when the claims it must verify reference source in a different worktree outside its -C root; fix is to inline the exact source excerpts into the handoff and narrow scope per round.
tags: [WaferEngine-staging, tooling, codex-review, gotcha, procedural, drained-inbox, 2026-08-05]
---

# codex-review returns nothing after ~1800s when the claims reference source outside `-C` root

This topic was created by the 2026-08-06 maintain pass from a dated inbox capture
(`memory/inbox/2026-08-05-codex-review-times-out-when-source-is-outside-the-root.md`, author claude).
Keep it as the durable home; the capture is marked drained. **Procedural / tool-general** — a
`codex-review`-skill promotion candidate, sibling to
[[codex-review-hangs-under-nohup-on-stdin]].

## The situation this applies to

You send a plan or design doc to `codex-review` (or the raw Codex CLI). The first round comes back
fine (<600 s). A later round asks Codex to **verify specific source claims** — line-anchored
assertions like "`decode.csl:1140` does X" — and it **hangs to the full timeout (1800 s) and
produces no output at all**: no verdict, no partial text, no raw file. Nothing to show for the wall
time.

This is a **different** failure from codex-review hanging on stdin under nohup
([[codex-review-hangs-under-nohup-on-stdin]]) — there it never starts; here it starts fine and
silently burns the whole budget.

## The cause

Codex was launched with its sandbox root at one checkout (`-C /home/lexu/WaferEngine-staging`), but
every claim it was asked to verify lived in a **different worktree** (`/home/lexu/we-m2bench`) —
*outside* its read-only root. Given deep line-anchored claims across a tree it cannot see, it spends
the entire timeout hunting for files that are not under its root. A `--dry-run` of the invocation
showed the root/`-C` and confirmed the target files were external.

## The fix (validated)

Retrying the same review scope but **(a) with the relevant source pasted inline into the handoff
doc** and **(b) with scope narrowed to the one section under review** returned in **180 s** instead
of timing out.

- Do not rely on Codex reaching source outside its `-C` root; bring the source to it — either root
  Codex at the common parent, or (better) inline the exact source excerpts the claims depend on.
- Narrow the review to one section per round; a broad "verify all N claims" across an unreachable
  tree is the worst case.
- A timeout is not a clean review (see the sibling note): retry cheaply, do not report or infer
  "converged".

## Related

- [[codex-review-hangs-under-nohup-on-stdin]] — the other codex-review failure mode.
- Surfaced during the M2/M3 planning review rounds — [[m2-s3-experiment-tracker]].
