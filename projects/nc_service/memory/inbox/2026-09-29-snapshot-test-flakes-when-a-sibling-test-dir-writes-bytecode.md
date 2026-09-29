# A "no bytecode residue" snapshot test goes red on the full run and green alone — a sibling test dir is writing `__pycache__` into the pinned tree — 2026-09-29

**Project:** nc_service
**Author:** claude
**Status:** captured

Retroactive capture from the 2026-07-28/29 M2 overnight session (transcript digest
reviewed 2026-09-29). The vendor-snapshot test still pins the fallback `kernels/` tree
as of [[2026-09-10-waferengine-submodule-default]], so the failure mode is still live.

## The situation this applies to

The full pytest run shows `test_snapshot_has_no_bytecode_residue` (the guard that the
vendored/fallback `kernels/qwen3_1p7b-sd-pdSeparate` tree is byte-pristine) failing,
but the same test passes when rerun alone, and passes on some full runs and not
others. Nothing in the snapshot itself changed. It looks like a random flake and is
easy to dismiss at 2 a.m.

## What happened / finding

- Root cause: `sd_kernel/tests/conftest.py` sets `sys.dont_write_bytecode = True`,
  but the **sibling directory `specdec/tests/` had no such conftest**. A new test
  there (the device driver's tests, added that night) imported the kernel modules,
  and CPython wrote `__pycache__` into the tree the snapshot test asserts is clean.
- The red/green depends purely on **collection order**: if the residue-check runs
  before the polluting test, it passes; after, it fails. Under random ordering that
  is a coin flip, which is exactly what "flaky" looks like.
- Fix that held: add the same `sys.dont_write_bytecode = True` line (with a comment
  stating why) to `specdec/tests/conftest.py`. Suite went to 620 passed and stayed
  green through the rest of the night; no residue on disk afterwards.
- General shape, worth remembering beyond this repo: **a pristine-tree guard is only
  as strong as the bytecode setting of every test directory that can import that
  tree.** Any new test directory that imports the kernel re-introduces the flake
  unless it carries the setting or the guard is hoisted to a root conftest.

## Implications / next actions

- [ ] When adding a test directory that imports from `kernels/` or the
      `third_party/WaferEngine` submodule, give it (or the root) a conftest with
      `sys.dont_write_bytecode = True` before chasing any snapshot-test red.
- [ ] If the residue test flakes again, check `find kernels/ -name __pycache__`
      before assuming the snapshot drifted.

## Pointers

- `waferengine/samples/specdec/sd_kernel/tests/conftest.py`,
  `waferengine/samples/specdec/tests/conftest.py`, the vendor snapshot test in
  `sd_kernel/tests/test_vendor_snapshot.py`.
- Session narrative: `M2_NIGHT_LOG_2026-07-28.md` (work repo root, W2 section).
- Related: [[2026-07-29-m2-device-bringup-and-the-ingress-blocker]],
  [[2026-07-28-m2-s1s2-staging-and-real-cfg]] (records the *other* unrelated
  flake of that session, `test_stub_daemon_emits_deeper_timing_fields`).
