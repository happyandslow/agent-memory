# Qwen3 decode pageability assessment

## Scope and provenance

- Target: `happyandslow/WaferEngine` `models/qwen3_1p7b-e2e-pdSeparate/src/decode`
- Audited local commit: `fcfc8c163a4bebe0d886ae062334dfcb1b0d8406` (`HEAD == origin/main` in the local checkout)
- Online refresh: not performed because GitHub DNS was unavailable during this run
- Config: `model_config/test_sim_1x2blk_kv.json` (`Pw=8`, `Ph=16`, two blocks, `bsz=1`)
- CSL evidence: source closure + fresh SDK 2.10 compile-only linked ELFs; no simfab execution
- Pageability evidence grade: **E**. No ablation, dynamic receiver, correctness, or timing claim is made.

Commands and full machine-readable results are in `pageability.json`; the generated overview is `pageability.md`.

## Outcome

The best first page candidate in this decode is `rope_kernel`, not the whole attention or FFN body:

| Boundary | linked symbol | source closure | current decision |
|---|---:|---|---|
| `rope_kernel` | 600 B | 8 memory DSDs, DSR ids 1–6, no normal helper, no fabric DSD | best next direct ABI-pinned proof |
| `vecmat_computation_f32` | 236 B | 3 memory DSDs, DSR id 1, one `@map` callback | useful DSD/DSR correctness primitive, weak standalone SRAM target |
| `qk_norm_phase1` | 296 B | memory DSD/DSR plus runtime `while` | address-matched candidate; only one side of a larger split phase |
| `rmsnorm_kernel` | 844 B | local compute + `math.sqrt` + `comm_mod.all_reduce_bsz_f32` | split compute from resident collective/helper thunk first |
| `softmax_score` | 892 B | three `@map`s, `math.exp`, two collectives | resident-thunk transformation, not a direct page |
| `decode_layer_body` | 3,600 B | 24 direct stages, collectives, route repaint, helpers | unsupported by the currently validated loader as one page |

`ffn_gate_silu`, `process_kv`, and several small residual/cast bodies were inlined in this linked configuration, so source span cannot provide their page bytes. They must first be made `noinline` in an isolated working copy and relinked before economic ranking.

## Cross-PE specialization blocks one-payload broadcast today

The four compute-role ELFs contain equal-size symbols but different bytes:

| Candidate | addresses across compute ELFs | sizes | distinct payload SHA-256 |
|---|---|---:|---:|
| `vecmat_computation_f32` | `0x218`–`0x220` | 236 B | 4/4 |
| `rope_kernel` | `0x650`–`0x658` | 600 B | 4/4 |
| `qk_norm_phase1` | `0x8a8`–`0x8b0` | 296 B | 4/4 |
| `rmsnorm_kernel` | `0x304`–`0x30c` | 844 B | 4/4 |

Therefore equal symbol size is not payload identity. A single holder image cannot yet be broadcast to all compute PEs. The integration must either:

1. group receivers by identical compiled payload and provide one holder/catalog entry per group; or
2. pin/synchronize all relevant ABI and placement inputs, then relink and prove the hashes become identical; or
3. retain PE-specific pages and route each to its matching receivers.

This is a grade-E finding only. The hash differences are consistent with embedded addresses and PE specialization, but their exact instruction fields have not been decoded.

## Fabric admission result

The `csl-color-audit` view covers all 30 `decode_layer_body` stages:

- 16 color ids are lifetime-free in this view;
- none of IQ0–IQ7 or OQ0–OQ7 is free/unbound at any stage;
- two color-reuse assumptions are marked `ASSERTED` by the auditor.

So a free color does not yield a loader channel. A real integration needs a proved queue drain, rebind, route repaint, and fence at the selected phase boundary, or must reuse an existing compatible transport. It must not allocate a loader queue by color inspection alone.

## Linked image facts

Compute-role `.text` varies from 21,880 to 22,524 B in this test configuration. The candidate symbols above appear in four compute ELFs; two smaller decode-role ELFs do not contain them. Final ELF relocation sections contain zero entries, which means there is no runtime relocation support—not that embedded global or branch addresses are position-independent.

## SRAM economics

Economics are intentionally **unmeasured** at this stage:

- 600 B is the `rope_kernel` linked symbol size, not removable ownership;
- 236 B is the vecmat symbol size, not net receiver saving;
- no body-absent receiver exists yet;
- no slot, loader wrapper, DSR reservation, queue reservation, or fixed-address gap has been linked into a dynamic receiver.

The next economic gate should build baseline/body-absent/dynamic receiver variants for `rope_kernel` and report:

```text
gross removable ownership = SRAM(baseline) - SRAM(body_absent)
dynamic admission floor   = SRAM(dynamic) - SRAM(body_absent)
net receiver saving       = SRAM(baseline) - SRAM(dynamic)
```

Only after that comparison should `rope_kernel` be paired with a mutually exclusive second page for shared-slot accounting.

## Recommended next steps

1. Isolate `rope_kernel` in a holder/body-absent receiver harness using its real decode ABI; start with one compute-PE specialization and an address-matched slot.
2. Record every referenced global/DSD address and reserve DSR ids 1–6 with the same kinds on the receiver.
3. Prove holder payload transfer, receiver candidate absence, slot execution, and bit-exact Q/K output.
4. Repeat for the other compute-PE variants or eliminate the payload differences through ABI pinning.
5. Build the three receiver images and measure net SRAM before adding a second shared-slot candidate.
6. Keep collectives, route repaint, and task machinery resident; explore `rmsnorm_kernel` and softmax only after splitting compute pages from narrow resident thunks.
