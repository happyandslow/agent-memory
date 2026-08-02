# M2 S1+S2: the kernel tree and the real decode cfg now reach the pod — and the 23 GB ELF blocker was already solved upstream

Date: 2026-07-28 · Repo: `nc_service`, branch `lexu/pdsep-kernel-integration`

**Project:** nc_service
**Author:** claude
**Status:** captured

## The situation this applies to

You are on M2 (swap `fake_device` for the real `launch_decode.serve()` on CS-3) and
are about to spend a device slot. Two things landed device-free, and one *belief*
about the device path turned out to be stale in a way that changes the plan.

Suite: **535 passed / 2 skipped** (M1's 495 + 28 new). No commits yet.

## S1 — staging: the path is the configuration

`inproc_bridge_check.assemble_staging()` is the SHARED staging assembler (driver_main's
three in-proc paths all call it), so the SD kernel tree hooks in there, opt-in on
`IOP_SD_KERNEL=1`, default OFF so existing PD/bridge runs stage byte-identically.

**The load-bearing choice is the destination**, `<stage>/kernels/qwen3_1p7b-sd-pdSeparate`.
`kernel_env.kernel_root()` resolves its default from its own `__file__`
(`parents[4] / "kernels" / ...`), and in the staged tree `kernel_env.py` lands at
`<stage>/waferengine/samples/specdec/sd_kernel/`, so `parents[4]` IS `<stage>`.
Mirroring the repo layout therefore means **the pod needs no `WE_SD_PDSEP_DIR` and no
extra controller-cmd env var**. Pinned by a subprocess test that strips the env var.

Second S1 change: `_build_controller_cmd()` grew a generic `IOP_*` passthrough (same
rule driver_main already uses) plus a selectable `build_handlers` dotted path. The
chain is `driver env -> controller_cmd -> controller env -> patched worker env`; a var
the driver holds but does not export into the cmd string **does not fail, it silently
defaults**. That is a whole class of device-slot loss.

## S2 — every serve quantity now has a publisher

New `sd_kernel/serve_setup.py` routes, rather than recomputes:

    request.json      -> launch._load_request
    prompts           -> host.qwen_tokenizer
    launch_prefill.py -> kv_egress_<i>.npz      (launch._subproc)
    kv_egress         -> host.kv_bridge          -> inj_<i>.npz
    compiled artifact -> serve_meta.json         -> sc (top_k, ...)

`read_serve_meta` is now on a real path for the first time (Task 5 wrote it; nothing
had called it). `read_serve_scalars` deliberately has **no fallback** to
`fake_serve_scalars` — a mis-set cache dir must stop the run, not produce a plausible
one against synthesised geometry. Pinned by a test that makes `fake_serve_scalars`
raise, and by a fixture where the artifact says `top_k=12` while model_config says 20.

**What we could NOT reuse, and the guard for it.** `launch.py::run()` is one function:
tokenize -> prefill -> KV bridge -> **decode subprocess** -> Q&A. We need decode
IN-PROCESS (the only way `bridge_target` reaches serve_loop's target seam), and the
prefill/bridge section is inline, not factored. So the *sequencing* is re-expressed
while every actual value still comes from the kernel's own helpers. The drift guard is
an **AST tripwire**: the test reads the kwargs of launch.py's own
`_write_cfg(dec_cfg, cfg, ...)` call and asserts our decode cfg is a superset. If
upstream adds a decode cfg key, the test fails instead of the wafer silently running
on a default. (A second test asserts the AST walk actually found the payload keys, so
the first cannot pass vacuously.)

`rearm_repeat_round0` is **refused**, not reproduced — it rewires decode's seed tokens
and KV, and a partial copy would diverge silently.

`handlers.build_handlers(args, cfg)` is the pod seam. It reads the artifact FIRST (a
file read) so a wrong cache dir costs 1 second, not the 40-minute prefill phase. It
ignores the backbone's own `IOP_CONFIG` cfg entirely: the kernel's request config is
the single source of truth, and mixing two config files is how they drift apart.

## The finding that changes S3/S4: `launch_device.py` already solved the ELF problem

`inbox/2026-07-21-cs3-elf-extract-reload-scale.md` concluded the loadable image is
~23 GB/phase and therefore not cheaply movable. **Upstream solved it, and the solution
is in the tree we vendored.** `launch_device.py` + `host/staged_dispatch.py`:

- the store ships `sim.elf.zst`, and the run command carries a shell prefix that
  `zstd -d` it on the worker before `cs_python launch.py`;
- `StagedDispatch.stage_chunked_weights` byte-splits any file over
  `CHUNK_BYTE_BUDGET = 1.8 GB` into parts, `launcher.stage()`s each part
  individually, and `cat`-reassembles on the worker — because `SdkLauncher.stage()`
  uploads ONE artifact per gRPC call and large files exceed the cap;
- part names key off the full dest path, not the basename, precisely because
  `prefill/sim.elf.zst` and `decode/sim.elf.zst` would otherwise collide.

So the compile step should be the kernel's own **unmodified** `launch_device.py
--mode compile`, which lands a persistent login-node store at
`serving_cache/<model_config>/{tokenizer,prefill,decode}`.

**But there is a structural conflict for the RUN.** `launch_device.py` owns the
`SdkLauncher` session (StagedDispatch opens `with SdkLauncher(...)`, runs ONE command,
exits). `InProcessPatchBridge` also owns an `SdkLauncher` session, and it only
tree-uploads `src_dir` — it has **no `stage()` hook and no worker-side reassembly
step**. One device job = one launcher session, so these are mutually exclusive.

Consequence: before S4 can run, `InProcessPatchBridge` needs an additive seam for
"extra artifacts to stage in parts + a prep command to run before `controller_cmd`",
with the SD side supplying the kernel-specific parts and the `zstd -d` line. That is
pure-local testable against the existing FakeLauncher. It was not in the S1–S6 sketch.

**Do not size that work by guessing.** Whether chunking is needed at all depends on the
compressed store size, which nobody has measured. S3 should report
`du -sh serving_cache/serve_2x4_8k20k/{prefill,decode,tokenizer}` and the size of each
`sim.elf.zst`; that number decides chunk count and whether the tree upload alone
suffices.

## Old numbers, for scale only (NOT the M2 baseline)

From the vendored `mtbench8/device_verdict.json` — long-form autoregressive decode,
measured inside the kernel's own loop, no gateway:
decode `load_s` 150.7 s, prefill `load_s` 141.5 s; device 655 µs/token vs host recv
739 µs/token (ratio 1.13); `per_round_kv_load_ms` 69.5 + `per_round_kv_repack_ms` 29.5
= ~100 ms host-side KV work per request; `per_round_recv_first_ms` 53.8.
The ~150 s load sits in `__IOP_INIT__`, not on the exchange path.

## Implications / next actions

- [ ] S3 = `launch_device.py --mode compile` (kernel's own path, unmodified), then
      **measure the store size** before deciding the staging design.
- [ ] Then the `InProcessPatchBridge` staging seam (additive), then S4.
- [ ] Flaky, unrelated, unfixed: `test_stub_daemon_emits_deeper_timing_fields` failed
      once under random ordering; passed alone and on four subsequent full runs.

## Pointers

- `waferengine/samples/specdec/sd_kernel/{staging,serve_setup}.py`, `handlers.py`
  (`build_handlers`), `kernel_env.py` (`import_launch` / `import_kv_bridge`).
- `kernels/qwen3_1p7b-sd-pdSeparate/{launch_device.py,host/staged_dispatch.py}`.
- Related: [[2026-07-28-m1-complete-bridge-architecture-index]],
  [[2026-07-28-take-scalars-from-the-kernel-not-your-own-derivation]],
  [[2026-07-21-cs3-elf-extract-reload-scale]] (the conclusion this note corrects).
