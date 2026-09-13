# Distinguish physical router strips from the old K-pipe relay — 2026-09-13

**Project:** wse3-performance-model
**Author:** codex
**Status:** captured

When budgeting the changed 4B layout, Le clarified that the inter-group path
is the single-color conversion case already discussed and requested a
whole-wafer, nonoverlapping-region color map. Do not interpret retaining the
inter-group transport function as adding the old eight-pipe CE relay beside
that replacement. Physical strip PEs remain for router turns/transit; this
does not require CE payload forwarding or the old fixed 16-color allocation.
This refines the K-pipe interpretation in the earlier same-day capture.

A dated analytical map now covers all 36 layers and support reservations.
It separates known component claims from unassigned links and auto-allocated
external-component colors. A1/A3 share switch-capable candidates
5-7,12-13,16-17,20-21 before new bridge/KV/head/tail/reset claims. C16 is a
candidate on replacement router bridges while A2 retains its disjoint X-row
multicast; it is not a finalized full-model assignment. Unknown IDs are not
certified free, and color availability does not prove queue/task availability.

Geometry, candidate complements, source hashes, five negative controls, and
Excalidraw-to-SVG consistency passed. No full-model compiler or hardware
validation was performed. No existing kernels or project trackers changed.

[Report and editable figure links](/home/lexu/wse3-performance-model/docs/design/2026-09-13-layoutC-regional-color-audit.md).
