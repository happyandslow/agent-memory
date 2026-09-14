#!/usr/bin/env python3
"""Two panels: optimisation ladder (CS-3, prefill 512 / decode 64) and the context penalty curve."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BASE = 672193
ladder = [("R\nfixed protocol,\nstaged hops", 3760395), ("R2\nstreamed\nhops", 2407451), ("T2\nGEMV\nscore", 1968766),
          ("M2\ntwo-pass\nmerge", 1346696), ("T3\nDSD\nt2", 1241770), ("SW\nswitch\nt1", 1177712)]
ctx  = [512, 2048, 4096, 7936]; base = [672193, 741896, 769208, 812929]; farm = [1177712, 1176958, 1180798, 1182501]
fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150)
xs = range(len(ladder)); ys = [v/1e3 for _, v in ladder]
a.plot(list(xs), ys, "s-", color="C1", label="S1 + farm (112 cols, 6 zero pos/PE)")
a.axhline(BASE/1e3, color="C0", ls="--", label="shipped layout, no farm (672K)")
for x, (_, v) in zip(xs, ladder): a.annotate(f"{v/BASE:.2f}×", (x, v/1e3), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
a.set_xticks(list(xs)); a.set_xticklabels([n for n, _ in ladder], fontsize=7)
a.set_ylabel("cycles per token (K)"); a.set_ylim(0, 4100); a.grid(alpha=0.3); a.legend(fontsize=8)
a.set_title("Optimisation ladder — CS-3, prefill 512 / decode 64", fontsize=10)
b.plot(ctx, [v/1e3 for v in base], "o-", color="C0", label="shipped layout (no farm)")
b.plot(ctx, [v/1e3 for v in farm], "s-", color="C1", label="S1 + farm, switch t1")
for x, u, v in zip(ctx, base, farm): b.annotate(f"{v/u:.2f}×", (x, v/1e3), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
b.set_xscale("log", base=2); b.set_xticks(ctx); b.set_xticklabels([str(c) for c in ctx])
b.set_xlabel("prefill context (tokens); decode 64"); b.set_ylim(0, 1350); b.grid(alpha=0.3); b.legend(fontsize=8, loc="center right")
b.set_title("Penalty curve vs context — CS-3", fontsize=10)
fig.tight_layout(); fig.savefig("ladder_and_curve.png"); print("wrote ladder_and_curve.png")
