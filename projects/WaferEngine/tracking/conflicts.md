# WaferEngine Manual Conflicts

Last reviewed: 2026-08-17 09:55 local

## Needs Le/manual resolution

1. **Canonical WSE per-PE resource analysis PPTX variant**
   - Existing dated file: `docs/2026-06-28/2026-06-28-wse_per_pe_resource_analysis.pptx`
   - Newly found undated file, renamed during maintenance: `docs/2026-06-28/2026-06-28-wse_per_pe_resource_analysis-alt.pptx`
   - The files have different SHA-256 hashes, so this is not a byte-identical duplicate. Maintenance did not choose which slide deck is canonical.

2. **Missing Obsidian image attachment for WaferOS meeting note**
   - Source note: `human/2026-06-29-meeting-notes-waferos.md`
   - The note references `![[73db331c7912ebc19f99d28a36f98082.jpg]]`, but no matching file exists in this repo.
   - The TODO text was curated into status/context, but the image context still needs human attachment recovery or a short textual replacement.

3. **M3.5 Claude PASS applicability vs stale no-verdict note**
   - `memory/inbox/2026-08-16-waferllm-function-container-m35-resident-helper-fork.md` says Claude Code attempts produced no verdict and warns not to cite a Claude PASS for the replacement.
   - `memory/inbox/2026-08-16-m35-claude-review-pass-conflicts-with-note.md` points to Claude session `72054b9f` and says a completed PASS exists for `/home/lexu/WaferEngine-staging/.m35_symmetric_refactor` with the same ABI/slot/offset/vecmat numbers.
   - Maintenance preserved both claims in topic memory but did not decide whether the staging artifact was byte-identical to `/home/lexu/WaferLLM/.../m35/` at review time. Le should verify artifact identity/scope before citing the PASS as covering the WaferLLM tree.

## Resolved by maintenance

- 2026-06-30: The undated docs artifact was renamed with a date prefix instead of deleted or overwritten.
