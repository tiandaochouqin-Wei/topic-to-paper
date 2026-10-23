# -*- coding: utf-8 -*-
"""P5 — motivation figures: show WHY the paper exists, in whatever form the evidence takes. Run by Claude.

A motivation figure carries one claim, normally the prereg §0 phenomenon ("existing methods fail under C", "the trade-off
X <-> Y is forced", "ours is a different paradigm"). Choose the subcommand by the kind of evidence, not by habit
(references/motivation-figures.md has the decision table and the checks):

  a measured phenomenon
    condition  metric vs a controlled condition (dose, illumination, noise, window, occlusion, time). Marks where the leading
               series changes (and says whether that change is outside seed noise), gap arrows and shaded regimes.
      python make_motivation.py condition --csv results/pilot.csv --x illum --y AP --series method [--ours ours]
                                [--among rgb_only,ir_only] [--gap "fusion,rgb_only@0.25"] [--regions "Night:0:0.3,Day:0.7:1"]
                                [--lower] [--logx] [--labels k=v,...]
    paired     the same items under two settings (better single modality vs naive fusion, full vs low dose, in- vs
               out-of-domain): slope chart for <= 12 items, sorted delta bars otherwise; counts how many items get worse.
      python make_motivation.py paired --csv results/table1.csv --item detector,dataset --from RGB,IR --to Naive
                                [--from-label "better single"] [--to-label "naive fusion"] [--lower] [--style auto|slope|bars]
      (long table instead of columns: --cond setting --value AP, then --from/--to name values of the --cond column)
    tradeoff   accuracy vs cost scatter with the Pareto front; says whether ours is on it.
      python make_motivation.py tradeoff --csv results/efficiency.csv --x GFLOPs --y AP --label method [--size params]
                                [--ours ours] [--logx] [--lower] [--higher-x] [--no-front] [--no-arrow] [--title "..."]
      Fig-5-style frontier over many benchmarks: --color dataset (one fill colour per value, front per value), --marker-ours star,
      --ours "A,B" (comma list), --broken-x "65,110" (x axis broken over that interval), --bubble-legend "8,100,786" (needs --size),
      labels placed greedily around each point (8 offsets, no label on label, dropped + printed when nothing fits; source CSV column
      placed_label); with --color each method is named once, ours at every point (--label-each: all points)
  breadth of a result (a results teaser, rarely a motivation: about 1 % of CS Fig. 1s in the local sample)
    radar      one polygon per series over >= 3 benchmarks, every axis on its own printed range
      python make_motivation.py radar --csv results/bench.csv --axis dataset --series method --value AP --ours ours [--groups ...]
  a different paradigm
    schematic  "existing vs ours" block diagram from a YAML spec in millimetres (template templates/motivation_scheme.yaml)
  new data / modality
    strip      dataset thumbnails, paired modalities side by side
      python make_motivation.py strip --item "M3FD RGB/IR|a.png|b.png" [--item ...]
  visible failure cases: make_comparison.py grid (input / baseline / ours / GT columns, --inset zoom) — not here.

Every subcommand writes <out>.png, <out>.pdf, <out>_gray.png and <out>.source.csv, registers the panel in figures.csv through
make_figure.finish (layout audit, inspected=no) and prints the numbers the caption may quote. Hybrids (concept + data) are
separate panels composed in LaTeX: latex_check.py figure --panels a.pdf,b.pdf --width 0.45,0.53 --env figure*
"""
import argparse, collections, csv, io, math, os, sys, zlib
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import make_figure as mf                       # sets the house rcParams (7.5 pt serif, TrueType in PDF) and the Agg backend
import matplotlib.pyplot as plt
from matplotlib import patches
plt.rcParams["savefig.pad_inches"] = 0.02     # make_figure.finish saves with bbox_inches='tight'; the default 0.1 in pad made every panel 5 mm wider than its print width

COLORS = {"rgb": "#e8833a", "x": "#2f6eb5", "shared": "#9aa0a6", "ours": mf.ACCENT, "good": "#2e9b57", "bad": "#c0392b",
          "neutral": "#4a4a4a", "light": "#f2f2f2"}
PANEL_EDGE = {"bad": "#8a8a8a", "good": "#2e9b57", "neutral": "#4a4a4a"}
OTHERS = ["#5b8bb5", "#8c7aa9", "#6c8e7a", "#b8873a", "#7a7a7a", "#2b4c6f"]   # distinguishable from each other and from the red accent
DASHES = ["--", "-.", ":", (0, (5, 1.5)), (0, (1, 1.2)), (0, (4, 1, 1, 1))]
MARKERS = ["o", "s", "^", "v", "P", "X"]
BAD, NEUTRAL = "#c0392b", "#9aa0a6"
REGION = ["#f3f3f3", "#e9eef5"]


def fail(msg):
    print(f"[FAIL] {msg}"); sys.exit(1)


def col(c, default="neutral"):
    c = c or default
    return COLORS.get(c, c)


def _dark(hexcol):
    h = hexcol.lstrip("#")
    if len(h) != 6: return True
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b < 150


def _parse_kv(s, sep=","):
    return dict(kv.split("=", 1) for kv in s.split(sep) if "=" in kv) if s else {}


def _rows(root, rel, need):
    path = os.path.join(root, rel)
    if not os.path.exists(path): fail(f"{rel} 不存在")
    rows = list(csv.DictReader(io.open(path, encoding="utf-8-sig")))
    if not rows: fail(f"{rel} 是空表")
    miss = [c for c in need if c and c not in rows[0]]
    if miss: fail(f"{rel} 没有列 {miss}：{list(rows[0])}")
    return rows


def fit_width(fig, axes, target_in, keep_aspect=False, what="figure", tries=8):
    """text hanging outside the axes (polar labels, slope-chart item names) makes savefig(bbox_inches='tight') wider than
    the print width, and G5 then sees every label shrunk (4.5 pt at 62 mm in the first radar). Shrink the axes until the
    tight box fits the width."""
    target_in = target_in - 2 * plt.rcParams["savefig.pad_inches"]     # bbox_inches='tight' adds this pad on both sides
    bb = 0.0
    for _ in range(tries):
        bb = fig.get_tightbbox(fig.canvas.get_renderer()).width
        if bb <= target_in * 1.005: return
        f = max(0.5, target_in / bb) ** 1.3
        for ax in axes:
            x0, y0, w, h = ax.get_position().bounds
            ax.set_position([x0 + w * (1 - f) / 2, y0 + (h * (1 - f) / 2 if keep_aspect else 0), w * f, h * f if keep_aspect else h])
    print(f"[WARN] {what}: tight width {bb * 25.4:.0f} mm still exceeds {target_in * 25.4:.0f} mm; shorten the labels")


def finish(fig, a, src, hdr, root, caption):
    mf.finish(fig, a, src, hdr, root, caption); plt.close(fig)


def _new_axes(a):
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, a.height_in))
    fig.subplots_adjust(left=0.15, right=0.97, bottom=0.2, top=0.93)
    return fig, ax


def _g(v):
    return f"{v:+.3g}"


# ------------------------------------------------------------------ condition
def _stats(pts):
    return {s: {x: (float(np.mean(v)), float(np.std(v, ddof=1)) if len(v) > 1 else 0.0, len(v)) for x, v in sorted(d.items())}
            for s, d in pts.items()}


def condition(a):
    root = os.path.abspath(a.project)
    rows = _rows(root, a.csv, [a.x, a.y, a.series])
    pts = collections.OrderedDict()
    for r in rows:
        try: xv, yv = float(r[a.x]), float(r[a.y])
        except ValueError: continue
        pts.setdefault(r[a.series] if a.series else a.y, collections.defaultdict(list))[xv].append(yv)
    if not pts: fail(f"{a.csv} 里 {a.x} / {a.y} 没有数值")
    st = _stats(pts); labels = _parse_kv(a.labels); hib = not a.lower
    xs_all = sorted({x for d in st.values() for x in d})
    if len(xs_all) < 2: fail(f"条件轴 {a.x} 至少要 2 个取值，现在 {xs_all}")
    ours = a.ours or ""
    if ours and ours not in st: fail(f"--ours {ours} 不在系列里：{list(st)}")
    among = [s.strip() for s in a.among.split(",") if s.strip()] if a.among else [s for s in st if s != ours]
    miss = [s for s in among if s not in st]
    if miss: fail(f"--among 里没有这些系列 {miss}（有：{list(st)}）")
    fig, ax = _new_axes(a)
    for i, part in enumerate([p for p in a.regions.split(",") if p.strip()] if a.regions else []):
        try:
            name, lo, hi = part.rsplit(":", 2); lo, hi = float(lo), float(hi)
        except ValueError: fail(f"--regions 写成 '名字:下限:上限,…'：{part}")
        ax.axvspan(lo, hi, color=REGION[i % 2], zorder=0, lw=0)
        ax.text((lo + hi) / 2, 1.01, name.strip(), transform=ax.get_xaxis_transform(), ha="center", va="bottom", fontsize=6.3, color="#555555", fontstyle="italic", clip_on=False)
    order = [s for s in st if s != ours] + ([ours] if ours else [])
    src = []
    for i, s in enumerate(order):
        xs = sorted(st[s]); m = np.array([st[s][x][0] for x in xs]); sd = np.array([st[s][x][1] for x in xs]); n = max(st[s][x][2] for x in xs)
        is_o = s == ours; c = mf.ACCENT if is_o else OTHERS[i % len(OTHERS)]
        ax.plot(xs, m, color=c, lw=1.5 if is_o else 1.0, marker="D" if is_o else MARKERS[i % len(MARKERS)], ms=3.0 if is_o else 2.6,
                label=labels.get(s, s) + (f" (n={n})" if n > 1 else ""), zorder=5 if is_o else 3)
        if n > 1: ax.fill_between(xs, m - sd, m + sd, color=c, alpha=0.15, lw=0, zorder=2)
    # where does the leading series (among --among) change along the condition axis?
    def leader(x):
        cand = [s for s in among if x in st[s]]
        return (max if hib else min)(cand, key=lambda s: st[s][x][0]) if cand else None
    leads = [(x, leader(x)) for x in xs_all]
    lead_at = dict(leads)
    for s in order:
        for x in sorted(st[s]): src.append([s, x, *st[s][x], lead_at.get(x) == s])
    def resolved(s1, s2, x):
        (m1, s1d, n1), (m2, s2d, n2) = st[s1][x], st[s2][x]
        if n1 < 2 or n2 < 2: return None
        return abs(m1 - m2) > 2 * math.sqrt(s1d ** 2 / n1 + s2d ** 2 / n2)
    crossings = []
    for (x0, l0), (x1, l1) in zip(leads, leads[1:]):
        if not l0 or not l1 or l0 == l1 or x0 not in st[l1] or x1 not in st[l0]: continue
        d0 = st[l0][x0][0] - st[l1][x0][0]; d1 = st[l0][x1][0] - st[l1][x1][0]
        t = d0 / (d0 - d1) if d0 != d1 else 0.5
        xc = 10 ** (math.log10(x0) + t * (math.log10(x1) - math.log10(x0))) if a.logx and x0 > 0 and x1 > 0 else x0 + t * (x1 - x0)
        r0, r1 = resolved(l0, l1, x0), resolved(l0, l1, x1)
        verdict = "single run, unverified" if r0 is None or r1 is None else ("outside seed noise" if r0 and r1 else "inside seed noise")
        crossings.append((l0, l1, xc, verdict))
        if verdict == "inside seed noise": continue          # not drawn: a line on the figure would claim a reversal the seeds do not support
        ax.axvline(xc, color="#777777", lw=0.6, ls=":", zorder=1)
        ax.text(xc, 0.04, f"{labels.get(l0, l0)} → {labels.get(l1, l1)}" + (" (1 run)" if verdict.startswith("single") else "") + " ", transform=ax.get_xaxis_transform(),
                rotation=90, ha="right", va="bottom", fontsize=5.6, color="#555555", bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none", alpha=0.7))
    gaps = []
    for g in a.gap or []:
        spec, _, at = g.partition("@")
        names = [p.strip() for p in spec.split(",")]
        if len(names) != 2: fail(f"--gap 写成 'A,B' 或 'A,B@x'：{g}")
        s1, s2 = names
        for s in (s1, s2):
            if s not in st: fail(f"--gap: 没有系列 {s}（有：{list(st)}）")
        common = [x for x in xs_all if x in st[s1] and x in st[s2]]
        if not common: fail(f"--gap: {s1} 与 {s2} 没有共同的 {a.x}")
        if at.strip():
            xg = float(at)
            if xg not in common: fail(f"--gap: {a.x}={xg:g} 不在两者共有的取值 {common}")
        else:
            xg = max(common, key=lambda x: abs(st[s1][x][0] - st[s2][x][0]))
        y1, y2 = st[s1][xg][0], st[s2][xg][0]; d = y1 - y2
        ax.annotate("", xy=(xg, y1), xytext=(xg, y2), arrowprops=dict(arrowstyle="<->", lw=0.8, color="#222222", shrinkA=0, shrinkB=0), zorder=6)
        ax.text(xg, (y1 + y2) / 2, f" Δ {_g(d)}", ha="left", va="center", fontsize=6.4, fontweight="bold", color="#222222", zorder=6)
        r = resolved(s1, s2, xg)
        gaps.append(f"{labels.get(s1, s1)} − {labels.get(s2, s2)} = {_g(d)} at {a.x} = {xg:g}" + ("" if r is None else ("" if r else " (inside seed noise)")))
    if a.logx: ax.set_xscale("log")
    ax.set_xlabel(a.xlabel or labels.get(a.x, a.x)); ax.set_ylabel(a.ylabel or labels.get(a.y, a.y))
    ax.grid(axis="y", lw=0.4, color="#e6e6e6", zorder=0)
    if a.legend == "below": ax.legend(fontsize=6.0, loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=min(len(st), 3), handlelength=1.6, frameon=False)
    else: ax.legend(fontsize=6.0, loc=a.legend, handlelength=1.6, framealpha=0.85)
    fit_width(fig, [ax], a.width_mm / 25.4, what="condition")
    for l0, l1, xc, v in crossings:
        print(f"leader change: {l0} -> {l1} at {a.x} ≈ {xc:.3g} ({v})")
        if v == "inside seed noise": print(f"[WARN] condition: the {l0} -> {l1} change is inside seed noise (not drawn); the caption must not call it a reversal")
        if v.startswith("single run"): print(f"[INFO] condition: one run per point; the {l0} -> {l1} change is unverified until seeds are added")
    if not crossings: print(f"no leader change among {among} along {a.x}")
    for gtxt in gaps: print("gap: " + gtxt)
    cap = f"{labels.get(a.y, a.y)} vs. {labels.get(a.x, a.x)}"
    if crossings: cap += "; leader changes: " + "; ".join(f"{l0}→{l1} at ≈{xc:.3g} ({v})" for l0, l1, xc, v in crossings)
    if gaps: cap += "; " + "; ".join(gaps)
    if any(max(st[s][x][2] for x in st[s]) > 1 for s in st): cap += "; shaded = ± s.d. over seeds"
    finish(fig, a, src, ["series", a.x, f"{a.y}_mean", f"{a.y}_sd", "n", "leader"], root, cap + ".")


# ------------------------------------------------------------------ paired
def _spread(vals, gap):
    """nudge label positions apart by at least gap (labels of a slope chart ending at nearly the same value)"""
    idx = np.argsort(vals); y = np.array(vals, float)[idx]
    for _ in range(100):
        moved = False
        for i in range(1, len(y)):
            if y[i] - y[i - 1] < gap - 1e-12:
                mid = (y[i] + y[i - 1]) / 2; y[i - 1], y[i] = mid - gap / 2, mid + gap / 2; moved = True
        if not moved: break
    out = np.empty_like(y); out[idx] = y
    return out


def paired(a):
    root = os.path.abspath(a.project)
    items = [c.strip() for c in a.item.split(",") if c.strip()]
    fcols = [c.strip() for c in a.from_.split(",") if c.strip()]; tcols = [c.strip() for c in a.to.split(",") if c.strip()]
    hib = not a.lower; best = max if hib else min
    pairs = []
    if a.cond:
        rows = _rows(root, a.csv, items + [a.cond, a.value])
        acc = collections.OrderedDict()
        for r in rows:
            try: v = float(r[a.value])
            except ValueError: continue
            acc.setdefault(tuple(r[c] for c in items), collections.defaultdict(list))[r[a.cond]].append(v)
        for k, d in acc.items():
            fv = [float(np.mean(d[c])) for c in fcols if c in d]; tv = [float(np.mean(d[c])) for c in tcols if c in d]
            if len(fv) == len(fcols) and len(tv) == len(tcols): pairs.append((" / ".join(k), best(fv), best(tv)))
        value = a.value
    else:
        rows = _rows(root, a.csv, items + fcols + tcols)
        acc = collections.OrderedDict()       # rows sharing an item key (seeds, the detectors of one dataset …) are averaged
        for r in rows:
            try: fv = [float(r[c]) for c in fcols]; tv = [float(r[c]) for c in tcols]
            except ValueError: continue
            acc.setdefault(" / ".join(r[c] for c in items), []).append((best(fv), best(tv)))
        pairs = [(k, float(np.mean([q[0] for q in v])), float(np.mean([q[1] for q in v]))) for k, v in acc.items()]
        value = a.value if a.value != "value" else ""
    if len(pairs) < 2: fail(f"少于 2 个成对项（{len(pairs)}）：检查 --item / --from / --to")
    fl = a.from_label or (fcols[0] if len(fcols) == 1 else ("best of " if hib else "lowest of ") + "/".join(fcols))
    tl = a.to_label or (tcols[0] if len(tcols) == 1 else ("best of " if hib else "lowest of ") + "/".join(tcols))
    d = np.array([t - f for _, f, t in pairs]); worse = (d < 0) if hib else (d > 0)
    n = len(pairs); nw = int(worse.sum()); med = float(np.median(d)); mean = float(np.mean(d))
    style = a.style if a.style != "auto" else ("slope" if n <= 12 else "bars")
    fig, ax = _new_axes(a)
    if style == "slope":
        for (lab, f, t), w in zip(pairs, worse):
            ax.plot([0, 1], [f, t], color=BAD if w else NEUTRAL, lw=0.9, marker="o", ms=2.4, zorder=3)
        ax.plot([0, 1], [np.mean([p[1] for p in pairs]), np.mean([p[2] for p in pairs])], color="#111111", lw=1.8, zorder=4, label=f"mean ({n} items)")
        ax.set_xticks([0, 1]); ax.set_xticklabels([fl, tl]); ax.set_xlim(-0.12, 1.12)
        if n <= 12:
            lo, hi = ax.get_ylim(); ys = _spread([p[2] for p in pairs], (hi - lo) * 0.055)
            for (lab, f, t), w, yl in zip(pairs, worse, ys):
                ax.text(1.05, yl, lab, fontsize=5.6, va="center", ha="left", color=BAD if w else "#555555", clip_on=False)
        ax.set_ylabel(a.ylabel or value or "value")
        ax.legend(fontsize=6.0, loc="lower left" if hib else "upper left", handlelength=1.6)
    else:
        order = np.argsort(d) if hib else np.argsort(-d)
        dd = d[order]; ww = worse[order]
        ax.bar(np.arange(n), dd, color=[BAD if w else NEUTRAL for w in ww], width=0.8, zorder=3)
        ax.axhline(0, color="#333333", lw=0.6, zorder=4)
        if n <= 30:
            ax.set_xticks(np.arange(n)); ax.set_xticklabels([pairs[i][0] for i in order], rotation=90, fontsize=5.4)
        else:
            ax.set_xticks([]); ax.set_xlabel(f"{n} items, sorted by Δ")
        ax.set_ylabel(a.ylabel or (f"Δ {value}" if value else "Δ"))
        ax.grid(axis="y", lw=0.4, color="#e6e6e6", zorder=0)
    summary = f"{nw}/{n} worse; median Δ {_g(med)}; mean Δ {_g(mean)}"
    if style == "bars":   # sorted bars leave the corner opposite the long bars empty
        tx, ty, ha, va = (0.98, 0.04, "right", "bottom") if float(np.sum(d < 0)) * 2 > n else (0.02, 0.96, "left", "top")
    else:                 # slope: the corner the mean line moves away from is empty
        down = np.mean([q[2] for q in pairs]) < np.mean([q[1] for q in pairs])
        tx, ty, ha, va = (0.97, 0.97, "right", "top") if down else (0.97, 0.04, "right", "bottom")
    ax.text(tx, ty, summary + chr(10) + f"Δ = {tl} − {fl}", transform=ax.transAxes, fontsize=6.2, fontweight="bold", va=va, ha=ha, linespacing=1.3,
            color=BAD if nw * 2 > n else "#333333", zorder=6, bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
    fit_width(fig, [ax], a.width_mm / 25.4, what="paired")
    print(f"{fl} -> {tl}: {summary} (Δ = {tl} − {fl}; {'higher' if hib else 'lower'} is better)")
    src = [[lab, f, t, t - f, bool(w)] for (lab, f, t), w in zip(pairs, worse)]
    finish(fig, a, src, ["item", fl, tl, "delta", "worse"], root,
           f"{tl} vs. {fl} over {n} items: {nw}/{n} worse, median Δ {_g(med)}, mean Δ {_g(mean)}" + (" (slope chart)" if style == "slope" else " (sorted Δ)") + ".")


# ------------------------------------------------------------------ tradeoff
STAR = {"star": ("*", 2.2), "circle": ("o", 1.8), "diamond": ("D", 1.5)}


def _legend_auto(fig, ax, handles, labels, pts_disp, **kw):
    """legend in the corner of `ax` that covers the fewest points (ties: the first corner listed)"""
    rend = fig.canvas.get_renderer(); best = None
    for loc in ("lower right", "upper right", "lower left", "upper left", "center right", "center left"):
        leg = ax.legend(handles, labels, loc=loc, **kw); fig.canvas.draw(); bb = leg.get_window_extent(rend)
        n = sum(1 for (px, py) in pts_disp if bb.x0 <= px <= bb.x1 and bb.y0 <= py <= bb.y1); leg.remove()
        if best is None or n < best[0]: best = (n, loc)
        if n == 0: break
    return ax.legend(handles, labels, loc=best[1], **kw)


def tradeoff(a):
    from matplotlib.lines import Line2D
    root = os.path.abspath(a.project)
    rows = _rows(root, a.csv, [a.x, a.y, a.label] + ([a.size] if a.size else []) + ([a.color] if a.color else []))
    acc = collections.OrderedDict()
    for r in rows:
        try: xv, yv = float(r[a.x]), float(r[a.y]); sv = float(r[a.size]) if a.size else None
        except ValueError: continue
        acc.setdefault((r[a.label], r[a.color] if a.color else ""), []).append((xv, yv, sv))
    if len({k[0] for k in acc}) < 2: fail(f"{a.csv} 少于 2 个方法")
    pts = {k: (float(np.mean([p[0] for p in v])), float(np.mean([p[1] for p in v])), (float(np.mean([p[2] for p in v])) if a.size else None), len(v)) for k, v in acc.items()}
    ours_set = [s for s in (a.ours or "").split(",") if s]
    for s in ours_set:
        if s not in {k[0] for k in pts}: fail(f"--ours {s} 不在 {a.label} 列里：{sorted({k[0] for k in pts})}")
    is_ours = lambda k: k[0] in ours_set
    nm = lambda k: k[0] + (f" [{k[1]}]" if a.color else "")
    hib, lowx = not a.lower, not a.higher_x
    def dominates(p, q):
        bx = p[0] <= q[0] if lowx else p[0] >= q[0]; by = p[1] >= q[1] if hib else p[1] <= q[1]
        sx = p[0] < q[0] if lowx else p[0] > q[0]; sy = p[1] > q[1] if hib else p[1] < q[1]
        return bx and by and (sx or sy)
    peers = lambda k: [o for o in pts if o != k and (not a.color or o[1] == k[1])]      # with --color a front only makes sense inside one benchmark
    front = [k for k in pts if not any(dominates(pts[o], pts[k]) for o in peers(k))]
    labels = _parse_kv(a.labels)
    cats = list(dict.fromkeys(k[1] for k in pts)) if a.color else []
    if len(cats) > len(mf.CAT): print(f"[WARN] tradeoff: {len(cats)} {a.color} values, fill colours repeat after {len(mf.CAT)}")
    cmap = {c: mf.CAT[i % len(mf.CAT)] for i, c in enumerate(cats)}
    gap = None
    if a.broken_x:
        try: gap = tuple(sorted(float(t) for t in a.broken_x.split(",")))
        except ValueError: gap = None
        if gap is None or len(gap) != 2 or gap[0] == gap[1]: fail("--broken-x wants the hidden x interval, e.g. 65,110")
        if a.logx: fail("--broken-x and --logx cannot be combined")
        inside = [nm(k) for k, p in pts.items() if gap[0] < p[0] < gap[1]]
        if inside: fail(f"points inside the hidden interval {gap[0]:g}–{gap[1]:g}: {inside}")
        if not any(p[0] <= gap[0] for p in pts.values()) or not any(p[0] >= gap[1] for p in pts.values()): fail("--broken-x: each side of the break needs at least one point")
    xs_all = [p[0] for p in pts.values()]
    if gap:
        xl = (min(xs_all) - 0.06 * ((gap[0] - min(xs_all)) or 1.0), gap[0]); xr = (gap[1], max(xs_all) + 0.06 * ((max(xs_all) - gap[1]) or 1.0))
        wr = [max(xl[1] - xl[0], 1e-9), max(xr[1] - xr[0], 1e-9)]; tot = sum(wr); wr = [max(w / tot, 0.18) for w in wr]
        fig, axs = plt.subplots(1, 2, sharey=True, figsize=(a.width_mm / 25.4, a.height_in), gridspec_kw=dict(width_ratios=wr, wspace=0.03))
        fig.subplots_adjust(left=0.1, right=0.97, bottom=0.2, top=0.91 if a.title else 0.93)
        axs[0].set_xlim(*xl); axs[1].set_xlim(*xr); axs[0].spines["right"].set_visible(False); axs[1].spines["left"].set_visible(False); axs[1].tick_params(left=False, labelleft=False)
        for ax_, w in zip(axs, wr):
            for xe in ((1,) if ax_ is axs[0] else (0,)):
                dx = 0.012 * sum(wr) / w
                for ye in (0, 1): ax_.plot((xe - dx, xe + dx), (ye - 0.02, ye + 0.02), transform=ax_.transAxes, color="#222", lw=0.6, clip_on=False, zorder=9)
    else:
        fig, ax0 = _new_axes(a); axs = [ax0]
        if a.title: fig.subplots_adjust(top=0.91)
    side = lambda k: 0 if (not gap or pts[k][0] <= gap[0]) else 1
    smax = max((p[2] for p in pts.values() if p[2] is not None), default=None)
    def area(sv): return 14 + 110 * (sv / smax) if (smax and sv is not None) else 16
    mark, star_k = STAR[a.marker_ours]
    for k, p in pts.items():
        ax_ = axs[side(k)]; fc = cmap[k[1]] if a.color else (mf.ACCENT if is_ours(k) else OTHERS[0])
        if is_ours(k): ax_.scatter(p[0], p[1], s=area(p[2]) * star_k, marker=mark, color=fc, edgecolors="#333333" if a.color else "white", linewidths=0.5 if a.color else 0.4, zorder=5)
        else: ax_.scatter(p[0], p[1], s=area(p[2]), color=fc, alpha=0.75, edgecolors="white", linewidths=0.4, zorder=3)
    if not a.no_front:
        groups = [None] if not a.color else cats
        for g in groups:
            fx_ = sorted([k for k in front if g is None or k[1] == g], key=lambda k: pts[k][0])
            if len(fx_) > 1:
                for ax_ in axs: ax_.plot([pts[k][0] for k in fx_], [pts[k][1] for k in fx_], ls="--", lw=0.8, color="#9a9a9a" if g is None else cmap[g], alpha=1 if g is None else 0.6, zorder=1)
    if a.logx:
        from matplotlib.ticker import FuncFormatter
        axs[0].set_xscale("log"); axs[0].xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    for ax_ in axs: ax_.grid(lw=0.4, color="#ececec", zorder=0)
    # labels: with --color every method is named once (at its best point), ours at every point; --label-each names every point
    cand = []
    for k, p in pts.items():
        if a.color and not a.label_each and not is_ours(k):
            same = [o for o in pts if o[0] == k[0]]; bestk = max(same, key=lambda o: pts[o][1]) if hib else min(same, key=lambda o: pts[o][1])
            if k != bestk: continue
        cand.append(k)
    cand.sort(key=lambda k: not is_ours(k))
    placed = {}; taken = []
    seff = lambda k: area(pts[k][2]) * (star_k if is_ours(k) else 1.0)
    def offs_for(k):       # label offsets clear of the point's own marker: three rings (radius + 2, + 9, + 18 pt) in 8 directions
        r = math.sqrt(seff(k)) / 2 + 1.0; out_ = []
        for ring in (2.0, 9.0, 18.0):
            for ux, uy, ha, va in ((1, .6, "left", "bottom"), (1, -.6, "left", "top"), (-1, .6, "right", "bottom"), (-1, -.6, "right", "top"), (0, 1.1, "center", "bottom"), (0, -1.1, "center", "top"), (1, 0, "left", "center"), (-1, 0, "right", "center")):
                out_.append(((ux * (r + ring), uy * (r + ring * .5)), ha, va))
        return out_
    for si, ax_ in enumerate(axs):
        onax = [k for k in pts if side(k) == si]; ks = [k for k in cand if side(k) == si]
        res = mf.place_labels(fig, ax_, [(pts[k][0], pts[k][1], labels.get(k[0], k[0]), mf.ACCENT if is_ours(k) else "#333333", is_ours(k), offs_for(k), onax.index(k)) for k in ks],
                              fontsize=5.8, obstacles=taken, markers=[(pts[k][0], pts[k][1], seff(k)) for k in onax])
        for k, bb in zip(ks, res):
            placed[k] = "yes" if bb is not None else "no"
            if bb is not None: taken.append(bb)
    dropped = [nm(k) for k in cand if placed.get(k) == "no"]
    if dropped: print(f"[WARN] tradeoff: {len(dropped)} label(s) dropped, no free spot: {dropped} (points are in the source CSV)")
    ar = axs[0] if lowx else axs[-1]
    corner = ((0.05 if lowx else 0.95), (0.95 if hib else 0.05)); tail = (corner[0] + (0.13 if lowx else -0.13) / (1 if len(axs) == 1 else 2), corner[1] + (-0.13 if hib else 0.13))
    if not a.no_arrow:
        ar.annotate("", xy=corner, xytext=tail, xycoords="axes fraction", arrowprops=dict(arrowstyle="-|>", lw=0.8, color="#2e9b57"))
        ar.text(tail[0], tail[1], " better", transform=ar.transAxes, fontsize=6.0, color="#2e9b57", ha="left" if lowx else "right", va="top" if hib else "bottom", fontstyle="italic")
    xlab = a.xlabel or labels.get(a.x, a.x) + (", log scale" if a.logx else "")
    if gap: fig.supxlabel(xlab, fontsize=7.5, y=0.045)
    else: axs[0].set_xlabel(xlab)
    axs[0].set_ylabel(a.ylabel or labels.get(a.y, a.y))
    if a.title: fig.suptitle(a.title, fontsize=7.5, fontweight="bold", y=0.995)
    if a.size and not a.bubble_legend: axs[-1].text(0.98, 0.03, f"marker area ∝ {labels.get(a.size, a.size)}", transform=axs[-1].transAxes, fontsize=5.6, ha="right", va="bottom", color="#666666")
    # one legend: markers | bubble sizes in the first column, fill colours in the second
    hd = lambda t: (Line2D([], [], ls="", marker=""), t, True)
    c1, c2 = [], []
    if a.color and ours_set: c1 += [hd("Marker"), (Line2D([], [], ls="", marker=mark, ms=7, mfc="#9a9a9a", mec="#333333", mew=0.5), "Ours", False), (Line2D([], [], ls="", marker="o", ms=5, mfc="#9a9a9a", mec="white"), "Prior methods", False)]
    if a.bubble_legend and a.size:
        try: refs = [float(t) for t in a.bubble_legend.split(",")]
        except ValueError: fail("--bubble-legend wants numbers, e.g. 8,100,786")
        c1 += [hd(f"Bubble area = {labels.get(a.size, a.size)}")] + [(Line2D([], [], ls="", marker="o", ms=math.sqrt(area(v)), mfc="#c9ced4", mec="#8a8f98", mew=0.4), f"{v:g}", False) for v in sorted(refs, reverse=True)]
    if a.color: c2 += [hd(f"{labels.get(a.color, a.color)} (fill colour)")] + [(Line2D([], [], ls="", marker="o", ms=5, mfc=cmap[c], mec="white"), c, False) for c in cats]
    has_front = (not a.no_front) and sum(1 for _ in front) > 1
    if has_front: (c1 if c1 or not c2 else c2).append((Line2D([], [], ls="--", lw=0.8, color="#9a9a9a"), "Pareto front" if not a.color else "Pareto front per " + a.color, False))
    ents = c1 + c2 if not (c1 and c2) else c1 + [(Line2D([], [], ls="", marker=""), "", False)] * max(0, len(c2) - len(c1)) + c2 + [(Line2D([], [], ls="", marker=""), "", False)] * max(0, len(c1) - len(c2))
    if ents:
        legax = axs[0] if len(axs) == 1 or wr[0] >= wr[1] else axs[1]; fig.canvas.draw()
        disp = [legax.transData.transform((p[0], p[1])) for p in pts.values()]
        leg = _legend_auto(fig, legax, [e[0] for e in ents], [e[1] for e in ents], disp, fontsize=5.8, ncol=2 if c1 and c2 else 1, handlelength=1.6, labelspacing=0.35, columnspacing=1.0, borderpad=0.4, frameon=True, framealpha=0.9, edgecolor="#cccccc", fancybox=False)
        for t, e in zip(leg.get_texts(), ents):
            if e[2]: t.set_fontweight("bold")
        leg.get_frame().set_linewidth(0.4)
    fit_width(fig, list(axs), a.width_mm / 25.4, what="tradeoff")
    fx = sorted([k for k in front], key=lambda k: pts[k][0]); fxn = [nm(k) for k in fx]
    print(f"Pareto front ({'lower' if lowx else 'higher'} {a.x}, {'higher' if hib else 'lower'} {a.y}){' per ' + a.color if a.color else ''}: {fxn}")
    for k in pts:
        if not is_ours(k): continue
        if k in front: print(f"ours ({nm(k)}) is on the Pareto front")
        else: print(f"[WARN] tradeoff: ours ({nm(k)}) is dominated by {[nm(o) for o in peers(k) if dominates(pts[o], pts[k])]}; the caption must not claim the best trade-off")
    src = [[k[0], p[0], p[1], p[2] if p[2] is not None else "", p[3], k in front, k[1], placed.get(k, "skipped")] for k, p in pts.items()]
    n_on = sum(1 for k in pts if is_ours(k) and k in front); n_o = sum(1 for k in pts if is_ours(k))
    finish(fig, a, src, ["label", a.x, a.y, a.size or "size", "n", "on_front", a.color or "color", "placed_label"], root,
           f"{labels.get(a.y, a.y)} vs. {labels.get(a.x, a.x)}" + (f"; fill colour = {labels.get(a.color, a.color)}" if a.color else "") + ("" if a.no_front else f"; dashed = Pareto front{' per ' + a.color if a.color else ' (' + ', '.join(fxn) + ')'}")
           + (f"; ours on the front in {n_on}/{n_o} points" if n_o and not a.no_front else "") + (f"; x axis broken between {gap[0]:g} and {gap[1]:g}" if gap else "") + ".")


# ------------------------------------------------------------------ radar
def radar(a):
    root = os.path.abspath(a.project)
    vals = collections.OrderedDict()                    # series -> axis -> [values]
    if a.csv:
        rows = _rows(root, a.csv, [a.axis, a.series, a.value])
        for r in rows:
            try: v = float(r[a.value])
            except ValueError: continue
            vals.setdefault(r[a.series], collections.OrderedDict()).setdefault(r[a.axis], []).append(v)
        res = {}
    else:
        a.metrics = a.axes
        root, res, main, abl, gk, ref, metrics, _ = mf.load(a)
        a.ours = a.ours or ref
        for r in main:
            for m in metrics:
                if mf._isnum(r.get(m, "")): vals.setdefault(r[gk], collections.OrderedDict()).setdefault(m, []).append(float(r[m]))
    mean = {s: {k: float(np.mean(v)) for k, v in d.items()} for s, d in vals.items()}
    groups = collections.OrderedDict()
    for part in (a.groups.split(";") if a.groups else []):
        if "=" not in part: continue
        name, members = part.split("=", 1); members = [m.strip() for m in members.split("+") if m.strip()]
        miss = [m for m in members if m not in mean]
        if miss: fail(f"--groups {name.strip()}: 没有这些系列 {miss}（有：{list(mean)}）")
        groups[name.strip()] = members
    if groups:
        used = {m for ms in groups.values() for m in ms}
        series = collections.OrderedDict((s, mean[s]) for s in mean if s not in used)
        for name, ms in groups.items():
            common = set.intersection(*(set(mean[m]) for m in ms))
            series[name] = {k: float(np.mean([mean[m][k] for m in ms])) for k in common}
    else:
        series = collections.OrderedDict(mean)
    axes = [x.strip() for x in a.axes.split(",") if x.strip()] if a.axes else list(dict.fromkeys(k for d in series.values() for k in d))
    if len(axes) < 3: fail(f"雷达图至少要 3 根轴，现在只有 {len(axes)} 根（{axes}）：两根轴用 make_figure.py main 画分组柱")
    incomplete = [s for s, d in series.items() if any(k not in d for k in axes)]
    if incomplete: fail(f"这些系列缺某些轴的值，雷达多边形会断：{incomplete}；补齐或用 --axes 只取共有的轴")
    ours = a.ours if a.ours in series else None
    if a.ours and not ours: fail(f"--ours {a.ours} 不在系列里：{list(series)}")
    labels = _parse_kv(a.labels)
    import metric_direction as mdir
    lower = {k for k in axes if k in set(a.lower.split(",")) or (not a.csv and mdir.lower_is_better(k, res))}
    lohi = {}
    for k in axes:
        v = [series[s][k] for s in series]; span = (max(v) - min(v)) or abs(max(v)) or 1.0
        lohi[k] = (min(v) - 0.12 * span, max(v) + 0.06 * span)
    def rad(k, v):
        lo, hi = lohi[k]; t = (v - lo) / (hi - lo)
        return 0.14 + 0.86 * ((1 - t) if k in lower else t)
    def unrad(k, r):
        lo, hi = lohi[k]; t = (r - 0.14) / 0.86; t = (1 - t) if k in lower else t
        return lo + t * (hi - lo)
    K = len(axes); th = np.linspace(0, 2 * np.pi, K, endpoint=False) + np.pi / 2; thc = np.r_[th, th[:1]]
    w_in = a.width_mm / 25.4
    fig = plt.figure(figsize=(w_in, w_in * 1.12))
    ax = fig.add_axes([0.2, 0.3, 0.6, 0.56], projection="polar")
    ax.set_ylim(0, 1.0); ax.set_xticks([]); ax.set_yticks([]); ax.spines["polar"].set_visible(False); ax.grid(False)
    for rr in (0.25, 0.5, 0.75, 1.0):
        ax.plot(thc, np.full(K + 1, rr), color="#d0d0d0", lw=0.4, zorder=1)
    for t in th: ax.plot([t, t], [0, 1.0], color="#bdbdbd", lw=0.4, zorder=1)
    def align(t):
        c, s_ = np.cos(t), np.sin(t)
        return ("left" if c > 0.2 else "right" if c < -0.2 else "center"), ("bottom" if s_ > 0.2 else "top" if s_ < -0.2 else "center")
    for t, k in zip(th, axes):
        for rr in (0.5, 0.75):     # inner rings only: the outer ring is where ours' values go
            ax.text(t + 0.13, rr, f"{unrad(k, rr):.3g}", fontsize=5.4, color="#9a9a9a", ha="center", va="center", zorder=2)
        ha, va = align(t)
        ax.text(t, 1.3, labels.get(k, k) + (" ↓" if k in lower else ""), fontsize=6.6, fontweight="bold", ha=ha, va=va)
    others = [s for s in series if s != ours]; src = []
    for i, s in enumerate(others):
        r = [rad(k, series[s][k]) for k in axes]
        ax.plot(thc, r + r[:1], color=OTHERS[i % len(OTHERS)], lw=0.9, ls=DASHES[i % len(DASHES)], marker="o", ms=1.8, label=s, zorder=3)
    if ours:
        r = [rad(k, series[ours][k]) for k in axes]
        ax.plot(thc, r + r[:1], color=mf.ACCENT, lw=1.5, marker="D", ms=2.4, label=labels.get(ours, ours), zorder=5)
        ax.fill(thc, r + r[:1], color=mf.ACCENT, alpha=0.07, zorder=4)
        for t, k, rr in zip(th, axes, r):
            ha, va = align(t)
            ax.text(t, rr + 0.08, f"{series[ours][k]:.1f}", fontsize=6.0, color=mf.ACCENT, fontweight="bold", ha=ha, va=va, zorder=6)
    best_n = 0
    for k in axes:
        pick = (min if k in lower else max)(series, key=lambda s: series[s][k])
        for s in series: src.append([s, k, series[s][k], lohi[k][0], lohi[k][1], k in lower, s == pick])
        best_n += int(pick == ours)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.3), ncol=2, fontsize=5.8, handlelength=2.2, columnspacing=1.0)   # follows the axes when fit_width shrinks it
    fit_width(fig, [ax], w_in, keep_aspect=True, what="radar")
    if ours:
        notbest = [k for k in axes if (min if k in lower else max)(series, key=lambda s: series[s][k]) != ours]
        print(f"ours ({ours}) is best on {best_n}/{K} axes" + (f"; not best on {notbest} — the caption must not call it an envelope" if notbest else ""))
    cap = "Radar over benchmarks; every axis is scaled independently between the printed values, outward = better"
    if lower: cap += f" (axes marked ↓ are lower-is-better and flipped: {sorted(lower)})"
    finish(fig, a, src, ["series", "axis", "value", "axis_lo", "axis_hi", "lower_is_better", "best"], root, cap + ".")


# ------------------------------------------------------------------ schematic and strip
def _crop_to(img, aspect):
    h, w = img.shape[:2]
    if w / h > aspect:
        nw = int(round(h * aspect)); x0 = (w - nw) // 2; return img[:, x0:x0 + nw]
    nh = int(round(w / aspect)); y0 = (h - nh) // 2; return img[y0:y0 + nh]


def _tile(pattern, seed, n=8):
    from matplotlib.colors import to_rgb
    rgb, x, g = (np.array(to_rgb(COLORS[k])) for k in ("rgb", "x", "shared"))
    rng = np.random.default_rng(seed)
    if pattern == "grid":        # identity preserved: every cell keeps one source
        choice = rng.integers(0, 3, (n // 2, n // 2)); lut = np.stack([rgb, x, g])
        return np.clip(lut[choice] * 0.85 + 0.15, 0, 1)
    t = rng.random((n * 2, n * 2))[..., None]     # mixed / entangled: every cell a blend
    return np.clip(t * rgb + (1 - t) * x + rng.normal(0, 0.05, t.shape), 0, 1)


def draw_spec(spec, root):
    W, H = (float(v) for v in spec.get("size_mm", [100, 60])); fs = float(spec.get("font_pt", 6.5))
    fig = plt.figure(figsize=(W / 25.4, H / 25.4)); ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    box = {}; src = []; warns = []; illustrative = False
    for p in spec.get("panels", []) or []:
        (x, y), (w, h) = p["xy"], p["wh"]; ec = PANEL_EDGE.get(p.get("style", "neutral"), col(p.get("style")))
        ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2", fc="none", ec=ec, lw=0.8, ls=(0, (3, 1.5))))
        if p.get("title"):
            ax.text(x + w / 2, y + h - 1.0, p["title"], ha="center", va="top", fontsize=fs + 1.5, fontweight="bold", fontstyle="italic", color=ec)
        src.append(["panel", p.get("title", ""), x, y, w, h, p.get("style", "")])
    for n in spec.get("nodes", []) or []:
        kind = n.get("kind", "box")
        if kind not in ("box", "trapezoid", "stack", "image", "tile", "mark", "text"): fail(f"节点 {n.get('id')} 的 kind={kind} 不认识")
        cx, cy = (float(v) for v in n["xy"]); w, h = (float(v) for v in n.get("wh", [10, 6])); x0, y0 = cx - w / 2, cy - h / 2
        c = col(n.get("color"), "neutral"); txt = str(n.get("text", "")); tc = "white" if _dark(c) else "black"
        if kind == "box":
            if n.get("outline"):
                ax.add_patch(patches.FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0,rounding_size=0.8", fc="white", ec=c, lw=0.8, ls="--" if n.get("dashed") else "-")); tc = c
            else:
                ax.add_patch(patches.FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0,rounding_size=0.8", fc=c, ec="none"))
        elif kind == "trapezoid":
            k = float(n.get("taper", 0.3)) * h / 2
            ax.add_patch(patches.Polygon([(x0, y0), (x0 + w, y0 + k), (x0 + w, y0 + h - k), (x0, y0 + h)], closed=True, fc=c, ec="none"))
        elif kind == "stack":
            d = min(w, h) * 0.12
            for i in (2, 1):
                ax.add_patch(patches.Rectangle((x0 + i * d, y0 + i * d), w - 2 * d, h - 2 * d, fc=c, ec="white", lw=0.4, alpha=0.55 + 0.15 * (2 - i)))
            ax.add_patch(patches.Rectangle((x0, y0), w - 2 * d, h - 2 * d, fc=c, ec="white", lw=0.4))
            cx, cy = x0 + (w - 2 * d) / 2, y0 + (h - 2 * d) / 2
        elif kind == "image":
            p = n.get("src", ""); ap = p if os.path.isabs(p) else os.path.join(root, p)
            if not os.path.isfile(ap): fail(f"节点 {n.get('id')} 的图像 {p} 不存在")
            from PIL import Image
            im = np.asarray(Image.open(ap).convert("RGB")); im = _crop_to(im, w / h)
            ax.imshow(im, extent=[x0, x0 + w, y0, y0 + h], interpolation="lanczos", zorder=2)
            ax.add_patch(patches.Rectangle((x0, y0), w, h, fc="none", ec=c if n.get("color") else "#666666", lw=0.5, zorder=3))
        elif kind == "tile":
            illustrative = True
            ax.imshow(_tile(n.get("pattern", "mixed"), zlib.crc32(str(n.get("id")).encode())), extent=[x0, x0 + w, y0, y0 + h], interpolation="nearest", zorder=2)
            ax.add_patch(patches.Rectangle((x0, y0), w, h, fc="none", ec="#666666", lw=0.5, ls=(0, (2, 1)), zorder=3))
        elif kind == "mark":
            m = n.get("mark", "check"); lw = max(1.5, min(w, h) * 0.9)
            if m == "check": ax.plot([x0, x0 + w * 0.38, x0 + w], [y0 + h * 0.5, y0, y0 + h], color=col(n.get("color"), "good"), lw=lw, solid_capstyle="round", solid_joinstyle="round")
            elif m == "cross":
                cc = col(n.get("color"), "bad"); ax.plot([x0, x0 + w], [y0, y0 + h], color=cc, lw=lw, solid_capstyle="round"); ax.plot([x0, x0 + w], [y0 + h, y0], color=cc, lw=lw, solid_capstyle="round")
            else: fail(f"节点 {n.get('id')}: mark 只认 check / cross")
        if txt and kind != "image":
            ax.text(cx, cy, txt, ha="center", va="center", fontsize=float(n.get("size", fs)), color=n.get("text_color", c if kind == "text" else tc),
                    fontweight="bold" if n.get("bold", kind != "text") else "normal", fontstyle="italic" if n.get("italic") else "normal", zorder=4, linespacing=1.05)
        if n.get("label"):
            ax.text(cx if kind != "stack" else x0 + w / 2, y0 - 0.8, n["label"], ha="center", va="top", fontsize=fs, color=col(n.get("label_color", n.get("color")), "neutral"), fontweight="bold" if n.get("label_bold", True) else "normal")
        if n.get("id"): box[n["id"]] = (x0, y0, w, h)
        if x0 < -0.01 or y0 < -0.01 or x0 + w > W + 0.01 or y0 + h > H + 0.01: warns.append(f"节点 {n.get('id') or txt[:12]} 超出画布 {W}×{H} mm")
        src.append([kind, n.get("id", ""), cx, cy, w, h, n.get("src") or txt.replace("\n", " ")])
    ids = list(box)
    for i, p in enumerate(ids):
        for q in ids[i + 1:]:
            (ax0, ay0, aw, ah), (bx0, by0, bw, bh) = box[p], box[q]
            if min(ax0 + aw, bx0 + bw) - max(ax0, bx0) > 0.3 and min(ay0 + ah, by0 + bh) - max(ay0, by0) > 0.3:
                warns.append(f"节点 {p} 与 {q} 重叠")
    for e in spec.get("edges", []) or []:
        f, t = e.get("from"), e.get("to")
        if f not in box or t not in box: fail(f"连线 {f} -> {t}：节点 id 不存在（有：{ids}）")
        (fx, fy, fw, fh), (tx, ty, tw, th_) = box[f], box[t]
        fcx, fcy, tcx, tcy = fx + fw / 2, fy + fh / 2, tx + tw / 2, ty + th_ / 2
        def side(s, x, y, w, h, cx, cy):
            return {"r": (x + w, cy), "l": (x, cy), "t": (cx, y + h), "b": (cx, y)}[s]
        if abs(tcx - fcx) >= abs(tcy - fcy): fs_, ts_ = ("r", "l") if tcx > fcx else ("l", "r")
        else: fs_, ts_ = ("t", "b") if tcy > fcy else ("b", "t")
        p0 = side(e.get("from_side", fs_), fx, fy, fw, fh, fcx, fcy); p1 = side(e.get("to_side", ts_), tx, ty, tw, th_, tcx, tcy)
        gap = float(e.get("gap", 0.8)); v = np.subtract(p1, p0); L = float(np.hypot(*v)) or 1.0; u = v / L
        p0 = tuple(np.add(p0, u * gap)); p1 = tuple(np.subtract(p1, u * gap))
        ax.add_patch(patches.FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=5.5, lw=float(e.get("lw", 0.9)), color=col(e.get("color"), "neutral"),
                                             ls="--" if e.get("dashed") else "-", connectionstyle=f"arc3,rad={float(e.get('rad', 0))}", zorder=3))
        src.append(["edge", f"{f}->{t}", "", "", "", "", e.get("color", "")])
    lg = spec.get("legend")
    if lg:
        x, y = lg["xy"]; step = float(lg.get("step_mm", 22))
        for i, (ck, lab) in enumerate(lg["items"]):
            ax.add_patch(patches.Rectangle((x + i * step, y - 1.0), 2.0, 2.0, fc=col(ck), ec="none"))
            ax.text(x + i * step + 2.8, y, lab, va="center", ha="left", fontsize=fs - 0.3, color=col(ck) if ck != "shared" else "#555555", fontweight="bold")
    for w_ in warns: print(f"[WARN] schematic: {w_}")
    return fig, src, illustrative, W


def schematic(a):
    import yaml
    root = os.path.abspath(a.project); sp = os.path.join(root, a.spec)
    if not os.path.exists(sp): fail(f"{a.spec} 不存在（模板：templates/motivation_scheme.yaml）")
    spec = yaml.safe_load(io.open(sp, encoding="utf-8")) or {}
    fig, src, illustrative, W = draw_spec(spec, root)
    a.width_mm = W
    cap = f"Schematic drawn from {a.spec}"
    if illustrative: cap += "; tiles are illustrations, not measured feature maps — say so in the caption"
    finish(fig, a, src, ["kind", "id", "x_mm", "y_mm", "w_mm", "h_mm", "text_or_src"], root, cap + ".")


def strip(a):
    root = os.path.abspath(a.project)
    items = []
    for it in a.item:
        parts = [p.strip() for p in it.split("|")]
        if len(parts) < 2: fail(f"--item 要写成 \"标签|图1[|图2]\"：{it}")
        items.append(parts)
    W = a.width_mm; pad = 0.6; ncol = max(len(p) - 1 for p in items); iw = (W - pad * (ncol + 1)) / ncol; ih = iw * a.aspect
    row_h = ih + 4.2; top = 4.0 if a.title else 0.8; H = top + row_h * len(items)
    nodes = []
    for r, parts in enumerate(items):
        y = H - top - r * row_h - ih / 2
        for c, p in enumerate(parts[1:]):
            nodes.append({"kind": "image", "src": p, "xy": [pad + iw / 2 + c * (iw + pad), y], "wh": [iw, ih]})
        nodes.append({"kind": "text", "text": parts[0], "xy": [W / 2, y - ih / 2 - 1.9], "wh": [W, 2.6], "size": a.font_pt, "bold": False, "color": "neutral"})
    if a.title: nodes.append({"kind": "text", "text": a.title, "xy": [W / 2, H - 1.8], "wh": [W, 3], "size": a.font_pt + 0.6, "bold": True, "italic": True, "color": "bad"})
    fig, src, _, _ = draw_spec({"size_mm": [W, H], "font_pt": a.font_pt, "nodes": nodes}, root)
    finish(fig, a, src, ["kind", "id", "x_mm", "y_mm", "w_mm", "h_mm", "text_or_src"], root, f"Dataset strip: {len(items)} benchmarks, paired modalities side by side.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("condition", help="metric vs a controlled condition; leader changes, gaps, regimes")
    c.add_argument("--csv", required=True, help="long table: one row per (series, condition value[, seed])"); c.add_argument("--x", required=True); c.add_argument("--y", required=True)
    c.add_argument("--series", default="", help="column naming the line; empty = one line"); c.add_argument("--ours", default="")
    c.add_argument("--among", default="", help="series that compete for the lead (default: all but --ours)")
    c.add_argument("--gap", action="append", help="'A,B' or 'A,B@x': arrow and Δ between two series (largest |Δ| when @x is omitted)")
    c.add_argument("--regions", default="", help="'Night:0:0.3,Day:0.7:1' shaded regimes"); c.add_argument("--lower", action="store_true", help="lower metric is better")
    c.add_argument("--logx", action="store_true"); c.add_argument("--legend", default="below", help="'below' (default, never covers data) or a matplotlib loc")
    p = sub.add_parser("paired", help="same items under two settings: slope chart or sorted Δ bars")
    p.add_argument("--csv", required=True); p.add_argument("--item", required=True, help="column(s) naming an item, comma list")
    p.add_argument("--from", dest="from_", required=True, help="column(s) of the reference setting; several = the better of them")
    p.add_argument("--to", required=True, help="column(s) of the compared setting"); p.add_argument("--from-label", default=""); p.add_argument("--to-label", default="")
    p.add_argument("--cond", default="", help="long table: column whose values --from/--to name"); p.add_argument("--value", default="value", help="long table: value column / axis name")
    p.add_argument("--lower", action="store_true"); p.add_argument("--style", choices=["auto", "slope", "bars"], default="auto")
    t = sub.add_parser("tradeoff", help="accuracy vs cost with the Pareto front")
    t.add_argument("--csv", required=True); t.add_argument("--x", required=True, help="cost column (params, GFLOPs, latency, labels used …)"); t.add_argument("--y", required=True)
    t.add_argument("--label", default="method", help="column naming each point; its value is the text label"); t.add_argument("--size", default=""); t.add_argument("--ours", default="", help="label value(s) of ours, comma list")
    t.add_argument("--logx", action="store_true"); t.add_argument("--lower", action="store_true", help="lower y is better"); t.add_argument("--higher-x", action="store_true", help="higher x is better")
    t.add_argument("--color", default="", help="categorical column (dataset): one fill colour per value, legend of the fills; the Pareto front is then per value")
    t.add_argument("--marker-ours", choices=list(STAR), default="star", help="marker of the --ours points (others stay circles)")
    t.add_argument("--label-each", action="store_true", help="with --color: name every point, not once per method (ours is always named at every point)")
    t.add_argument("--broken-x", default="", help="'65,110': hide this x interval, two axes with break marks (not with --logx)")
    t.add_argument("--bubble-legend", default="", help="'8,100,786': reference bubble sizes in the legend (needs --size)")
    t.add_argument("--no-front", action="store_true", help="no Pareto front line"); t.add_argument("--title", default="")
    t.add_argument("--no-arrow", action="store_true", help="no green 'better' arrow")
    r = sub.add_parser("radar", help="one polygon per series over >= 3 benchmarks")
    r.add_argument("--csv", default="", help="long table, one row per (axis, series[, seed]) value; empty = state.results main table")
    r.add_argument("--axis", default="dataset"); r.add_argument("--series", default="method"); r.add_argument("--value", default="AP")
    r.add_argument("--axes", default="", help="axis order / subset (comma list)"); r.add_argument("--groups", default="", help="'name=s1+s2;name2=s3+s4': average series into one polygon")
    r.add_argument("--ours", default=""); r.add_argument("--lower", default="")
    s = sub.add_parser("strip", help="dataset thumbnails"); s.add_argument("--item", action="append", required=True, help="'label|img_a|img_b'"); s.add_argument("--title", default="")
    s.add_argument("--aspect", type=float, default=0.75, help="image height / width"); s.add_argument("--font-pt", type=float, default=6.0)
    sc = sub.add_parser("schematic", help="block diagram from a YAML spec"); sc.add_argument("--spec", required=True)
    widths = {"condition": 88, "paired": 88, "tradeoff": 88, "radar": 62, "strip": 30, "schematic": 0}
    for name, q in (("condition", c), ("paired", p), ("tradeoff", t), ("radar", r), ("strip", s), ("schematic", sc)):
        q.add_argument("--project", default="."); q.add_argument("--out", required=True, help="figures/<name>.png (the .pdf is written next to it)")
        q.add_argument("--labels", default="", help="'col=display name,…'")
        if name != "schematic": q.add_argument("--width-mm", type=float, default=widths[name])
        if name in ("condition", "paired", "tradeoff"):
            q.add_argument("--height-in", type=float, default=2.1); q.add_argument("--xlabel", default=""); q.add_argument("--ylabel", default="")
    a = ap.parse_args()
    if not a.out.lower().endswith(".png"): fail("--out 给 .png 路径（同名 .pdf、_gray.png、.source.csv 自动写在旁边）")
    if a.cmd == "schematic": a.width_mm = 0
    {"condition": condition, "paired": paired, "tradeoff": tradeoff, "radar": radar, "strip": strip, "schematic": schematic}[a.cmd](a)


if __name__ == "__main__":
    main()
