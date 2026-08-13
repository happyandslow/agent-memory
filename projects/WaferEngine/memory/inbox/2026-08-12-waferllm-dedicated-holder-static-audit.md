# WaferLLM Decode vecmat dedicated-holder static gate

Date: 2026-08-12
Project: WaferEngine
Status: captured; CS-3 execution pending

`/home/lexu/WaferLLM/MeshJit-Decode/mirror-xq-phase/` now separates the
function-storage holder from every Decode compute PE.

- `decode_dynamic.csl` is receiver-only: it has the 512-B slot, 38-B ABI,
  IQ2/fabin receive, admission wrapper, and a 4-B layout-wide payload RPC stub.
  It has no full payload, OQ2/fabout sender, holder variant param, or candidate.
- `holder.csl` owns the 512-B payload catalog at 0x9000 and OQ2/fabout sender.
  Its final ELF has no Decode tensors, collective state, slot, ABI, or candidate.
- All seven final compute ELF variants have identical section sizes: text 5796
  B, data.lo 144 B, data 66 B, bss 886 B, slot 512 B, ABI 38 B, payload stub 4 B.
- Receiver candidate absence, slot at 0xa000, resident/receiver ABI initial
  image equality, 264-B payload identity, and empty relocation tables still
  pass final-linked audit.
- A CSL rectangle cannot contain holes. The P=4 layout therefore occupies a
  5x4 rectangle: 16 compute receivers, one active holder at (4,0), and three
  minimal filler PEs at (4,1..3). The fillers own no payload/slot/ABI/candidate
  or code color queue. This is a 20-PE artifact and is not run in local sim.
- `csl-color-audit` still refuses this workspace because it lacks the tool's
  expected launch.py; the artifact records a source-derived ledger instead of
  claiming a tool verdict. Code color 1/IQ2-OQ2 is disjoint from Decode colors
  5-9/queues 3-7.

Primary audit:
`MeshJit-Decode/mirror-xq-phase/results/elf_audit_dedicated_holder_test_p4_b2.json`.
Next gate is CS-3 resident-vs-dedicated-holder dynamic bit-exact execution.
