# Check the branch tip before treating its recorded timings as the current state of the art

Date: 2026-07-28 · Repo: `WaferEngine-staging` · M2 kickoff (tiering cost model)

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## The situation this applies to

Someone points you at a branch ("use this line for the study"), it has committed result files, and
you start planning measurements against those numbers. The branch is a *snapshot* — of whenever it
was last fetched — and the numbers in it age with the code.

## What happened

Le linked `CongjieHe/WaferEngine` branch `real_qwen3_1p7`. It was already present locally as
`pr14-real` (reflog: `fetch github.com:CongjieHe/WaferEngine.git real_qwen3_1p7:pr14-real`), tip
`efa954d`, **2026-07-21**. Its `request_config/mtbench8/timing.json` showed
`per_round_kv_load_ms = 5290` — 5.3 s per round spent loading a `.npz` off disk, ~8× the entire
wire transfer.

That is a striking finding, and it went straight into `GOALS.md §7` as *"likely the single largest
available win on the serving path"*.

**It was not available.** A second local branch `pr14-head` (`WaferAGI/WaferEngine`
`refs/pull/14/head`, tip `a3a509c`, **2026-07-28**) has `pr14-real` as an ancestor, **5 commits
back**, and those commits had already fixed it: `per_round_kv_load_ms` **5290 → 69.5 ms** (76×),
KV handoff per prompt 2.94–3.12 s → 0.72 s. The same commits also **froze the host-stream `io_loc`
pins** in `serve_2x4_8k20k.json`, closing a second known ~3× bandwidth loss.

So baselining the linked branch would have measured **two already-fixed implementation artifacts
and attributed them to the architecture** — and the study's whole purpose is to rank what to
implement next.

## The useful diagnostic

`git reflog show <branch>` records the fetch line that created a local branch — remote URL, remote
ref, and whether it was a fast-forward. That is how the identity was confirmed rather than inferred.
`git merge-base --is-ancestor A B` then settles staleness in one command.

Worth separating **what moved from what didn't**: across those 5 commits the *device* anchors were
stable within ~1% (decode 659.4 → 655.0 µs/token, prefill 30-token span 57.03 → 56.91 ms, KV egress
22.31 → 23.53 ms) while every *host-side* overhead changed by multiples. Knowing which half moved
tells you which conclusions survive a stale baseline and which do not.

## What to do instead

- Run `git reflog show <branch>` and `git merge-base --is-ancestor` **before** quoting a branch's
  committed result files. Add "re-fetch and confirm the tip" as an explicit first task in any
  measurement plan.
- When two refs track the same upstream line, write the branch map down (ref → remote → tip → date)
  where the next session will read it, not in chat.
- A local branch cannot tell you whether the *remote* has moved since the fetch. Say so explicitly
  rather than implying currency.
- Prefer the newer head for measurement even when it is less settled, and name the fallback plus
  what must be subtracted by hand if you fall back.

## Confidence / attribution

Branch identity, ancestry, commit range, and both `timing.json` deltas were read in-session via
`git reflog` / `git merge-base` / `git show`. Whether `real_qwen3_1p7` has advanced past `efa954d`
since the last fetch is **not knowable from the local clone** `[unverified]`. `pr14-head` also
carries "Qwen3 1p7b Speculative Decoding" and "4B Decode Optimization", so it is less settled than
`pr14-real` — that risk is recorded, not resolved.

**Promotion candidate (procedural).** Stated without naming this project: *a branch someone links
you to is a snapshot with a date; before planning work against the results committed in it, confirm
its tip against the upstream line and check whether the problem you found has already been fixed
downstream of it.*

## Pointers

- `milestones/M2-tiering-cost-model.md` § "Which pr14 branch is the baseline".
- `GOALS.md §7` — the disk-npz entry, closed as `[answered — already fixed upstream]` the same day
  it was raised.
- `docs/session-prompts/M2-S0.md` — branch provenance is now the first item under 背景.
- Related: [[pr14-real-serving-port-contract]] (carries the branch map),
  [[git-branch-status-verification]], [[a-quoted-number-is-not-a-measured-number]].
