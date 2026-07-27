#!/usr/bin/env python3
"""Force-decode context sweep: skip-compute vs pipelining, full device scale.

Window model (per config): DECODE_LENS[-1] = 256, WARMUP = 16 -> warmup_cycles = 17,
so the timed window is W = 239 steps.  F = 209 forces steps 0..208, of which
f = 209 - 17 = 192 fall inside the window; the remaining W - f = 47 are free.

    span(F=1)   = W * C_free
    span(F=209) = (W - f) * C_free + f * C_forced
"""
import re, sys, pathlib

LOGD = pathlib.Path("/tmp/claude-1023/-home-lexu-WaferEngine-staging/"
                    "e5dc6825-52b7-44ec-849c-4a107eaddb7d/scratchpad/logs")
W, f = 239, 192
N_LAYERS, MAX_LPB = 28, 4
FREQ_GHZ = 1.1

def span(cfg):
    for name in (f"dev_{cfg}.log", f"dev_{cfg.replace('test_device_','')}.log"):
        p = LOGD / name
        if p.is_file():
            m = re.search(r"Span cycles \(end - start\):\s+(\d+)", p.read_text())
            if m:
                return int(m.group(1))
    return None

print(f"Full device scale: 524,288 PEs | dim 2048 | {N_LAYERS} layers over 8 blocks "
      f"(max_layers_per_block={MAX_LPB}) | vocab 151,936")
print(f"PIPELINING predicts forced/free -> {MAX_LPB}/{N_LAYERS} = {MAX_LPB/N_LAYERS:.1%} "
      f"(flat / slightly rising with context)")
print(f"SKIP-COMPUTE predicts forced/free -> RISES toward 100% as context grows\n")
print(f"{'prefill':>8}{'kv/PE':>7}{'free us/tok':>13}{'forced us/tok':>15}"
      f"{'forced/free':>13}{'speedup':>9}")
print("-" * 65)
rows = []
for pref in (256, 768, 1792, 3840):
    s1, s2 = span(f"test_device_ctx{pref:04d}_F001"), span(f"test_device_ctx{pref:04d}_F209")
    if s1 is None or s2 is None:
        print(f"{pref:>8}{'':>7}{'  (pending)':>13}")
        continue
    c_free = s1 / W
    c_forced = (s2 - (W - f) * c_free) / f
    us = lambda c: c / (FREQ_GHZ * 1e3)
    print(f"{pref:>8}{(pref+256)//256:>7}{us(c_free):>13.1f}{us(c_forced):>15.1f}"
          f"{c_forced/c_free:>12.1%}{c_free/c_forced:>8.2f}x")
    rows.append((pref, c_forced / c_free))
if len(rows) >= 2:
    lo, hi = rows[0][1], rows[-1][1]
    print("-" * 65)
    print(f"trend: forced/free {lo:.1%} -> {hi:.1%} as prefill {rows[0][0]} -> {rows[-1][0]}")
    print("VERDICT:", "PIPELINING (stays near max_lpb/n_layers, far below 100%)"
          if hi < 0.4 else "SKIP-COMPUTE (climbs toward 100%)")
