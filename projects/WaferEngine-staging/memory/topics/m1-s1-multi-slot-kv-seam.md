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

**The half-migration is the recurring shape, not the typo.** The fourth review bug was the same
family from the other side: `set_layer()`'s KV pointer repointing had been *commented out* while
the use sites still read those pointers — so they silently kept their declaration-time value and
**every layer addressed layer 0**. Both this and the drifting inlined formula are "migration
started, old consumers left in place". When retiring an addressing mechanism, the search that
finds these is *who still reads the thing I stopped updating*, not *did I update everything I
changed*.

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

Both fixes are implemented and exercised, and the vacuousness is now confirmed *empirically*, not
only by reading: on the same config the pre-change baseline prints `prefill_len_per_pe=0` and the
fixed version prints `prefill_len_per_pe=1`. A worthwhile habit — when you claim a check was
vacuous, make the check *print the width it compared*, so the claim is falsifiable from a log.

Same shape, still open once the active set stops being static: `_kv_seed_check` and the isolation
check both key off `last_active_slots_rnd`, so the idle set should mean *slots never active in any
round*, not *slots not active in the last round* — otherwise a slot holding real KV from an earlier
round gets reported as an isolation failure `[unverified — read off the code, not yet hit]`.

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

## Lesson 6 — the numpy oracle is not independent by default

You are about to gate a KV-reuse change on `numpy_oracle_*` — either as the red half of a negative
control ("run the red config on the old code, it must FAIL") or as the correctness gate for the
widened cache. The oracle agrees with the device, so the change looks sound. It does not follow
unless the oracle is independent of the thing under test, and in this codebase it is coupled two
ways, both silent (all read off the code in-session, 2026-07-27):

1. **The oracle carries a second copy of the formula under test.** The per-slot high-water
   computation exists **three times** — `kv_store.last_idx`, `launch.py:2936` `_hw`,
   `host/oracle_fp16.py:633` `high_water`. So "run the red config on the old code and expect FAIL"
   gives *device wrong, oracle wrong in exactly the same way, comparison agrees, **PASS***. A
   control that discriminates has to break the shared copy: **new (per-slot) oracle vs old device
   must FAIL**, plus old-device round-2 logits ≠ new-device round-2 logits. Related trap: the bug
   is invisible unless rounds have **unequal** lengths — fresh rounds take `start_idx = pl_per_pe`
   and never read `last_idx`, so with equal-length rounds the single scalar coincidentally equals
   the correct per-slot value and the old code passes *honestly*
   (`DECODE_LENS = [8, 16, 8]` forces the split; proposed, not yet run `[unverified]`).

2. **The oracle shares the host's RNG draw order.** `launch.py:1857` says so in-repo: *"RNG order
   MUST match oracle."* Mock weights and mock K/V come from `RandomState(2025 + global_l)` in a
   fixed sequence, and `oracle_fp16.py:92-93` replays the same order with the same seeds.
   Consequence: the natural-looking edit — widening `for _ in range(bsz)` to `range(slot_count)`
   so the baked cache matches the new device width — **must not be made**. It draws `2*(S−M)` extra
   values and shifts every subsequent weight, so device and oracle run on different FFN weights.
   The symptom is *small numeric drift everywhere* — the hardest kind to attribute — plus a failing
   byte-identity gate that looks like the seam's fault. **Correct shape: keep the draw count at
   `bsz`, then zero-pad to `slot_count` and place by `active_slot[b]`** — the RNG stream is
   untouched and only the baked symbol layout changes. (Independently, an S-wide staging array also
   changes the wire length: the streaming payload is M tiles.) Since no config takes the bake path
   today, the cheap correct move was an assertion `kv_stream_ingress or slot_count == bsz`.

**Generalize:** before treating a reference implementation as evidence, ask what it *shares* with
the thing under test. A duplicated formula makes agreement meaningless; a shared pseudo-random draw
order makes any change in draw **count** silently invalidate every downstream comparison.

## Structural fact worth remembering (decode kernel)

**Two globals pin every active lane to the same sequence position**, and both must be duplicated
before any "ragged batch" (lanes at different lengths) is possible:

1. the scalar `iter_num` is simultaneously the attention length **and** the per-lane stride of the
   *packed* `score` buffer (the buffer is allocated by capacity but packed by valid length);
2. the RoPE rotation state (`cos_cur/sin_cur`) has **no batch axis** and advances once per step
   outside the layer loop.

Good news for a future ragged implementation: the kv-head collective is already capacity-sized
with a zero-padded tail, so the fabric side needs no change — only local packing.

## Config hygiene: unknown keys are silently ignored

Two independent bugs this session were **config key name mismatches** — `FORCED_DECODE_LEN` vs the
code's `FORCED_DECODE_LENS` (so a config's force-decode setting had never taken effect), and
`ACTIVE_SLOT` vs `ACTIVE_SLOTS` (which would have quietly degraded the multi-slot red test into a
duplicate of the inert one, passing for the wrong reason). `cfg.get(key, default)` makes every typo
a silent no-op. **An unknown-config-key assertion pays for itself** — it is still **not
implemented** as of the S1 close-out, so this is an open hole, not a fixed one.

Two follow-ons worth carrying: (i) per-key validation is the fallback where a global assertion is
missing — for `ACTIVE_SLOTS` that means length == `bsz`, every value < `SLOT_COUNT`, and **no
duplicates** (a duplicate = two lanes writing one slot = silent cross-contamination); (ii) decide
the **broadcast-vs-per-round rule** at the same time you add the key. A single map `[3,0]` sliced
per round as `active_slots[rnd*bsz:(rnd+1)*bsz]` yields `[3,0]` for round 0 and **`[]`** for rounds
1–3, shrinking the meta tile by two i16 — that one at least trips the KV band-size assert loudly.

## Constraints reasoned out in review became assertions, not doc lines

A design review produces a list of "this must hold" statements. Writing them into the milestone doc
means the next person has to read the doc; every one that could be checked cheaply at run time was
made an assertion instead. What S1 shipped as guards: i16 overflow of the addressing seam; the
meta-block fabric extent; `ACTIVE_SLOTS` length / range / duplicates; **retain-round + remapped
active set rejected** (it would resume an empty slot); and `slot_count == bsz` on the bake path (see
Lesson 6 for why). The single constraint left as prose — the unknown-config-key check — is also the
one still unimplemented, which is the pattern in miniature.

Side effect to expect: a guard can block your own negative control. On current HEAD the S2 red
config trips the `retain + remap` assertion *before* reaching the code under test, so that guard has
to be temporarily disabled for the control to run.

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

### What the two gates actually proved (S1 close-out, sim 2×2 / 7-layer, ≤16×16 PE)

Recorded so the strength of the evidence is not later remembered as stronger or weaker than it was:

- **Inert gate** (`slot_count = bsz`, identity map, vs a worktree of the pre-change HEAD, same
  config): **bit-identical over 48 `[LOGITDUMP]` records / 192 fp32 logits**, plus identical verdict
  fields. Element-exact, not within tolerance.
- **Slot-shift invariance** (`SLOT_COUNT=4, ACTIVE_SLOTS=[3,0]`): bit-identical to the inert run —
  correct, since changing slots only changes addresses — plus `KV-SEED PASS slots=[3,0]` (device
  read-back matched the host payload byte-exactly *at the mapped slots*) and a new
  `KV-ISOLATION PASS` (the unmapped slots still exactly zero after four rounds).

What that does **not** cover: it is one kernel, in simulation, with a *static* active set. The
`min(L_match)` mixed-batch rule and everything that varies the active set per round are untested
(S2/S3). A red config with `SLOT_COUNT=5` — leaving one slot genuinely untouched in every round —
is what keeps the isolation check meaningful once the active set starts moving.
