# WaferLLM Decode Phase-1 Step-6 admitted Policy-P receiver

Date: 2026-08-21
Status: drained

## Situation

The earlier Step-6 result measured the Step-5 `D_both_profiles` receiver as a
static proxy.  It did not yet own the authoritative page identity/epoch latch,
the final load/run/release RPC roots, or a holder image with a real full-slot
sender and queue-drain path.  Step 6 therefore built the final-linked
`D_full_admitted` Policy-P receiver/holder/filler image family for SDK 2.10,
P=256, Route A, and bsz=1/2.  This remains static Grade-E evidence: no page was
transferred or executed on simfab/CS-3.

## Durable conclusion

Complete receiver SRAM uses the occupied union of all SHF_ALLOC ranges below
`0xc000`, including NOBITS and the fixed 1-KiB task table.  The admitted
Policy-P result is:

| Batch | B | A_both | prior Step-5 proxy | D_full admitted | D_full floor | B-D_full | recovery to +256 B |
|---|---:|---:|---:|---:|---:|---:|---:|
| bsz=1 | 25,716 B | 15,290 B | 30,670 B | 31,560 B | 16,270 B | -5,844 B | 6,100 B |
| bsz=2 | 27,180 B | 15,322 B | 32,198 B | 33,088 B | 17,766 B | -5,908 B | 6,164 B |

Thus the exact admitted static receiver is 890 B larger than the preceding
Step-5 proxy in both batches and the Phase-1 capacity gate is NO-GO.  The
controlled ladder attributes the 890 B as: topology normalization -8 B,
authoritative load/latch +554 B, phase loop +364 B, release plus real holder
protocol +100 B, and production-root pruning -120 B.  The final-linked receiver
section delta is `.text` +208 B, `.bss` +4 B, `.d1_loader_code` +104 B,
`.d_full_latch` +18 B, `.d3_runtime_code` +492 B, and `.d5_profile_code` +64 B.
`.cs.pe_state.misc_cfg` changes size but overlaps `.data.lo`, so it contributes
0 B to the occupied union and must not be added again.

The holder image owns two full zero-padded catalog slots, OQ2, an asynchronous
`@mov32` sender, queue-flush task/empty handler, and a holder identity latch.
Complete holder SRAM is 13,530 B at bsz=1 and 15,066 B at bsz=2; fillers use
4,440 B.  Holder SRAM and filler SRAM are whole-wafer overhead and are not part
of the per-receiver `B-D_full` subtraction.

## Frozen host-attested load contract

`d_full_load_page` is one layout-wide SDK RPC name exported by receivers,
holder, and fillers.  One blocking host launch invokes that name across every
role.  The holder streams the selected full slot and unblocks only after OQ2
drain; every receiver performs a synchronous fixed-count IQ2-to-slot `@mov32`,
publishes READY last, and then unblocks; fillers are no-ops.  Phase 1 treats the
blocking host return as the global load-completion attestation.  This is a
contract to validate later, not a runtime proof today.

The holder catalog may not remain linker-zero initialized.  The deterministic
host provisioning path extracts `.m4_page` from the frozen Attention/FFN ELFs,
checks raw and padded hashes from `page_catalog.json`, concatenates two full
slots, rejects an all-zero catalog, writes only holder `(P,0)`, and performs an
exact D2H readback before the first load RPC.  The check-only evidence records
8,704 B / 2,176 u32 words for bsz=1 and 10,240 B / 2,560 u32 words for bsz=2.
Runtime provisioning itself was not executed in Phase 1.

## Review corrections and evidence integrity

Four review findings were fixed: explicit holder catalog provisioning;
validation of a freshly regenerated machine-audit inventory rather than a
stale report; fail-closed tombstones before validation prerequisites; and hard
rejection of any SHF_ALLOC section crossing `0xc000` rather than silently
omitting it.  Six host-only tests pass.  Aggregate static validation reports
`COMPLETE_STEP6_NO_GO_CAPACITY` with zero evidence failures.

An expanded independent recheck has not yet passed: the local external review
invocation was blocked pending explicit authorization to transmit the larger
private source/evidence set.  Keep technical validation PASS separate from
independent-review status.

Canonical evidence:
`/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step6-dfull-admitted/`.

Drained 2026-08-22 into `memory/topics/meshjit-code-relocation.md` and `plan.md`.

## Next decision

Do not enter Phase 2 from this result.  Policy R still needs the same exact
admitted D_full measurement if it is to be compared fairly.  The immediate
optimization discussion should use 5,908 B as the worst-batch break-even gap
or 6,164 B for the evaluated +256-B admission margin, with D3 as the dominant
common-floor candidate.  Correct transferred-page execution remains a later
runtime-validation gate.
