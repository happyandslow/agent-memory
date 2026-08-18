# WaferLLM Attention/FFN function-container Step 3 pre-review checkpoint

Status: captured

Situation: an Attention page and an FFN page must share one address-matched
executable slot on a Decode compute receiver.  Source-level closure, empty ELF
relocations, and symbol tables were insufficient to admit the pages because
the final gate also required complete receiver-image economics and WSE machine
call/branch/back-edge evidence across every emitted specialization.

## Durable result

Phase 1 Step 3 implementation and self-audit are complete and the result is
`READY_FOR_INDEPENDENT_REVIEW`; formal Step 3 remains
`PENDING_INDEPENDENT_REVIEW`.  Evidence is Grade E (static executable/link
evidence), not transferred-page execution or numerical correctness.

The canonical active choice is division Route A plus vecmat policy P.  Route B
is the deterministic page-private division fallback, and policy R remains a
non-active performance alternative.  Route A/B and P/R were all final-linked
and audited; P was not selected because it is faster, but because R is 120 B
larger in complete allocated receiver SRAM under both math routes:

| Route | Policy | Attention page | FFN page | Slot | Permanent receiver floor | Complete allocated receiver |
|---|---|---:|---:|---:|---:|---:|
| A | P | 4,188 B | 2,276 B | 4,352 B | 16,172 B | 20,524 B |
| A | R | 3,896 B | 2,040 B | 4,096 B | 16,548 B | 20,644 B |
| B | P | 4,236 B | 2,256 B | 4,352 B | 16,172 B | 20,524 B |
| B | R | 3,944 B | 2,020 B | 4,096 B | 16,548 B | 20,644 B |

R saves 256 B of aligned slot but adds 376 B of permanent receiver floor.  No
runtime performance comparison exists, so R cannot be described as better.

U04 was repaired in the generated pages by restoring the odd RoPE DSD offset
to 1 after each base reset.  Arena ABI alignment remains 2 B minimum while the
actual object placement contract is 4 B.  All receiver specializations passed
slot non-overlap; all nine R-policy five-word vecmat ABI call-site tuples passed
exact ordered-value and dispatch checks.  The actual deduplicated page-bearing
specialization counts are P-Attention 52, P-FFN 38, R-Attention 53, and R-FFN
39, not the earlier assumed count of 25.

## WSE machine control-flow closure

SDK 2.10 contains an authoritative Cerebras disassembly path even though
`elf2lst` cannot find a suitable `llvm-objdump`:

- SIF: `/home/lexu/Cerebras-SDK-2.10.0/sdk-cbcore-2.10.0-sdk-202604101435-4586d3f0d8.sif`
- emitter: `/cb/toolchains/llvm/cerebras/202602052146-6014-df837627/bin/elf2am`
- official AM parser: `/cbcore/py_root/cerebras/hwdebug_common/viz_service/plugins/gsv/ufv/rosetta_stone.py`
- AM record: little-endian word-PC, filename string, instruction string, source
  line; AM PCs and jump targets are 16-bit-word addresses, while ELF addresses
  are bytes.

A strict scan covered all 364 final page ELFs (182 per division route).  Every
4-byte instruction in `.m4_page` had an AM record; every direct call, ordinary
branch, and true backedge stayed inside `.m4_page`; every call target was a page
FUNC symbol; every return-address setup was consumed; and no control opcode was
left unparsed.  P has no non-return indirect jump.  Every R page has exactly one
approved sequence resolving to byte address `0x7a08`, and all 60 Route-A/B R
receiver ELFs define `m5r_resident_vecmat` as a FUNC at that address.

## Evidence and next gate

Authoritative compact evidence:

- `/home/lexu/WaferLLM/MeshJit-Decode/attention-ffn-phase1/step3-page-regions/m5r3-final-link/results/m5r3_step3_pre_review.json`, SHA-256 `1c8a3a20ed831510a354d3accfb8fe10198edb89ed74ffae711fe6588d184772`
- Route A machine audit SHA-256 `752d6431bd65749fc2656ac4c1db3395a718d683e82d7de5e332c8ad8322d350`
- Route B machine audit SHA-256 `ac77349d649dc485537ffff47a27d6867b002cadd0e89809aeba215ec4264950`
- design SHA-256 `ab2b7b280094fa771f2fddf95680ae968b8a8069d154ef49617c18dad2dd684a`
- tracking SHA-256 `fa52d80d216853594a7473d21a0fafda3e209f2e77eead033e6a6a423944bd81`

The next and only gate is a fresh independent review of the materialized
pre-review package.  If it passes, produce M6 and stop Phase 1 Step 3.  Do not
claim loader/transfer/invoke correctness, numerical equivalence, simulator or
device correctness, latency, or dynamic net savings; do not enter Step 4,
runtime implementation, or Phase 2 from this checkpoint.

This result supersedes the earlier M5R-3 `REVISE_EXTERNAL_CODE_ESCAPE` and
`REVISE_NO_WSE_AWARE_DISASSEMBLY` blockers; those remain useful historical
failure evidence, not current blockers.
