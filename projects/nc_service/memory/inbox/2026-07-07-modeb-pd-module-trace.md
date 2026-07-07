---
summary: Module-by-module map of the mode-B PD disaggregation run (run_e2e_pd_modeb_real.sh) — four processes, three couplings, the seam split — plus deliverable locations and two operational gotchas (OAuth refresh, render toolchain). Companion to [[specdec-modeb-drive-path]].
tags: [nc-service, specdec, mode-B, PD-disaggregation, module-map, wse3, io_pipeline, realkv, gotcha]
---

# Mode-B PD module trace (architecture map + deliverables)

Session 2026-07-07: traced every module the two-pod spec-dec PD run touches and shipped
an annotated architecture diagram. Companion to [[specdec-modeb-drive-path]] (that note is
the per-round *timing* call chain; this one is the *who-runs-where* map).

## Architecture facts the trace established

- **Four processes.** (1) verifier — `mock_verify_host.py` stub, stands in for the GPU
  `verify_service`; (2) CS-3 gateway node — `driver_main --pd` + `gateway_frontend.run_session`
  + two `ExchangePump`/`InProcessPatchBridge` pairs (NO wafer here); (3) decode pod (up first);
  (4) prefill pod (up second). Colour-by-process in the figure.
- **Three couplings.**
  - Leg ① gRPC `DraftControl` bidi (verify ⇄ gateway). `translate.py` is the *only* proto⇄u32 bridge.
  - Leg ② `launcher.run(<frame>)` u32 frame (gateway ⇄ each pod) over the **in-process-patch**
    path (`controller`→`handler`→`serve_core`), **instantiated twice** (one bridge per pod).
  - **KV side-channel** — the only prefill→decode coupling, `kv_channel.py` (16-stream TCP,
    disk-free), rides *off* the backbone wire. Rendezvous: decode binds `KvReceiver`, publishes
    `IOP_KV_BOUND` via the `__IOP_INIT__` reply (echoed through backbone `IOP_INIT_EXTRA`);
    driver points prefill's `IOP_KV_PEER` at it.
- **Seam split (why real kernels drop in cleanly).** Two module-level factory hooks in
  `appliance_handlers` — `_PREFILL_APP_FACTORY` / `_DECODE_APP_FACTORY`. `IOP_SPECDEC_MODE=B`
  swaps *only* the decode factory (`DecodeModeBAdapter`, rewind); prefill identical to mode A.
  Framework (`driver_main --pd` + `run_session` + `build_decode_handlers`) is unchanged.
- **Per-pod stack:** patched worker (backbone) → role handler (`build_{prefill,decode}_handlers`,
  sample) → realkv adapter (`PrefillRealAdapter` / `DecodeModeBAdapter`) → resident real appliance
  (`PrefillApplianceReal` / `DecodeApplianceReal`, reuse real `launch.py` build via the
  `_BuildComplete` monkeypatch) → `ApplianceSession` (backbone, legs ③④ host⇄wafer) → real `.csl`.
- **Path scope:** the FIFO `executor_daemon`/`fifo_server` path is the **non-PD default**, NOT
  exercised by `--pd`. Easy to mis-read the backbone and assume the daemon path.

## Deliverables

- Committed to **PR #10** (lausannel/nc_service, branch `lexu/specdec-real-kernels`) under
  `docs/pd-disagg/`: hi-res PNG (1803×5315), single-page **vector** PDF, interactive theme-aware
  HTML, README. Embedded in a PR comment.
- Uploaded PNG+PDF to **contextbase** storage; ready-to-post log entry saved at
  `docs/pd-disagg/CONTEXTBASE_ENTRY.md` (attachment ids: PNG 64e84bb7…, PDF 24ddb683…).
  **Contextbase doc creation BLOCKED** pending MCP re-auth (see gotcha).

## Gotchas (operational)

1. **Never manually refresh an MCP OAuth token via curl.** The contextbase (Outline) token
   server rotates **single-use** refresh tokens. Refreshing by hand (to authenticate a direct
   REST upload) consumes the token the MCP relies on and returns a *new* refresh token; if you
   don't write that new token back into `~/.claude/.credentials.json`, the MCP's next call fails
   with "Invalid grant: refresh token is invalid" and stays broken until interactive `/mcp`
   re-auth. Upload attachments through a path that doesn't disturb the MCP's token, or capture &
   persist BOTH rotated tokens.
2. **Render toolchain on this box:** only `wkhtmltopdf`/`wkhtmltoimage` 0.12.6 (old WebKit — no
   CSS custom properties, no grid, no flex `gap`) + `ghostscript`/`pdftoppm`; **no chromium**.
   Recipe that works: write a print-safe HTML (literal hex colors, table layouts), render a
   **single-page vector PDF sized to content** (`--page-width/--page-height`, `--dpi 150`), then
   `pdftoppm -r 150 pdf` for a genuinely hi-res PNG. `wkhtmltoimage --zoom` does NOT raise raster
   density (that lever is PDF-only); `--zoom N --width 2N` stretches horizontally (distorts).

## Commands / paths

```bash
DEADLINE_S=60 PYTHONUNBUFFERED=1 \
  bash waferengine/samples/specdec/realkv/run_e2e_pd_modeb_real.sh 2
# figure/pdf: docs/pd-disagg/  (also PR #10)
```

## Last updated

2026-07-07
