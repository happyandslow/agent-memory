# Spec-dec sample on real Qwen3-1.7B kernels — dual-kernel in-order deployment (v1)

Date: 2026-06-30
Session: specdec-dual-kernels
Repo: WaferEngine (`waferengine/samples/specdec` + `models/qwen3_1p7b-{prefill,decode}`)
Status: DESIGN — pending user review before writing-plans.

## 1. Goal

Replace the spec-dec sample's v1 `passthrough.csl` oracle kernel with the **real
Qwen3-1.7B prefill + decode CSL kernels**, with **real HF weights on both
kernels**. Both kernels are **co-resident in one `SdkLayout`** (vertical stack),
**compiled and loaded once**; the prefill→decode switch transfers **only the KV**
(no kernel reload). Add the minimal on-chip operations the decode kernel needs so
it behaves as the spec-dec **DRAFT model** described by `samples/specdec/proto`.

> **Revision note (2026-06-30):** earlier drafts chose sequential launch +
> cold-start decode. Superseded — we now **co-reside both kernels (single load)
> and hand off KV at the switch**, so decode is **warm-started** from the prompt
> (real continuity) and the decode kernel is never reloaded between phases. This
> makes a per-request prefill→decode serving loop viable (switch cost = a KV
> transfer, not a ~2.5-min recompile+reload).

## 2. Topology (confirmed)

Per `samples/specdec/README.md`, **the CS-3 chip is the DRAFT model**, not the
verifier. The external GPU is the TARGET/verifier. Each round the chip is asked
to produce `draft_len = 16` candidate tokens; the GPU returns how many of the
previous round's drafts it accepted plus its own correction token(s). So the
chip's job is **autoregressive generation of 16 draft tokens per round** — which
the decode kernel already does — plus a **round boundary operation** (rollback +
re-seed) it does not do today.

This is NOT parallel verification of K tokens in one pass; the chip never scores
candidates. That removes the heavy "K parallel attention paths / per-candidate
snapshot" work that a verifier topology would need.

## 3. Key facts that shape the design (from investigation)

- **KV never leaves either chip.** Prefill keeps K/V on-device (`V_stash`,
  `prefill.csl:760`) and emits only the last-token hidden state → HT_tail → one
  sampled token. Decode zero-inits its KV and only uses `PREFILL_LEN` to offset
  `iter_num`/RoPE. There is no on-chip prefill→decode KV bridge.
- **Both kernels co-reside (vertical stack).** Each kernel is `Pw×Ph = 512×512`
  (real footprint ~Pw+HT flanks wide × ~514 tall); usable WSE-3 fabric is
  ~762×1172. They do NOT fit side by side (≈700+700 > 762 wide) but DO **stack
  vertically** (≈514+514 ≈ 1028 < 1172 tall, each ≤762 wide). This is exactly what
  the deleted `build_*_layout(layout, origin, name)` origin-offset/namespacing
  adapters were built for — they get restored/finished and both regions go into
  one `SdkLayout`. Combined-compile feasibility (two transformers in one program)
  and host-edge I/O-port placement for the lower (offset) region are the two
  placement risks to retire early with a compile-only check.
- **KV `set_symbol_all` is compile-time only**, so warm-starting decode from
  prefill's KV at the switch needs a **runtime** KV-import path into decode (it
  cannot be `set_symbol`'d on a live runtime). See §7.2.
- **Cold-start decode with real weights already works on device.** The
  integration `launch.py` honors `cfg["real_weights"]=True` with no
  `kv_cache_file` → loads real Qwen3-1.7B weights via `integration/hf_weights.py`
  + `integration/device_reshard.py`, zero-inits KV, decodes from a seed token.
  This path passed the device chain (`_runs/device_chain_e2/...tokenmatch.log`,
  CHAIN PASS). So real-weight **decode** is a config, not new infra.
- **The integration `*.py` sources are deleted from the working tree** but full
  copies survive under
  `models/qwen3_1p7b-decode/integration/_staging_chain_e2_sim/.../integration/`
  (`run_pipeline.py`, `hf_weights.py`, `device_reshard.py`,
  `prefill_kv_unshard.py`, `run_chain_sim.py`, staging `launch.py`). These must
  be restored to `models/qwen3_1p7b-decode/integration/` as part of the work.
- **`hf_weights.HFWeights` is kernel-agnostic** — it reads HF safetensors into
  oracle orientation per layer (`Q,K,V,O,UP,GATE,DOWN,q_norm,k_norm,norms`,
  `embed`, `lm_head`, `final_norm`). `device_reshard.py` then packs to the
  **decode** kernel's per-PE tile layout. **Prefill's banked layout differs** and
  has no loader yet (see §6).
- **The spec-dec gateway/proto/codec layer already matches qwen3-decode's
  south-blob layout** (`sampled_off=12`, `south_wlts=14`, derived in
  `codec.derive_counts`). So gateway/translate/codec stay UNCHANGED; only the
  appliance seam changes.

## 4. The spec-dec round algorithm (what the decode kernel must do)

The chip maintains its own committed length `C` (count of confirmed KV positions)
as on-chip state across rounds. The codec round payload is
`[flags, num_accepted, num_correction, correction_id…]` — it does **not** carry
`C`; the chip tracks `C` itself, consistent with the proto's stateless gateway.

Per round (given `A = num_accepted`, `m = num_correction`, correction ids `c₀…c_{m-1}`):

1. **Rollback**: set `iter_num ← C + A`. Last round the chip speculatively wrote
   16 draft K/V at positions `C…C+15` with `iter_num = C+16`; only `A` were
   accepted. Because attention reads are length-bounded by `iter_num`
   (`@set_dsd_length(right_matrix_dsd, iter_num)`) and writes overwrite at
   `iter_num`, **resetting `iter_num` is the entire rollback** — no KV erase.
2. **Ingest corrections**: feed `c₀…c_{m-1}` as autoregressive decode steps at
   positions `C+A … C+A+m-1` (each writes K/V; RoPE angle from the position
   table, §5.2). The output sampled after the last correction `c_{m-1}` is the
   first new draft `d₀`.
3. **Generate drafts**: continue autoregressively feeding `d₀…d₁₄` until 16
   drafts `d₀…d₁₅` are emitted (one south blob each, token id at `sampled_off`).
   `iter_num` ends at `C + A + m + 15`.
4. **Update state**: `C ← C + A + m` (accepted drafts + committed corrections).
   The 16 emitted drafts are speculative beyond `C` for the next round.

Round 0 (no commit): `C` initialized from the prefill seed (see §7); feed the
seed token, generate 16 drafts at positions `1…16`.

`k` is fixed at 16 (compile-time), enforced by the gateway today.

## 5. Decode kernel edits (`models/qwen3_1p7b-decode`)

Scope: change the runtime loop from "one host seed → `MAX_OUTPUT_LEN` steps →
done" to "**one spec-dec round per host exchange, looping forever**", plus the
round-boundary ops. Targets `src/decode.csl` (+ `ht_head.csl` for the token
inject) and `launch.py`/round driver.

### 5.1 Per-round ingest + re-arm (io_pipeline repeated-exchange pattern)
- Replace the single startup hidden-state seed with a per-round input read of the
  round payload `[flags, num_accepted, num_correction, correction_id…]` on the
  input stream.
- After emitting 16 drafts, re-arm and block for the next round's payload. This
  is the self-re-arming kernel pattern already proven in io_pipeline
  (`csl_sdklayout_repeated_stream_exchange`, ~160µs/op).
- The outer loop runs forever (no `MAX_OUTPUT_LEN` terminator); `MAX_SEQ_LEN`
  still bounds total positions.

### 5.2 iter_num rollback + RoPE position table
- Maintain `C` (per-PE committed depth) in a bank alongside `iter_num_bank`.
- At round start, set `iter_num_bank[li] ← per_pe(C + A)` for every layer, where
  `per_pe(L)` is the round-robin owner count the kernel already uses for
  `prefill_len` (positions with `pos % P_BLOCK_SIZE == local_py`).
- Replace the current pure-incremental cos/sin **delta** advance with a
  **precomputed per-position RoPE angle table** (cos/sin for positions
  `0…MAX_SEQ_LEN`), uploaded once via `set_symbol_all`, indexed by `iter_num`.
  This gives correct angles after an arbitrary-magnitude rollback. Size is modest
  (`head_dim/2 × MAX_SEQ_LEN` bf16, already sharded per-PE like the existing
  freqs).

### 5.3 Correction-token / draft-token feed
- Each round's first `m` fed tokens are the host correction ids; route them into
  HT_head's existing token-embedding path (the same path that today consumes the
  on-chip sampled token for steps ≥1), overriding the on-chip sample for those
  steps. Subsequent steps feed the chip's own sampled drafts (unchanged path).

### 5.4 Emit
- Emit exactly 16 draft blobs per round (the per-step top-K/sampled south blob
  format is unchanged; mux relays east to host). The driver pulls
  `blob[sampled_off]` for each of the 16.

### 5.5 Real weights + runtime KV
- Set `cfg["real_weights"]=True`. Reuse the staging `launch.py` real-weight path
  (`HFWeights` + `device_reshard.weights_to_device` +
  `embed/lm_head/final_norm_to_device`), restored to `integration/`.
- **No compile-time `kv_cache_file`** — decode's `XKCache/XVCache` compile as
  zero-init and are **filled at runtime** by the KV-import path at the switch
  (§7.2). This is the change from the prior `--kv-source` flow, which loaded KV at
  compile time via `set_symbol_all` (and thus required a recompile per prompt).

## 6. Prefill kernel: real-weight loader (the largest new piece)

Prefill currently has mock weights only and no real-weight path. The decode-side
`device_reshard.py` targets decode's tile layout, which differs from prefill's
**banked, fused** layout. New work: a prefill weight packer (e.g.
`integration/prefill_device_reshard.py`) that reuses `HFWeights` and produces
prefill's banks, sharded per prefill's geometry (dim along Y, seq along X):

| Prefill bank | HF source (via `HFWeights.layer`) | Packing note |
|---|---|---|
| `rms_w_x_bank` (L·dim_per_pe) | `W_attn_norm` | per-layer banked |
| `rms_w_z_bank` (L·dim_per_pe) | `W_ffn_norm` | per-layer banked |
| `q_norm_w_bank` (L·dim_per_pe) | `q_norm` | Qwen3 QK-Norm |
| `k_norm_w_bank` (L·kv_dim_per_pe) | `k_norm` | Qwen3 QK-Norm |
| `W_qkv_bank` (L·dim_per_pe·`fused_qkv_Nt`) | `Q,K,V` | **fuse** Q\|K\|V; `Nt = dim_per_pe + 2·kv_dim_per_pe`; match prefill column perm |
| `W_o_bank` (L·dim_per_pe·dim_per_pe) | `O` | post-shard transpose as prefill expects |
| `W_upgate_bank` (L·dim_per_pe·`upgate_Nt`) | `UP,GATE` | **fuse** up\|gate; `Nt = 2·ffn_dim_per_pe` |
| `W_down_bank` (L·ffn_dim_per_pe·dim_per_pe) | `DOWN` | |
| `we_buf_0` (HT_head) | `embed` | prefill HT_head embed tile |
| `lm_head_tile` (HT_tail) | `lm_head` | prefill HT_tail tile (DIM-outer) |
| `W_final_norm_tile` (HT_tail) | `final_norm` | |
| `freqs_q/k_cos/sin` | host-computed | already real (RoPE, θ=1e6); keep |

Open implementation risk: prefill's Q/K column interleave and the fused-QKV
ordering must match the kernel's on-chip RoPE/QK-Norm expectations (mirror the
care taken in decode's `_perm_WQ`/`_reshard_K_dim`). This is the most likely
source of numeric bugs and the main reason §9 leans on a host oracle.

Prefill needs **no functional CSL edits** for v1 — it stays a one-shot prompt →
first-token kernel. Only the real-weight loader and a thin run wrapper are new.

## 7. Deployment / spec-dec wiring (co-resident, single load, KV-only switch)

New `QwenDraftAppliance` in `samples/specdec/appliance.py`, a drop-in for
`PassthroughAppliance` (same `exchange()` contract → gateway/translate/codec
untouched). It builds and loads **both kernels once**, then per request does a
KV-only switch.

### 7.1 One co-resident layout, one load
- `build_layout(layout)` places **both** regions in one `SdkLayout`: prefill at
  origin `(0,0)`, decode at origin `(0, prefill_height)` (vertical stack), using
  the restored origin-offset + region-namespacing adapters (`build_prefill_layout`
  / `build_decode_layout`). Both load real weights (§5.5, §6).
- Host streams created for: prefill prompt-in + first-token-out; decode round-in +
  16-draft-out; and the **KV transfer** ports (§7.2).
- One `compile()` → one `SdkRuntime.load()` → one `run()`. Decode is armed but
  idle until it receives KV + seed.

### 7.2 The switch = KV-only handoff (no reload)
Per request:
1. Send prompt tokens to the prefill region; it runs and produces (a) the
   first-token blob and (b) its on-chip KV.
2. **Drain prefill KV → reshard → load into decode at runtime.** Recommended:
   **host-round-trip within the single live runtime** — prefill drains KV to host
   (chip-drain wire, `prefill_kv_unshard.unshard_wire` → canonical K/V); host
   reshards to decode layout (`device_reshard.kv_to_device`); host loads it into
   decode's `XKCache/XVCache` via the runtime KV-import path. KV-import mechanism
   is one of: **(a)** `memcpy_h2d` into the KV symbols (co-resident layout built on
   the memcpy framework), or **(b)** a streaming KV-import port + a decode kernel
   drain task. Pick during implementation; (a) is less new CSL if memcpy coexists
   with the stream ports, (b) is more self-contained. A fully **on-chip**
   prefill→decode KV shuttle (no host) is the faster v-next but needs cross-region
   routing + on-chip reshard.
3. Set decode `C`/`iter_num`/RoPE base to `prompt_len`; seed token_ids[0] from the
   prefill first token. Decode is now warm and continues the prompt.
4. Drive spec-dec rounds: each `exchange(u32s)` sends the round payload, receives
   16 draft blobs, returns `[blob[sampled_off] …]` (existing 1-send / 16-receive
   contract).
5. Next request: re-run prefill (overwrites prefill KV), re-handoff (overwrites
   decode KV + resets `C`/`iter_num`). No reload at any point.

`appliance_handlers.build_handlers` `real` branch → `QwenDraftAppliance`.
`config/v0.json` keeps `draft_len=16`; add a model-config pointer
(`test_device_2x2blk*.json`) and HF path (`$HF_MODEL_PATH`).

The 4 GB HF checkpoint reaches the pod via the existing per-shard `stage()` path
(`launch_chain_device.py`); the spec-dec `LauncherBridge` staging must include
the `integration/` tree and the checkpoint, mirroring `run_pipeline`'s flow.

## 8. Risks / known v1 limitations

- **Combined compile.** Two transformer kernels in one `SdkLayout` is a large
  program; compile time and placement (vertical stack + host-edge ports for the
  offset region) are unproven. Retire early with a compile-only check before any
  full device run.
- **Runtime KV import is the genuinely new primitive.** `set_symbol_all` is
  compile-time only, so warm-starting decode requires either `memcpy_h2d` into the
  KV symbols or a streaming KV-import port + drain task (§7.2). This is the
  highest-uncertainty piece; prototype it in isolation first.
- **KV-layout fidelity at the switch.** Prefill's drained KV must reshard exactly
  to decode's `XKCache/XVCache` layout (RoPE pairing, round-robin seq-PE mapping).
  Reuses `prefill_kv_unshard` + `device_reshard.kv_to_device`, but the prefill
  drain wire on the *real* prefill kernel (vs the sim drain) may need work.
- Single batch (`bsz=1`), greedy/top-1 sampling per the device config.
- On-chip (host-free) KV shuttle is out of scope (v-next); v1 uses the
  host-round-trip-within-one-runtime transfer.

## 9. Validation (straight to device, per decision)

No simfab numerical gate. Guard rails instead:
- **Local compile-only** (`launch_sim`/`--compile-only`) after each kernel edit —
  and critically for the **combined co-resident layout** (placement + host-edge
  ports) — to catch build/placement errors cheaply before spending a device slot.
- **Runtime-KV-import prototype** in isolation (smallest config) before the full
  build: confirm host can write decode's `XKCache/XVCache` on a live runtime and
  decode reads it back correctly.
- **Host numpy oracle** of the §4 round algorithm with real weights (reuse the
  `host/oracle_fp16.py` style), run alongside device runs to check the 16 draft
  ids per round and the rollback/correction bookkeeping. With KV handoff the
  oracle includes the prompt context, so the **warm-start continuity** is checked
  (first-round drafts should plausibly continue the prompt).
- **Device runs** via the existing `cs3-runner` ladder; compare device draft ids
  to the oracle; confirm the prefill→decode KV switch (≥2 requests, no reload) and
  multi-round re-arm (≥ several rounds, varying `num_accepted` including 0 and 16)
  with 0 transmission loss.
- Reuse `mock_verify_host.py` to drive rounds locally through the real appliance
  before pointing at the live GPU service.

## 10. Work breakdown (for writing-plans)

1. Restore `integration/` sources (`hf_weights.py`, `device_reshard.py`,
   `prefill_kv_unshard.py`, `run_pipeline.py`, etc.) from the staging copy to
   `models/qwen3_1p7b-decode/integration/`.
2. **Co-resident layout**: restore/finish the origin-offset + region-namespacing
   adapters; place prefill + decode in one `SdkLayout` (vertical stack); pass a
   compile-only feasibility check (placement, host-edge ports). (§3, §7.1)
3. **Runtime KV import into decode** (prototype first): `memcpy_h2d` into KV
   symbols, or streaming KV-import port + drain task. (§7.2, §8)
4. **KV switch path**: prefill KV drain → `prefill_kv_unshard` →
   `device_reshard.kv_to_device` → runtime import; set decode `C`/`iter_num`/RoPE
   base = `prompt_len`. (§7.2)
5. Decode kernel round ops: per-round ingest + re-arm; iter_num rollback + `C`
   state; RoPE position table; correction-token inject; forever loop. (§5)
6. Decode round driver: host-side round payload encode/decode + 16-draft drain;
   numpy oracle. (§4, §9)
7. Prefill real-weight loader `prefill_device_reshard.py` + run wrapper. (§6)
8. `QwenDraftAppliance` (one-load + KV switch) + `appliance_handlers` +
   `config/v0.json` + staging. (§7)
9. Device bring-up via cs3-runner; multi-request prefill→decode switch +
   multi-round verification vs oracle. (§9)

## 11. Out of scope (v1)

Fully **on-chip** (host-free) prefill→decode KV shuttle; batch > 1; variable `k`;
the verifier topology. (Co-residence, single-load, and real prompt-KV continuity
via the host-round-trip switch are now IN scope.)
