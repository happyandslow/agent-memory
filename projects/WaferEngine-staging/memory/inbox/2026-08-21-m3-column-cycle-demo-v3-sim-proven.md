# M3 park/reload: NO_POP broadcast kills the segmented relay; column_cycle_demo v3 SIM-PROVEN — 2026-08-21

**Project:** WaferEngine-staging
**Author:** claude
**Status:** captured

## What happened / finding

- Situation this applies to: designing or resuming the M3 Mode-L park/reload column
  protocol (`bench/m3_park_band/`) while believing that the 8-command control-payload
  limit forces a segmented PREP/COMMIT CE relay for columns longer than 8 PEs, and that
  same-color CE reinjection is an unproven gate — the framing in the 2026-08-20 note
  `m3-park-tail-reload-transition.md` and in the `full_cycle_probe` design. That framing
  is superseded.
- **A single `SWITCH_ADV` control wavelet sent with NO_POP advances every
  advance-capable PE it passes** (routed-then-advance, wavelet survives to the end of
  the path). The 8-command limit only constrains *targeted* (pop=true) chains, never
  broadcast — so column length no longer needs boundary relays at all: 16 PEs and 256
  PEs use the same one sweep wavelet. Verified on simfab **and on the physical CS-3**
  (`popfalse_probe`, ledgers field-identical sim vs device). Hardware semantics +
  side-findings (pop corrupts the low-16 arg; spent control wavelets still fire
  RAMP-tap tasks) are promoted into the shared skill `csl-switch-adv-pop-semantics` —
  consult that, not older probe READMEs.
- **Why the v2 per-PE park TURN was dropped:** pop mode is per-PE-per-color *state*,
  not a wavelet attribute. One column cannot simultaneously host POP_ON_ADVANCE (each
  PE's TURN dying at its sender) and NO_POP (the sweep surviving the whole column), and
  the CE cannot safely time a mode switch between the two phases. v3: after
  `@queue_flush` drains its payload, each regular PE opens its north door by a direct
  `set_config` route rewrite (`RAMP→S` ⇒ `N→S`) — safe because opening the door *is*
  the release action, so no in-flight traffic can race it. Reload keeps per-owner
  demux TURNs (pop=true, terminated by RAMP-only routing) plus a zero-command FENCE
  that only P0 can catch, serving as the end-to-end drain proof.
- **`column_cycle_demo` is SIM-PROVEN** (16-PE default and N=10/E=5): strict checker
  validates exact park order N-1..0 at storage, dual-predicate join before reload,
  per-owner reload payloads with TURN-arg cross-check, FENCE landing only at P0,
  monotonic per-PE event stamps, `unexpected=0`. Single compile variant (pe_index from
  fabric coords, so 256-PE won't explode the build). Next gate: 256-PE run on real
  CS-3. Nothing committed.
- Gotcha found on the way `[root cause open]`: a storage-side `@queue_flush`
  empty-queue callback initiated from a **wavelet-task context** never fired, while the
  identical flush pattern on compute PEs (init-task context) worked every time. Worked
  around with a strictly stronger drain proof: gather-count completion itself requires
  the FENCE to have reached P0 and P0's ledger to have traversed the column back to
  storage. Recorded in the demo README; do not build a protocol step on a
  wavelet-task-context queue_flush callback without re-verifying it.

## Implications / next actions

- [ ] 256-PE `column_cycle_demo` run on real CS-3 (`launch_device.py --n-pes 256`).
- [ ] Integration leftovers deliberately deferred: round-boundary reset/re-arm
      (`SWITCH_RST`/`write_Y_routes` repaint) and the release condition — design noted
      in the demo README, to be written when merging into decode round boundaries.
- [ ] Fold the supersession into `m3-park-tail-reload-transition` at the next maintain
      pass (segmented relay + explicit ACK/GO fallback are no longer needed).

## Pointers

- `models/qwen3_1p7b-decode/bench/m3_park_band/column_cycle_demo/` (src, checker, README)
- `models/qwen3_1p7b-decode/bench/m3_park_band/popfalse_probe/` (sim+device evidence)
- skill: `csl-switch-adv-pop-semantics` (claude-skills repo)
- supersedes parts of: `memory/inbox/2026-08-20-m3-park-tail-reload-transition.md`

## Update 2026-08-21 (later same day): DEVICE-PROVEN at 256 PEs + A1 + queue_flush doc gap

- **`column_cycle_demo` is DEVICE-PROVEN at decode block height**: real CS-3
  (wsjob-frfycsmtzugnjjoitj5jjp), `--n-pes 256 --payload-len 64` — strict checker
  fully green: 16,384 park words verified word-for-word in exact 255..0 order,
  dual-predicate join, 256-owner reload demux with TURN-arg cross-checks, FENCE at
  P0 only, ledger gather in exact baton order, unexpected=0. Functional evidence
  only; no performance claim. (Also passed the appliance road: read_symbol is
  simulator-only and a zero-host-stream SdkLayout layout asserts in wio_group_config
  — both in the `csl-switch-adv-pop-semantics` skill.)
- **ASSUMPTION A1 (recorded, doc-checked):** the door-open rewrite relies on
  OQ-empty ⇒ "my payload cannot be overtaken by newly admitted northern wavelets
  inside the router". SDK `builtins_wse3.md` guarantees ONLY "the respective queue
  will be empty" (CE queue drained into the router) — router-internal no-overtake
  has **no documentation backing**. Falsifier is built in: storage's exact-order
  automaton re-tests A1 on every run; held at 16/10 PE sim and 256-PE device.
- The storage-side queue_flush non-firing gotcha above now **contradicts the
  documented semantics** ("activates ... once the queue becomes empty *or is
  already empty*"), so already-empty is not the explanation; root cause still open.
- **Per-request payload equations (qwen3_1p7b decode, serve 2x4, P=256,
  kv_dim=1024 ⇒ kv_cols=4 fp16/PE, layers-per-block lpb ∈ {2,4} as [2,4,4,4,4,4,4,2]):**
  per compute PE `S_PE(L) = lpb·ceil(L/256)·16 B`; per column = per storage PE
  `S_col(L) = 256·S_PE = 16·L·lpb B`; demo words `E = S_PE/4 = 4·lpb·ceil(L/256)`.
  Cross-checks: Σ_blocks 4096·lpb = 114,688 B/token = the known B_tok ≈ 112 KB;
  S_col(672, lpb=4) = 43,008 B ≈ the 42 KiB/PE storage-strip budget (the ~672
  tokens/block capacity in the M3 study). Next: payload-size variation experiment
  on the demo (round-boundary offload/reload overhead vs E), device-only numbers.
