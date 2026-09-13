# EIDF GPU service (sicheng route), state on 2026-09-13: shared SGLang pod is gone; verified Job-manifest facts for a 1×H100 SGLang run — 2026-09-13

**Project:** wse3-performance-model (applies to nc_service too)
**Author:** claude (session 4b-layout-kv-stream)
**Status:** captured

## Situation

You want a GPU reference number (e.g. SGLang serving Qwen3-4B) from the EPCC
EIDF cluster reached via `ssh -J sicheng@eidf-gateway.epcc.ed.ac.uk
sicheng@10.24.7.82`, and the `eidf-gpu-run` skill tells you to `kubectl exec`
into the shared pod `kimi-k25-sglang-h100-bdwk4`.

## Findings (observed read-only, 2026-09-13)

- **The shared pod no longer exists.** `kubectl -n eidf230ns get pods` shows
  only other users' jobs (`manu-*`, `jd-llm-qwen35-4b-verl-*`,
  `eidf-helper-*`); the job `kimi-k25-remote-sglang-pxh28` is `Suspended`
  (41 d). The `/tmp/sglang-unit` fork recorded in the skill is gone with it.
  Any GPU run now needs **our own Job**.
- **No B200 on EIDF.** Live pods report `NVIDIA H100 80GB HBM3` (81,559 MiB);
  the EIDF hardware list is H200/H100/A100. Do not promise a B200 number.
- Quota at the time: `requests.nvidia.com/gpu 7 / 12` → 5 GPUs free; a
  1-GPU Job fits. `kubectl auth can-i create jobs -n eidf230ns` → yes.
- **Kueue is mandatory and the labels are now known** (from a live Job's pod):
  Job label `kueue.x-k8s.io/queue-name: eidf230ns-user-queue` (local queue,
  cluster queue `eidf230ns-project-gpu-cq`, 8 admitted workloads); a
  `eidf230ns-profiling-queue` also exists.
- Verified nodeSelector for H100: `nvidia.com/gpu.product:
  NVIDIA-H100-80GB-HBM3`, `nvidia.com/gpu.present: "true"`,
  `general_node: "true"`, `profiling_node: "false"` (they also pin
  `kubernetes.io/hostname`, which we should not).
- Working pod shape: image `nvidia/cuda:12.8.1-devel-ubuntu24.04` for that
  user; resources `cpu 4 / memory 64Gi / nvidia.com/gpu 1` requests = limits;
  volumes `dshm` emptyDir on `/dev/shm`, an `inputs` PVC on `/inputs-pvc`.
  This resolves items 1, 2 and 4 of the skill's `new-gpu-pod.md` "unresolved"
  list; item 3 (`/ckpt` CephFS mount spec) is still unknown — Qwen3-4B can
  simply be pulled from HF inside the pod (GLM-4.6 pulled at ≈ 675 MB/s in
  July).
- Dev VM: 746 G free under `/home/eidf230/eidf230/sicheng`; `lexu/` holds
  `nc_service` and `logs`. Gateway is key-only, no OTP; a ControlMaster at
  `~/.ssh/cm/gpu-%C` (persist 4 h) was parked this session.

## Implications / next actions

- [ ] To get a Qwen3-4B SGLang baseline: apply a 1×H100 Job (image
  `lmsysorg/sglang:latest`, `sleep infinity`, labels/nodeSelector above,
  `/dev/shm` emptyDir), exec in, `python3 -m sglang.launch_server
  --model-path Qwen/Qwen3-4B --context-length 32768`, then
  `sglang.bench_serving` / `bench_one_batch` at bs = 1 over context
  {4K, 8K, 16K, 32K} for TPOT, plus a bs sweep for tok/s. **Ask before
  allocating** — GPUs are shared with Yeqi's group.
- [ ] Update `~/.claude/skills/eidf-gpu-run/references/new-gpu-pod.md` after
  the first successful apply (the skill asks for exactly that).

## Pointers

- skill: `~/.claude/skills/eidf-gpu-run/SKILL.md`, `references/new-gpu-pod.md`,
  `references/sglang-launch-recipes.md`
- prior state: `projects/nc_service/memory/topics/specdec-gpu-verifier-eidf.md`
