# Lane B full-KV reload has no forced delta — 2026-08-03

**Project:** WaferEngine-staging
**Author:** human
**Status:** drained   <!-- drained 2026-08-06 into m2-experiment-register.md change log + plan.md next actions -->

## What happened / finding

- Situation: when the three-lane resume study defines Lane B as loading the complete
  target-position KV snapshot from host DRAM, adding a post-ingress forced-decode term
  double-counts reconstruction work. Its resume-to-KV-ready cost is `B(L)=I(L)`.
- The next normal free-decode token is a common tail: either exclude it from all lanes or
  add it to all lanes. Do not charge it only to Lane B.
- For the two slide-12 cases whose final context is 8,192, Lane B is therefore
  `I(8192)=338.266 ms` in both cases, with zero on-card reconstruction compute.
- E10/E10D's older `reload history + force-decode L_new` fixture remains valid evidence
  for that distinct delta-reload policy, but must not be presented as the current
  full-KV Lane B definition.

## Implications / next actions

- [ ] Audit the Lane B equation and A/B-crossing slides for the same delta-reload versus
  full-KV-reload definition mismatch.

## Pointers

- `projects/WaferEngine-staging/meetings/2026-08-02.pptx`, visible slide 12
- `projects/WaferEngine-staging/meetings/2026-08-02-src/make_figures.py`
- `projects/WaferEngine-staging/memory/topics/m2-experiment-register.md`, E10/E10D
