# Qwen3-4B on CS-3: prefill throughput measured; decode bsz>1 blocked by two small buffers — 2026-09-03

**Project:** wse3-performance-model
**Author:** claude
**Status:** captured

## Situation

You need the 4B prefill rate on CS-3 (for any TTFT / per-request latency
model), or you are about to compile the 4B decode deployment with `bsz > 1`
and expect it to "just fit" because KV capacity has headroom. Doc:
`wse3-performance-model/docs/analysis/2026-09-03-cs3-4b-prefill-and-bsz-measurement.md`;
raw logs/summary under `analyses/2026-09-03-cs3-4b-prefill-bsz/`.

## What happened / finding

- **Measured (device TSC, 0.85 GHz assumed; mock weights; `qwen3_4b-prefill`
  tree 17ccc489, `device.json` 2×4×256², MAX 8192, CHUNK 1024):** one
  8,192-token prompt = 624.9 M cycles = 735 ms = **11,142 tok/s**
  (wsjob-eptcyqjparjjjombvqiozp); four 2,048-token prompts = 165.09 M
  cycles = 194 ms each = **10,545 tok/s**, rounds byte-identical
  (wsjob-gbgvnij9crj7srrlc5nyce). Near-linear in length 2K→8K, unlike the
  1.7B artifact (super-linear). The 1.7B proxy (8,180 tok/s) underestimated
  4B by ~30 %.
- **Host-side companions:** first-token wait = 1.134× device span; KV egress
  to host after prefill 1.37–1.44 GB/s (8K: 1.21 GB in 840 ms) — the "host
  mirror" write path; appliance compile ~300 s + host weight build ~247 s +
  load ~107 s per launch.
- **Decode `bsz > 1` does not compile at device geometry** (bsz 2 @8K and
  bsz 4 @4K both fail identically; no execute job):
  1. FFN image: `decode.csl:113` `@comptime_assert(exp_p_dcache_bytes +
     2*silu_dcache_bytes <= 512)` — the two SiLU vectors are
     `align16(4·bsz·ffn_dim_per_pe)` = 160 B at bsz 1, 304 B at bsz 2, and
     they share the 512 B WSE-3 D-cache window at 0xFE00.
  2. HT tail: `partials_buf [bsz·V_per_pe_x] f32` = 4,752 B per batch on a
     PE with 4,218 B free → `.bss`/task-table/`.data.hi` overflow.
  Both are small-buffer placement limits, not KV capacity; both need kernel
  edits (move SiLU scratch out of dcache; bf16 or two-pass logits partials
  or a wider tail band). Simulator configs (`sim_2x4_bsz2.json`) pass only
  because per-PE dims are tiny there.
- Consequence for the serving comparison: the 4B CS-3 deployment is
  single-stream today; the Mooncake trace needs ~4.3 wafers single-stream
  to keep up with 6.7 req/s.

## Gotchas (procedural)

- `cs3-tmux ensure` needs a tty; from a non-interactive shell create the
  session with `tmux new-session -d -s claude` and `tmux send-keys` inside
  one `cs3-run ssh CS-3-cmd` call.
- The cs3-runner `cs3-run.sh` guard goes through `cs3-ssh.sh`, which points
  `SSH_ASKPASS` at the OTP generator — under the cs3-run OTP discipline run
  the guard on the CS-3 side instead (`timeout` + `csctl cancel` in the
  remote driver, `~/rsync/run_all_cs3.sh` pattern).

## Pointers

- `analyses/2026-09-03-cs3-4b-prefill-bsz/run_all_cs3.sh`, `parse_logs.py`, `results/summary.json`
- Mooncake model updated with the measured prefill rate:
  `analyses/2026-09-03-mooncake-trace-study/percall_latency.py` (`P_cs3`)
- related: `2026-09-03-mooncake-percall-latency-serving-trace.md`
