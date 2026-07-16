# route-only files — no task/fn state machine

> Model `qwen3_1p7b-prefill`, ref config `test_sim_2x4_kv_varlen.json`. Companion note to the
> per-kernel task/fn state-machine set (`qwen3_1p7b-prefill.<kernel>.statemachine.{md,svg}`).

Three source files under `models/qwen3_1p7b-prefill/src/` carry **no runtime task graph**, so they
get no state-machine diagram — one line each:

- **`kickoff_relay.csl`** — a pure fabric relay: its `comptime { }` block is empty and every PE is
  inert (`kickoff_relay.csl:12`). The host paints `kickoff_color` `N→S` on the west column and the
  router forwards the 1-wavelet forward-start sentinel through the HT-band gap with **no PE program**
  (`kickoff_relay.csl:1-10`). No `task`, no `@activate` — nothing to draw.

- **`route_util.csl`** — shared route-config helpers only: `inline fn` wrappers over
  `@get_config`/`@set_config` (`set_route_1tx`/`set_route_2tx` at `route_util.csl:28-45`;
  `compute_route_word_*`/`apply_route_word` at `:52-74`). They are called **synchronously** from
  `comm_pe`/`ht_head`/`ht_tail` init and the runtime all-reduce-axis reconfig — plain function calls
  on the caller's stack, not activated tasks. No task graph of its own.

- **`route_calc.csl`** — compile/init-time route-direction calculation: pure `fn`s
  (`band_dirs`, `terminate_dir`/`terminate_band`, `get_params` at `route_calc.csl:59-185`) that
  return a `runtime_params_t` of per-PE RX/TX directions consumed by `comm_pe.csl` init. All
  data-flow, no control-flow tasks — nothing to sequence.

Where these functions appear as **edges** in another kernel's machine (e.g. `comm_pe`'s `reconfig`
route machine calling `apply_route_word`, or init calling `get_params`), they show up there as
`call:` (synchronous) transitions — see that kernel's `.statemachine.md`.
