# Stacked groups invalidate an outside-target terminal — 2026-09-13

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

When extending the isolated LayoutC marker protocol to the proposed stacked
groups, do not place STREAM_END one PE beyond the local-feedback destination
zone without checking that cell's existing source role. A source/geometry audit
found six collisions: WEST x131 at y257/513/769 for G1/G2/G3 northbound feedback,
and CENTER x388 at y770/514/258 for G5/G6/G7 southbound feedback. Each cell is
the neighboring group's first source junction on the same proposed color.
An isolated test with spare space outside its target zone does not cover this.

These are analytical collisions in the proposed full-model allocation, not
hardware failures of an integrated implementation. The reviewed plan proposes
termination within the final receiving row; that protocol change still needs
its own validation. No finalized color allocation is captured as a fact.

[Plan and geometry](/home/lexu/wse3-performance-model/docs/plans/2026-09-13-layoutC-full-model-routing-allocation.md)
and [Claude Code reviews/disposition](/home/lexu/wse3-performance-model/docs/reports/2026-09-13-layoutC-routing-plan-claude-review.md).
