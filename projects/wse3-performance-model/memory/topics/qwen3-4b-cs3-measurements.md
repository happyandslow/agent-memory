# Qwen3-4B CS-3 measurements

- CS-3 measurements pinned decode step cost, batch scaling, phase breakdown, forced-prefill rates, and stage-cut opportunities. Use raw cycles and 750 MHz calibration unless a specific artifact states otherwise.
- Decode step cost vs context is approximately 680,741 + 16.07 cycles/token, and current forced-decode row timing is ATTN ~127K + FFN ~50K cycles/token.
- 4B bsz>1 required experiment-only scratch fixes; stage pipelining is a stronger multiplier than raw batch scaling. Eight-stage forced prefill measured 7,373 tok/s at 2K and 6,326 tok/s at 8K after tail-colour race handling.
- Softmax is the dominant phase/context slope; exact pass fusion was byte-identical but slower, so the lever is DSD overhead/exp kernel/online softmax rather than naive pass fusion.
