#!/usr/bin/env python3
"""Generate the qwen3_1p7b kernel-analysis atlas topic doc.

Aggregates, per model: one floorplan + per-kernel algo walkthrough (where it exists)
+ per-kernel state-machine, all as relative links (../../assets/...) into the existing
assets so the topic stays a thin, maintainable index over the generated files.
"""
import os, glob, re

ASSET = "/home/lexu/agent-memory/projects/WaferEngine-staging/assets"
KA = ASSET + "/kernel-algo"
CA = ASSET + "/color-audit"
REL = "../../assets"                    # from memory/topics/ to assets/
OUT = "/home/lexu/agent-memory/projects/WaferEngine-staging/memory/topics/qwen3-kernel-analysis-atlas.md"

def rel_ka(fn):  return f"{REL}/kernel-algo/{fn}"
def rel_ca(fn):  return f"{REL}/color-audit/{fn}"
def exists_ka(fn): return os.path.exists(os.path.join(KA, fn))
def exists_ca(fn): return os.path.exists(os.path.join(CA, fn))

# ---- per-model config ----------------------------------------------------
MODELS = [
    {
        "id": "qwen3_1p7b-prefill", "title": "1 · Prefill (standalone)",
        "config": "test_sim_2x4_kv_varlen.json",
        "blurb": "Reads the whole prompt at once and produces the first token. The compute PE holds a slice "
                 "of transformer layers and runs them as a pipeline; the head/tail PEs do token->embedding and "
                 "the final output; comm_pe is the shared message-passing library.",
        "floorplans": [("prefill_floorplan.svg", "Wafer placement of the prefill regions (compute block + HT head/tail bands).")],
        "phased": False,
    },
    {
        "id": "qwen3_1p7b-decode", "title": "2 · Decode (standalone)",
        "config": "test_sim_2x2block_kv_varlen.json",
        "blurb": "Generates one token at a time, reusing the KV cache. Same head/compute/tail shape as prefill, "
                 "plus KV-ingress kernels that inject the cache from the host each round.",
        "floorplans": [("qwen3_1p7bdecodeworktreetest_sim_2x2block_kv_retain_chain.svg",
                        "Wafer placement + color/queue occupancy for a multi-round KV-retain decode run.")],
        "html_reports": [("qwen3_1p7bdecodeworktreetest_sim_2x2block_kv_retain_chain.html",
                          "Full color-audit report (occupancy matrix + dependency graph).")],
        "phased": False,
    },
    {
        "id": "qwen3_1p7b-e2e", "title": "3 · E2E (fused prefill+decode, one artifact)",
        "config": "test_sim_2x2blk_kv.json",
        "blurb": "Prefill and decode compiled into ONE device program. Two phase regions on the wafer share the "
                 "fabric; the prefill phase samples its own first token, the decode phase runs the rest.",
        "floorplans": [("e2e-floorplan-regions.svg", "The two phase regions (prefill band + decode band) on the wafer."),
                       ("e2e-floorplan-512.svg", "512-token variant of the same region layout."),
                       ("qwen3_1p7b-e2e@fcfc8c1+test_sim_2x2blk_kv.svg", "Color-audit floorplan at commit fcfc8c1.")],
        "phased": True,
    },
    {
        "id": "qwen3_1p7b-e2e-pdSeparate", "title": "4 · E2E pd-Separate (prefill & decode as two artifacts, KV bridged via host)",
        "config": "test_sim_2x2blk_kv.json",
        "blurb": "Prefill and decode are two separate device programs; the KV cache is shipped prefill->host->decode. "
                 "Adds the KV-bridge kernels: kv_mux (prefill egress), kv_adaptor / kv_demux (decode ingress).",
        "floorplans": [],
        "html_reports": [("qwen3_1p7b-e2e-pdSeparate@origin-main.html",
                          "Color-audit report (no standalone spatial SVG; structure mirrors the e2e floorplans above).")],
        "phased": True,
    },
]

# functional ordering of a bare kernel name (phase prefix stripped)
FUNC_RANK = {"prefill":0, "decode":1, "decode_strip":2, "ht_head":3, "ht_tail":4,
             "comm_pe":5, "demux":6, "mux":7,
             "kv_egress_colmux":8, "kv_ingress_adaptor":8, "kv_ingress_injector":8,
             "kv_adaptor":8, "kv_demux":8, "kv_mux":8, "kickoff_relay":9}
def func_rank(bare): return FUNC_RANK.get(bare, 10)

ROLE = {
    "prefill":"main compute PE (transformer layers)", "decode":"main compute PE (one token/step)",
    "decode_strip":"strip/helper PE", "ht_head":"token->embedding lookup",
    "ht_tail":"output head (norm + lm_head + top-K + sampling)", "comm_pe":"shared comm library",
    "demux":"host token-id ingress", "mux":"logits/token egress",
    "kv_egress_colmux":"KV-cache egress to host", "kv_ingress_adaptor":"host->device KV adaptor",
    "kv_ingress_injector":"host->device KV injector", "kv_adaptor":"KV-bridge adaptor (decode side)",
    "kv_demux":"KV-bridge demux (decode side)", "kv_mux":"KV-bridge egress (prefill side)",
    "kickoff_relay":"forward-start sentinel relay",
}

def kernels_for(model_id):
    """Return list of (kernel_key, bare_name, phase) for a model, ordered."""
    sm = glob.glob(os.path.join(KA, f"{model_id}.*.statemachine.md"))
    keys = set()
    for p in sm:
        b = os.path.basename(p)
        k = b[len(model_id)+1:-len(".statemachine.md")]
        if k in ("ALL", "route-only"): continue
        keys.add(k)
    # algo-only kernels (prefill): <model>.<kernel>.md that is NOT statemachine
    for p in glob.glob(os.path.join(KA, f"{model_id}.*.md")):
        b = os.path.basename(p)
        if ".statemachine." in b: continue
        k = b[len(model_id)+1:-len(".md")]
        if k in ("ALL",): continue
        keys.add(k)
    out = []
    for k in keys:
        phase = None; bare = k
        if k.startswith("decode-"): phase, bare = "decode", k[len("decode-"):]
        elif k.startswith("prefill-"): phase, bare = "prefill", k[len("prefill-"):]
        out.append((k, bare, phase))
    # order: phase (prefill=0, decode=1, none=0) then functional rank then name
    def ph(p): return {"prefill":0, "decode":1, None:0}[p]
    out.sort(key=lambda t: (ph(t[2]), func_rank(t[1]), t[1]))
    return out

def fig_block(lines, kind, svg_fn, md_fn, caption):
    """Emit an image (if svg exists) + source links."""
    have_svg = exists_ka(svg_fn); have_md = exists_ka(md_fn)
    if not (have_svg or have_md):
        return
    if have_svg:
        lines.append(f"![{kind}](<{rel_ka(svg_fn)}>)")
        lines.append("")
    srcs = []
    if have_md:  srcs.append(f"[doc]({rel_ka(md_fn)})")
    if have_svg: srcs.append(f"[svg]({rel_ka(svg_fn)})")
    lines.append(f"*{kind} — {caption}* &nbsp; source: " + " · ".join(srcs))
    lines.append("")
    # Large machines are split into an overview (svg_fn) + per-component detail figures named
    # <stem>.<LETTER>-<slug>.svg. List them so the detail set is reachable from the atlas.
    stem = svg_fn[:-len(".svg")]
    details = sorted(glob.glob(os.path.join(KA, f"{stem}.?-*.svg")))
    if details:
        items = []
        for d in details:
            b = os.path.basename(d)
            tag = b[len(stem) + 1:-len(".svg")]          # e.g. "A-boot-ingress"
            letter, _, slug = tag.partition("-")
            items.append(f"[{letter} · {slug.replace('-', ' ')}]({rel_ka(b)})")
        lines.append(f"Detail figures (the above is the overview): " + " · ".join(items))
        lines.append("")

L = []
L.append("---")
L.append("summary: One-stop visual atlas of every qwen3_1p7b WSE-3 kernel — per model, a floorplan "
         "plus per-kernel algorithm walkthrough and task/fn state machine, all as links into the "
         "generated assets. Generated by make_atlas.py.")
L.append("tags: [waferengine-staging, qwen3, kernel-analysis, floorplan, statemachine, algo-walkthrough, atlas]")
L.append("---")
L.append("")
L.append("# qwen3_1p7b Kernel Analysis Atlas")
L.append("")
L.append("Related: [[e2e-kernel-dataflow-and-topology]], [[csl-control-payload-mechanisms]], "
         "[[standalone-vs-integrated-kernel-parity]].")
L.append("")
L.append("> Generated index — do not hand-edit the links; re-run `assets/_gen_kernel-analysis-atlas.py` "
         "after adding assets. "
         "All figures are relative links into `assets/kernel-algo/` and `assets/color-audit/`, so the "
         "topic stays thin and the source files remain the single copy to maintain.")
L.append("")
L.append("This atlas collects everything the analysis skills have produced about the qwen3_1p7b WSE-3 "
         "kernels, in one place. It is split into the **four model variants**; under each you get, for "
         "every kernel, up to three views:")
L.append("")
L.append("- **Floorplan** — *where* on the wafer the kernels sit (physical placement + which fabric "
         "colors/queues are busy). One per model.")
L.append("- **Algorithm walkthrough** — *what* data each PE holds and *how* PEs talk to each other "
         "(data layout + communication pattern). Currently authored for the prefill model.")
L.append("- **State machine** — the *control flow*: which task/function runs, and what event triggers "
         "the next one. Authored for every model.")
L.append("")
L.append("Companion skills: `cerebras-kernel-algo-walkthrough` (algorithm), "
         "`cerebras-kernel-statemachine` (control flow), `csl-color-audit` (floorplan/occupancy).")
L.append("")
L.append("## Contents")
for m in MODELS:
    L.append(f"- [{m['title']}](#{re.sub(r'[^a-z0-9]+','-',m['title'].lower()).strip('-')})")
L.append("")

for m in MODELS:
    mid = m["id"]
    L.append(f"## {m['title']}")
    L.append("")
    L.append(f"`models/{mid}` · ref config `{m['config']}`. {m['blurb']}")
    L.append("")
    # floorplan
    L.append("### Floorplan")
    L.append("")
    emitted = False
    for fn, cap in m.get("floorplans", []):
        if exists_ca(fn):
            L.append(f"![floorplan](<{rel_ca(fn)}>)")
            L.append("")
            L.append(f"*{cap}* &nbsp; source: [svg]({rel_ca(fn)})")
            L.append("")
            emitted = True
    for fn, cap in m.get("html_reports", []):
        if exists_ca(fn):
            L.append(f"- Color-audit report: [{fn}]({rel_ca(fn)}) — {cap}")
            emitted = True
    if emitted:
        L.append("")
    else:
        L.append("_(no floorplan asset yet)_")
        L.append("")
    # kernels
    L.append("### Kernels")
    L.append("")
    ks = kernels_for(mid)
    last_phase = "___"
    for key, bare, phase in ks:
        if m["phased"] and phase != last_phase:
            L.append(f"#### {phase.capitalize()} phase")
            L.append("")
            last_phase = phase
        role = ROLE.get(bare, "")
        L.append(f"##### `{bare}`" + (f" — {role}" if role else ""))
        L.append("")
        # algo (stem = <model>.<key>) ; statemachine (stem = <model>.<key>.statemachine)
        fig_block(L, "Algorithm", f"{mid}.{key}.svg", f"{mid}.{key}.md",
                  "data layout + who-talks-to-whom")
        fig_block(L, "State machine", f"{mid}.{key}.statemachine.svg", f"{mid}.{key}.statemachine.md",
                  "task/fn control flow")
        # if neither
        if not (exists_ka(f"{mid}.{key}.svg") or exists_ka(f"{mid}.{key}.statemachine.svg")):
            L.append("_(route-only or no diagram)_")
            L.append("")
    # route-only note link if present
    ro = f"{mid}.route-only.statemachine.md"
    if exists_ka(ro):
        L.append(f"> Route-only files (no task state machine) for this model: [{ro}]({rel_ka(ro)}).")
        L.append("")
    # aggregate inbox doc pointer
    L.append(f"> Full per-kernel state-machine index for this model: "
             f"`memory/inbox/{mid}.ALL.statemachine.md`.")
    L.append("")

open(OUT, "w").write("\n".join(L))
print("wrote", OUT, "bytes:", len(open(OUT).read()))
