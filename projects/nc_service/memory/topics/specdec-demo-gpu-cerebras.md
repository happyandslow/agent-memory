---
summary: Browser demo for GPU-alone vs GPU+GPU-draft vs GPU+Cerebras speculative decoding; parameterized timing model, rendering pitfalls, and final K=32 coding-workload caveats.
tags: [nc-service, specdec, demo, gpu-verifier, cerebras, acceptance-rate, visualization]
---

# SpecDec demo: GPU + Cerebras

Curated from `memory/inbox/2026-07-20-specdec-video-demo.md`.

## Artifact and purpose

Single-file browser demo for talks: `nc_service/demo/specdec_race/index.html`, with tests in `demo/specdec_race/tests/` (`./run.sh`). The final layout has three vertical lanes: GPU alone, GPU + GPU draft, and GPU + Cerebras. It is meant as a live backdrop / parameterized visual model, not a fixed clip.

## Model caveats that matter

- Acceptance rate is ambiguous. For speculative decoding, geometric/per-token acceptance is the right default; a block-fraction interpretation can overstate speedup by ~3× at K=16.
- The final K=32 defaults use Le's coding-workload setting: K=32, ~25 accepted tokens per 32-token draft, Cerebras target 1600 tok/s. ContextBase surfaced a measured code-region accept length of **25.720285 / 32** (97,377 accepted over 3,786 rounds), so the demo’s 25/32 is measured-ish and conservative for code regions.
- The same report says **all rows** average only **0.915 accepted tokens per 32-token draft**. The demo is therefore a coding-workload best case; all external claims must name the regime. At the K=32 defaults, code-region speedup is ~6× while all-rows is slower than GPU alone.
- GPU-only speculative decoding is the real informed baseline, not vanilla GPU decode. GPU-only pays zero cross-system communication; the Cerebras path wins only if faster wafer drafting and GPU capacity relief offset the communication leg. At K=16 / p=0.62, GPU-draft break-even was ~1.07 ms/token; at K=32 defaults it tightened to ~0.72 ms/token.
- The demo models steady-state decode only. It omits TTFT/prompt prefill and the measured ~2.2 s one-time mode-B bring-up; over short generations, that omission can dominate.

## Final parameter shape

Le simplified the stages to drafting / verification / communication while retaining K and acceptance. Verification needs fixed + marginal terms because K tokens are verified in one forward pass (1 tok 9.2 ms, 32 tok 17.0 ms); a single per-token value is misleading. Drafting can be modeled as per-token plus optional fixed, but the fixed part was not measured on the production batch path.

Published ContextBase page: `SpecDec demo (GPU + Cerebras) — how to run it, how to tune it, what every parameter means` at https://context.ed-aisys.com/doc/specdec-demo-gpu-cerebras-how-to-run-it-how-to-tune-it-what-every-parameter-means-UUYyJTKb4Z . Attachment upload failed; the page points at repo paths.

## Rendering / harness lessons

Timing assertions did not catch visual failures. Bugs found only through screenshots or explicit node-retention/class-census checks included committed tokens vanishing after CSS animation, commit-after-reveal clearing tokens before promotion, queue skew freezing the spec pane at 0, trace rendering future rounds only, and rejected tokens living for only one frame. Keep visual retention/history checks in the suite.

See also: [[specdec-gpu-verifier-eidf]], [[specdec-modeb-drive-path]], [[specdec-cs3-roadmap]].
