# WaferLLM Decode Phase-1 Step-6 static-proxy economics

Date: 2026-08-20
Status: drained 2026-08-21 into `memory/topics/meshjit-code-relocation.md` and `plan.md`

## Situation

When deciding whether the Attention/FFN shared executable slot actually frees
receiver SRAM, do not compare the functional baseline `B` directly with an
incomplete source ablation or mix complete-image metrics. The current
production-shaped comparison uses Route-A / Policy-P, SDK 2.10, P=256, and
both bsz=1 and bsz=2. `A_both` is only an ownership ablation; Step-5
`D_both_profiles` is only a final-linked static receiver proxy, not yet the
production-authoritative transferred-page receiver.

## Durable conclusion

Using the same final-linked SHF_ALLOC occupied-union metric below `0xc000`
(including NOBITS and the 1-KiB task table):

| Batch | B | A_both | D_full_static_proxy | joint removable | proxy floor | B-proxy |
|---|---:|---:|---:|---:|---:|---:|
| bsz=1 | 25,716 B | 15,290 B | 30,670 B | 10,426 B | 15,380 B | -4,954 B |
| bsz=2 | 27,180 B | 15,322 B | 32,198 B | 11,858 B | 16,876 B | -5,018 B |

The old bsz=1 result `-4,942 B` was a metric-mixing error: it subtracted the
30,670-B occupied union from B's 25,728-B high-water. The correct same-metric
result is `25,716 - 30,670 = -4,954 B`.

The frozen static proxy therefore fails capacity in both batches. Recovering
to zero requires 5,018 B in the worst batch; reaching the evaluated +256-B
alignment margin requires 5,274 B. The 256-B margin is only one alignment
quantum and does not cover unresolved production protocol seams.

## Scope of the verdict

Static evidence is `PASS_STEP6_STATIC_PROXY_EVIDENCE / Grade E`, but the design
Step 6 gate remains `REVISE_STEP6_DFULL_UNRESOLVED` and open. The proxy includes
one slot, D1 load path, D2 control/arena/invoke, frozen D3, and both Step-5
profiles. It does not freeze the authoritative page-id/epoch/payload latch,
all-receiver completion/global quiescence, holder drain/fence, or final
production-versus-audit RPC ownership. Those changes may add, remove, or
replace code, so the proxy is neither a strict lower nor upper bound on exact
production `D_full`; do not generalize the negative proxy result into a
universal design NO-GO.

High-water remains an address-pressure diagnostic only. For bsz=1, B/A/proxy
high-water is 25,728/15,296/39,432 B with 12/6/8,762 B of holes below
high-water. For bsz=2 it is 27,184/15,328/39,432 B with 4/6/7,234 B of holes.

## Holder and ownership accounting

Step-4 fixed-full-slot transfer is authoritative. Two holder payload arrays
cost 8,704 B at bsz=1 and 10,240 B at bsz=2. Linked payload contents are
6,464/7,340 B and zero-tail padding is 2,240/2,900 B. The 52 Attention and 38
FFN specialization records collapse to one payload hash per phase, so the
catalog stores two blobs, not 90 copies. Catalog metadata, sender/OQ2/fabove
state, replicas/fillers and global fencing remain unmeasured whole-wafer
overhead and must not be charged against per-receiver `net_free`.

The measured 1,200-B Attention-and-FFN profile union is already in the proxy.
Unaccounted page-specific retention is 0 B, receiver compute DSD pool is 0 B,
and incremental DSR SRAM is 0 B, while serialized DSR lifetime remains a
protocol constraint.

## Evidence and next decision

Two independent review-fix loops converged to PASS. The final validator binds
exact ELF inventories, raw per-ELF section accounting, the four CSL inputs and
configs, command-addressed bsz=2 source trees, Step-4 full-slot semantics,
upstream reports, tools, and the frozen semantic contract. The compact evidence
is under
`/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step6-exact-economics/`.

Stop before Step 7 and Phase 2. The agreed next discussion is D3 SRAM
optimization against the measured 5,018-B zero / 5,274-B +256-margin target.
Exact design Step 6 can close only after the production seams above are frozen
and a final-linked `D_full_admitted` is measured.
