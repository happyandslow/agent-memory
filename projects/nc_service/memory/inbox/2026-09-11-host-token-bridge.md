# Interim Qwen drafting while the Kimi draft is training — 2026-09-11

**Project:** nc_service
**Author:** codex
**Status:** captured

## What happened / finding

- Le requested a host converter while the Kimi drafting model is still training.
  This supersedes the earlier claim that retaining Kimi target necessarily requires
  replacing the Qwen draft checkpoint: a same-tokenizer draft is required for direct
  raw-ID feedback reuse, but heterogeneous tokenization can be bridged with state repair.
- Added SDK-free `waferengine/samples/specdec/token_bridge.py`. Target-to-draft conversion
  returns the desired draft IDs and a longest-prefix `keep_tokens + append_ids` repair
  plan against ACTUALLY materialized KV IDs. `apply()` checks stale host ledgers only;
  no device KV is modified. Draft-to-target conversion preserves exact committed target
  IDs and re-encodes proposal bytes; if full-context tokenization changes the prefix,
  it independently encodes the suffix and records `suffix_fallback`.
- Exact byte recovery matters for partial UTF-8 tokens. The implementation never decodes
  through replacement characters; incomplete/invalid bytes use one-byte vocabulary
  entries. Qwen tokenizer.json has NFC normalization, which the bridge explicitly disables
  to preserve target bytes (decomposed Unicode must not silently change).
- First version handles ordinary text/raw IDs. It rejects Qwen added/Kimi reserved
  control IDs without an explicit semantic mapping. Draft EOS terminates candidates
  without forcing target EOS; literal marker text remains ordinary text.

## Validation

- 31 pure-logic cases passed; with actual local Qwen/Kimi tokenizers, 43 passed and
  zero skipped. Covers every byte split of multilingual/code/whitespace/emoji samples,
  arbitrary bytes, noncanonical target IDs, boundary merges, stale plans, and KV-ledger
  repair under zero/partial/full acceptance and missing-last-token KV.
- Full 61-layer Kimi HTTP verifier gate passed on prompt `def quicksort(arr):`:
  K=4 accepts [4,4], [2,1,1], [0,0,0]; K=16 CuteDSL accepts [16]. All returned Kimi IDs
  match the fresh 20-token greedy baseline prefix. Proposals were synthetic CPU Qwen
  token sequences converted by the actual bridge. Observed 4 Qwen tokens -> 3 Kimi tokens
  and a noninitial multi-token repair. No actual draft model or Cerebras KV was tested.
- GPU cases exercised context-aligned conversion. Suffix fallback is covered by logic
  and real-tokenizer tests, not a GPU-case claim. This is correctness smoke evidence,
  not a measured real-draft acceptance rate or speedup.
- Pytest was installed only into nc_service `_runs/token_bridge_20260911/test_deps`;
  the shared read-only CuteDSL environment was not modified. Tokenizer source hashes
  and converter hashes are in the run's provenance.json.

## Implications / next actions

- Current SD feedback accepts only accepted_count plus one correction. Applying a general
  repair plan still requires a backend capable of arbitrary crop/multiple-token ingestion,
  or a full-prefill fallback. New-request full prefill currently cold-loads the worker.
- Define chat-role/BOS/tool/think mappings before claiming chat support. Preserve target
  IDs across conversion; a canonical retokenization of the same bytes is not an equivalent
  target KV state. Cross-vocabulary token counts cannot be reused as rewind counts.
- Retained all weights/kernels. No commit/push performed. Interim converter is implemented;
  real Cerebras integration and the future trained Kimi draft remain separate work.

## Pointers

- `/home/lexu/nc_service/waferengine/samples/specdec/TOKEN_BRIDGE.md`: API, invariants,
  dependency paths, test commands and scope.
- `/home/lexu/nc_service/_runs/token_bridge_20260911/gpu01/report.json` and
  `conversions.json`; `../provenance.json` pins tokenizer and converter contents.
- `/home/lexu/hybrid-nn/docs/local-verifier.md`: prior same-tokenizer-only wording corrected.
