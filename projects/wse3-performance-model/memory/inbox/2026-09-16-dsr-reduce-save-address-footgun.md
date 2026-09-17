# DSR scalar reductions: `save_address = true` breaks them in simfab (footgun); a separate device-only "last-slot" reduction bug is still unpinned — 2026-09-16

**Project:** wse3-performance-model
**Author:** claude (session 4b-layout-kv-stream)
**Status:** captured

## The footgun (confirmed)

When you reduce a DSR into a scalar with `@fmaxh`/`@fmaxs`/`@faddh`/`@fadds`/
`@fminh` (`@fmaxs(ptr, init, dsr)`), the result depends on the `save_address`
flag of the `@load_to_dsr` that filled the DSR:

- `save_address = false` — reload the DSR each iteration and advance the memory
  DSD with `@increment_dsd_offset` — ACCUMULATES the segment correctly.
- `save_address = true` — load once, let the DSR auto-advance — does NOT
  accumulate: each element does `*ptr = op(init, element)`, so only the LAST
  element of the segment survives.

**Tested on WSE-3 (2026-09-16):** the broken behaviour is a **simulator (simfab)
effect** — with `save_address = true` a per-head max came back 0.0 in simfab,
while the same build PASSED on device (CS-3, 32x256, N=16,384 and 65,536,
seeded nonzero) with the max exact. It is **placement-sensitive**: with the flag
set AND the reduction inlined right behind the `@map` that filled the buffer,
simfab passes again.

**Standing rule:** keep `save_address = false` on every reduction DSR (reload +
`@increment_dsd_offset`). `save_address = true` belongs on GEMV-style operand
DSRs that must stride (e.g. a K-column DSR), not on a reduction accumulator.
`kv_farm.csl` already follows this (save_address=false on the max/l reduces).

## NOT the same as the still-unpinned device defect

Separately, one KV-farm build once returned, ON DEVICE, a max equal to the max
over the LAST slot only (denominator inflated ~1.19x at N=16,384); simfab never
reproduced it. That symptom (device-only, last-slot) is different from the
save_address effect (simfab-only, returns 0.0), so save_address does not explain
it. Eleven seeded device runs across five reduction forms failed to reproduce
the original; mechanism unpinned (suspect: compiler scheduling / DSR allocation
in a specific fused loop shape). Practical control: gate farm changes on the
nonzero-KV device harness + an EXACT per-head max compare, not on pattern-spotting.

## The original Slack report (attached, verbatim context)

Le, reducing a DSR into a scalar with `@fmaxh`, found the result changed with
`save_address`:

Data: three 4-element f16 segments {5,3,8,2},{1,9,4,6},{7,0,3,1}.

Works (proper reduction), `save_address = false`, reload + increment each iter:
```
for (@range(i16, 3)) |i| {
    result = 0.0;
    @load_to_dsr(src1_dsr, data_dsd, .{ .save_address = false });
    @fmaxh(ptr_result, result, src1_dsr);
    results[i] = result;
    data_dsd = @increment_dsd_offset(data_dsd, 4, f16);
}
// results = [8.0, 9.0, 7.0]  (correct per-segment max)
```

Broken (last element wins), `save_address = true`, load once:
```
@load_to_dsr(src1_dsr, data_dsd, .{ .save_address = true });
for (@range(i16, 3)) |i| {
    result = 0.0;
    @fmaxh(ptr_result, result, src1_dsr);
    results[i] = result;
}
// results = [2.0, 6.0, 1.0]  (only max(0, last element of each segment))
```

Le's read at the time: with `save_address = false` the accumulator reloads each
op and reduces properly; with `save_address = true` the DSR auto-advances
between iterations but within each `@fmaxh` each element independently does
`*ptr = max(init, element)`, overwriting — only the last survives. Open
questions raised: is it intended; is there a loop-free segmented-reduction idiom
(e.g. `@map`); does it hit `@faddh`/`@fminh` too (yes for the reduction family;
`@fmach` map-style ops with save_address=true were fine). An isolated codex test
(`/home/lexu/build/save-addr-test/`) was spun up to pin which builtins and
whether it is sim-only across all of them.

## Pointers

- Personal memories: `wse3-dsr-reduce-after-map-returns-last-element`,
  `kv-farm-device-seed-harness`, `kv-farm-implementation-state`.
- `/home/lexu/build/save-addr-test/` (isolated test), `analyses/2026-09-15-attention-scaling-sidebyside/`.
