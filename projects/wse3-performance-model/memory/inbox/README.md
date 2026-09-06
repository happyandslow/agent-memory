# Inbox

Dated capture area for session writes, per `write-contract.md`. A live session
writes here by default; new `topics/` files are created only by the maintain
pass.

Use `templates/capture-entry.md`, filename `YYYY-MM-DD-<topic>.md`.

## Lifecycle

Each note carries a status line that drives the whole loop:

```
**Status:** captured   <!-- captured | drained -->
```

1. **captured** — written during a session, not yet curated.
2. **drained** — the maintain pass has folded the content into `topics/*.md`,
   `plan.md`, or the generated views, and flipped the status.

**Drained notes stay here.** They are not deleted or moved — the file remains as
the dated provenance record of when a fact entered the base and what the raw
capture looked like. So a non-empty inbox is normal and is not a backlog; only
the *status values* say whether work is outstanding.

## Checking

`scripts/find_conflicts.py` reports `un-drained inbox: <file>` for any note whose
status is not `drained`. That, not the file count, is the signal to act on.

```bash
python3 <claude-skills>/agent-memory/scripts/find_conflicts.py --root <agent-memory>
```
