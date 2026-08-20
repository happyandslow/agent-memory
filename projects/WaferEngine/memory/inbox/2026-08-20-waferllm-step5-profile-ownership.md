# WaferLLM Decode Phase-1 Step-5 profile ownership

Date: 2026-08-20

## Durable conclusion

For the active Route-A / Policy-P shared-slot receiver, SDK 2.10 and P=256,
final-linked Attention/FFN profile ownership is identical at bsz=1 and bsz=2:

- Attention profile delta: 884 B.
- FFN profile delta: 720 B.
- controlled union delta: 1,200 B.
- interaction: 404 B.

Complete receiver endpoints are 29,470→30,670 B at bsz=1 and
30,998→32,198 B at bsz=2. The metric is the maximum specialization-wise union
of SHF_ALLOC ranges below 0xc000, including NOBITS and the 1-KiB task table;
high-water and fixed gaps are separate.

The 1,200-B union is 1,032 B `.d5_profile_code`, 92 B D3 invocation/
continuation seam, and 76 B ordinary `.text` RPC admission. The 404-B
interaction is 236 B common D5 validation/control plus the common 92-B D3 seam
and 76-B RPC admission.

M5R's entry-local DSD contract supersedes old M3 `resident_prebind`: receiver
compute DSD/Kt/Nt/pointer/scalar ownership is 0 B. Removing 15 unused page DSR
declarations from D3 changes complete SRAM, 384-B `.data.lo`, 48 lowmem-init
objects, and 108-B hardware misc config by 0 B. Across bsz=1/2, all 52
Attention page specializations have the receiver-identical 108-B misc config;
all 38 FFN page specializations have its 72-B prefix. DSR incremental SRAM is
therefore 0 B, but kind/id reuse remains a serialized-lifetime protocol
constraint.

Evidence grade is E: 10 receiver final links, two bsz=2 canonical page control
links, 612 binder mutation cases, and full elf2am closure for 228 profile ELFs,
including the new ordinary `.text` admission path. It does not prove runtime
payload identity, monotonic load epoch, transferred execution, numerical
correctness, queue behavior, or Step-6 net economics. Initial page identity and
load epoch must come from the future authoritative loader metadata latch.

Four independent review-fix rounds converged to PASS. The final admission
validator binds each of the six 38-ELF machine-audit inventories exactly to the
current SRAM/build name-and-hash inventory, and writes a non-PASS tombstone
before prerequisites so a failed rerun cannot leave stale PASS evidence.

Canonical compact evidence:
`/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step5-profile-costs/`.
Raw reproduction archive:
`/home/lexu/WaferEngine-staging/.step5_profile_costs/artifacts/`.

## Deferred optimization

D3's `d3_execute_operation` and `d3_invoke_bound_entry` are large because the
compiler expands tuple comparisons into straight-line control flow. Keep a
future optimization item, but do not mix it into ownership baselines. The first
constant descriptor-table/dynamic-index probe was 920 B worse, added 260 B BSS,
288 B runtime code, 372 B ordinary text, and introduced external memcpy closure.
Only revisit with a different fixed-index encoding or new compiler-lowering
evidence.
