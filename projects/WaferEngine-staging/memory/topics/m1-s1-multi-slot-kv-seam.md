# M1-S1 — multi-slot KV addressing seam: engineering learnings

> Curated, transferable learnings from implementing + verifying the multi-slot KV
> addressing seam in `qwen3_1p7b-decode` (M1-S1, 2026-07-26). **Plan/state live in the
> in-repo durable docs** (`milestones/M1-intra-pe-reuse.md`, `milestones/kv-reuse-tradeoff-register.md`,
> `PROGRESS.md`) — those win on any conflict. This note holds only the reusable engineering
> lessons, not the milestone status.

## The change in one line

Split the conflated `bsz` into a **storage axis** (`slot_count`, sizing the KV cache tiles)
and a **compute axis** (`bsz`, sizing every other buffer), linked by a per-lane
`active_slot[]` map that rides the KV-ingress meta tile. Provable-inert: at
`slot_count = bsz` with an identity map the result is bit-identical to before.

## Lesson 1 — destination = slot, source = lane

Adding a per-request storage dimension hits **every** place that indexes "by request", and the
compiler cannot tell the two meanings apart because both are `i16` in `[0, bsz)`. Three of the
four review bugs were the *same* mistake: a **source** buffer indexed by the slot id.

- `QKV_tile` (freshly projected K/V, packed `[Q | K | V]` by lane) — indexing K by `slot_idx`
  with `slot_idx >= bsz` silently reads out of the K region **into the V region**: V values get
  written into the K cache. No crash, no OOB, just wrong numbers.
- `kv_ingress_buf` (this round's ingress payload, sized `bsz * kv_cols * prefill_max_per_pe`) —
  the payload is M tiles; slot-indexing it reads another lane's tile or past the live region.

The rule that survived: **only the destination address carries the slot; every source buffer
stays lane-indexed.** Worth writing as a comment at each site, because the types don't say it.

## Lesson 2 — one addressing form, or the two copies will drift

The layout decision (contiguous fixed slots) was implemented as a seam:

```
fn k_cache_offset(layer, slot, pos) = (layer * slot_count + slot) * kv_cols * kv_len_per_pe + pos
fn v_cache_offset(layer, slot, pos) = (layer * slot_count + slot) * kv_len_per_pe * kv_cols + pos * kv_cols
```

Two forms coexisted for one revision: the hot sites used the seam while the KV-ingress copy kept
an inlined formula. The inlined copy was left at the **old** layer stride (`l * bsz`) after the
cache had been resized to `slot_count` — every layer then overlapped the next. This is the exact
failure the seam exists to prevent, and it appeared *because* the seam was only half-adopted.

Sub-lesson on the seam's shape: make `layer` a **parameter**, not a read of the "current layer"
global. The ingress path runs *before* `set_layer()` and has its own layer loop; a seam that
reads the global cannot be used there, which is what forced the second (drifting) copy to exist.

Cost accepted: `set_layer()` loses its "repoint every pointer to layer l" symmetry for KV only.
Worth it — under paging the per-layer base pointer stops being meaningful at all, so keeping it
would have left half the addressing outside the seam anyway.

## Lesson 3 — a checker that can compare nothing must refuse, not pass

The kernel's `KV-SEED` check (post-stop `read_symbol` of the KV tiles vs the host payload) was
handed the **last round's** `prefill_len_per_pe`. On a retain round that is `0`, so every
comparison sliced `[..., :0]`, `np.array_equal(empty, empty)` returned True, and it printed
**PASS having compared zero bytes**. It had been vacuous on every retain config since the
`plen == 0` meta-only heartbeat was introduced — invisible because a silent pass and a real pass
print the same word.

Two fixes, both general:
1. feed it the last round that **actually** ingressed (the round-0 prefix is never overwritten —
   decode only appends at `>= plen`);
2. add an explicit `if nothing_to_compare: print("skipped"); return`.

**Generalize:** any verifier whose input can legitimately be empty needs a third outcome besides
pass/fail. "Nothing to compare" must never render as success.

## Lesson 4 — an identity map cannot test an index

The obvious first multi-slot config (`SLOT_COUNT=4`, `ACTIVE_SLOTS=[0,1]`) would have passed even
if the seam ignored the slot index entirely. The config that has teeth is **non-identity,
non-contiguous and reversed** (`[3,0]`), plus two device-side reads:

- read the KV tiles back and confirm the payload landed **at the mapped slots**;
- confirm the **unmapped** slots are still exactly zero (cross-slot isolation) — this one holds
  even when the byte comparison is vacuous, so it is the more robust of the two.

Generally: when adding an indirection, the red test must permute the index, not merely widen it.

## Lesson 5 — check whether the host already owns the state before mirroring it onto the device

The design contract called for per-`(layer, slot)` device counters plus an on-device occupancy
table ("a slot with `iter_num == 0` is empty"). Implementation showed both are unnecessary here:
all active lanes share one sequence position, and the control plane is centralized on the host,
which already tracks each slot's valid length and sends the round's start. An idle slot's **content**
survives with no bookkeeping at all — writes only reach active slots; only its *length* needs
remembering, and that lives on the host. Removing it made the change strictly smaller.

## Structural fact worth remembering (decode kernel)

**Two globals pin every active lane to the same sequence position**, and both must be duplicated
before any true "ragged batch" (lanes at different current sequence positions) is possible:

1. the scalar `iter_num` is simultaneously the attention length **and** the per-lane stride of the
   *packed* `score` buffer (the buffer is allocated by capacity but packed by valid length);
2. the RoPE rotation state (`cos_cur/sin_cur`) has **no batch axis** and advances once per step
   outside the layer loop.

The corrected M1-S3 batching rule is therefore narrower than the first review conclusion:
mixed prefix-hit/prefix-miss lanes are legal **if the whole round starts at the same position**
(`start = min(L_match)` over active lanes) and all lanes walk to the same prompt end. A hit lane
then redundantly recomputes `[start, L_match)` and overwrites bit-identical K/V in its slot; the
batch's benefit is the minimum hit length across lanes. What remains illegal without a larger O1
redesign is **take-over raggedness**: one lane jumping its scalar/RoPE state to `L_match` while
another is still at an earlier position.

Good news for a future ragged implementation: the kv-head collective is already capacity-sized
with a zero-padded tail, so the fabric side needs no change — only local packing plus per-lane
local state/score layout/RoPE state.

## Config hygiene: unknown keys are silently ignored

Two independent bugs this session were **config key name mismatches** — `FORCED_DECODE_LEN` vs the
code's `FORCED_DECODE_LENS` (so a config's force-decode setting had never taken effect), and
`ACTIVE_SLOT` vs `ACTIVE_SLOTS` (which would have quietly degraded the multi-slot red test into a
duplicate of the inert one, passing for the wrong reason). `cfg.get(key, default)` makes every typo
a silent no-op. **An unknown-config-key assertion pays for itself.**

Slot-map validation should land with the reader: decide broadcast/length semantics explicitly,
reject duplicates (two lanes writing one slot is silent cross-contamination), and make a red config
prove it can fail before its PASS means anything. Identity maps and empty comparisons are positive
controls, not red tests.

## Host/device ownership of per-slot length

Per-slot KV **bytes** live on the device, but per-slot valid length stays in the host control plane
for S1/S2. The device needs one current scalar per active forward because active lanes share one
sequence position; on reactivation, the host's `kv_store` sends the slot's `retained_len` through the
meta tile and `round_reset` overwrites the scalar. A device-side `[layer][slot]` counter bank would
duplicate host-owned state and create drift.

The real host-side trigger is: **active set changes across rounds and later returns to a previously
used slot**. A single `last_idx` high-water mark is then wrong (`[0,1]` decodes to 3, `[2,3]` decodes
to 6, returning to `[0,1]` with a `-1` sentinel sends 6 and leaves holes). S2 should replace the
single sentinel/high-water path with an explicit per-slot valid-length table on the host; S1 static
maps do not need it.

## Environment

The Cerebras SDK's singularity container **cannot bind-mount paths under `/tmp`**
(`FATAL: container creation failed: ... doesn't exist in container`). A comparison worktree used
for a before/after run must live under `$HOME`.

## Verification recipe (reusable for any inert seam)

1. `git worktree add <under $HOME> HEAD` → run the same config on the pre-change code;
2. extract every `[LOGITDUMP]` record (simprint fp32 logits, all rounds × lanes × vocab shards)
   from both `sim.log`s and compare **element-exact**, not "within tolerance";
3. diff the verdict JSON fields as a second, independent signal;
4. only then run the red config, and compare it to the *inert* run the same way.
