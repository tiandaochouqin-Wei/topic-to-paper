# -*- coding: utf-8 -*-
"""P5 — the parts of a motivation / teaser figure (the "Fig. 1" of a CV paper), one PDF per panel. Run by Claude.

  python make_teaser.py radar     --project . --out figures/fig_teaser_radar.png [--csv results/benchmarks.csv --axis dataset --series method --value AP]
                                  [--groups "RGB-only (avg. 7)=a_rgb+b_rgb;Naive (avg. 7)=a_cat+b_cat"] [--ours ours] [--lower m1,m2]
                                  [--labels "m3fd=M3FD,llvip=LLVIP"] [--axes m3fd,llvip,...] [--width-mm 62]
      one polygon per series over K >= 3 benchmark axes. Without --csv: axes = metric columns of state.results main_table and
      series = method means over seeds. Every axis is scaled to its own range, printed on the axis; outward is always better
      (lower-is-better axes are flipped and say so in the caption). Ours' values are written at its vertices.
  python make_teaser.py strip     --project . --out figures/fig_teaser_data.png --item "M3FD RGB/IR|figures/src/m3fd_rgb.png|figures/src/m3fd_ir.png"
                                  [--item ...] [--width-mm 30] [--title "6 datasets"]
      the dataset column: one row per benchmark, the paired images side by side, the label underneath.
  python make_teaser.py schematic --project . --out figures/fig_teaser_scheme.png --spec figures/teaser_scheme.yaml
      a naive-vs-ours block diagram drawn from a YAML spec whose coordinates are millimetres on the printed figure (vector output).
      Spec keys: size_mm, font_pt, panels, nodes, edges, legend; node kinds: box, trapezoid, stack, image, tile, mark, text
      (full description in references/phases/P5.md, a worked spec in templates/teaser_scheme.yaml).

Every subcommand writes <out>.png, <out>.pdf, <out>_gray.png and <out>.source.csv and registers the panel in figures.csv through
make_figure.finish (layout audit, inspected=no). Do not pre-compose the teaser: one PDF per panel, then
  latex_check.py figure --panels a.pdf,b.pdf,c.pdf --labels ... --width 0.15,0.33,0.50 --env figure*
"""
import argparse, collections, csv, io, os, sys, zlib
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


# ------------------------------------------------------------------ radar
def _parse_kv(s, sep=","):
    return dict(kv.split("=", 1) for kv in s.split(sep) if "=" in kv) if s else {}


def radar(a):
    root = os.path.abspath(a.project)
    vals = collections.OrderedDict()                    # series -> axis -> [values]
    if a.csv:
        path = os.path.join(root, a.csv)
        if not os.path.exists(path): fail(f"{a.csv} 不存在")
        rows = list(csv.DictReader(io.open(path, encoding="utf-8-sig")))
        if not rows: fail(f"{a.csv} 是空表")
        for c in (a.axis, a.series, a.value):
            if c not in rows[0]: fail(f"{a.csv} 没有列 {c}：{list(rows[0])}")
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
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import metric_direction as mdir
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
    fit_width(fig, ax, w_in)
    if ours:
        notbest = [k for k in axes if max(series, key=lambda s: (-1 if k in lower else 1) * series[s][k]) != ours]
        print(f"ours ({ours}) is best on {best_n}/{K} axes" + (f"; not best on {notbest} — the caption must not call it an envelope" if notbest else ""))
    cap = "Radar over benchmarks; every axis is scaled independently between the printed values, outward = better"
    if lower: cap += f" (axes marked ↓ are lower-is-better and flipped: {sorted(lower)})"
    finish(fig, a, src, ["series", "axis", "value", "axis_lo", "axis_hi", "lower_is_better", "best"], root, cap + ".")


# ------------------------------------------------------------------ schematic
def _crop_to(img, aspect):
    h, w = img.shape[:2]
    if w / h > aspect:
        nw = int(round(h * aspect)); x0 = (w - nw) // 2; return img[:, x0:x0 + nw]
    nh = int(round(w / aspect)); y0 = (h - nh) // 2; return img[y0:y0 + nh]


def _tile(pattern, seed, n=8):
    rng = np.random.default_rng(seed)
    from matplotlib.colors import to_rgb
    rgb, x, g = (np.array(to_rgb(COLORS[k])) for k in ("rgb", "x", "shared"))
    if pattern == "grid":        # modality-preserved: each cell keeps one identity
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
    ids = [k for k in box]
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


def fit_width(fig, ax, target_in, tries=8):
    """axis labels hang outside a polar axes; savefig(bbox_inches='tight') then makes the PDF wider than the print width and
    G5 sees every label shrunk (4.5 pt at 62 mm in the first version). Shrink the axes until the tight box fits the width."""
    target_in = target_in - 2 * plt.rcParams["savefig.pad_inches"]     # bbox_inches='tight' adds this pad on both sides
    for _ in range(tries):
        bb = fig.get_tightbbox(fig.canvas.get_renderer()).width
        if bb <= target_in * 1.005: return
        x0, y0, w, h = ax.get_position().bounds; f = max(0.5, target_in / bb) ** 1.3
        ax.set_position([x0 + w * (1 - f) / 2, y0 + h * (1 - f) / 2, w * f, h * f])
    print(f"[WARN] radar: tight width {bb * 25.4:.0f} mm still exceeds {target_in * 25.4:.0f} mm; shorten the axis labels")


def finish(fig, a, src, hdr, root, caption):
    mf.finish(fig, a, src, hdr, root, caption); plt.close(fig)


def schematic(a):
    import yaml
    root = os.path.abspath(a.project); sp = os.path.join(root, a.spec)
    if not os.path.exists(sp): fail(f"{a.spec} 不存在（模板：templates/teaser_scheme.yaml）")
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
    r = sub.add_parser("radar"); r.add_argument("--csv", default="", help="long table, one row per (axis, series[, seed]) value; empty = state.results main table")
    r.add_argument("--axis", default="dataset"); r.add_argument("--series", default="method"); r.add_argument("--value", default="AP")
    r.add_argument("--axes", default="", help="axis order / subset (comma list)"); r.add_argument("--groups", default="", help="'name=s1+s2;name2=s3+s4': average series into one polygon")
    r.add_argument("--ours", default=""); r.add_argument("--lower", default=""); r.add_argument("--labels", default=""); r.add_argument("--width-mm", type=float, default=62)
    s = sub.add_parser("strip"); s.add_argument("--item", action="append", required=True, help="'label|img_a|img_b'"); s.add_argument("--title", default="")
    s.add_argument("--width-mm", type=float, default=30); s.add_argument("--aspect", type=float, default=0.75, help="image height / width"); s.add_argument("--font-pt", type=float, default=6.0)
    c = sub.add_parser("schematic"); c.add_argument("--spec", required=True)
    for p in (r, s, c): p.add_argument("--project", default="."); p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "schematic": a.width_mm = 0
    {"radar": radar, "strip": strip, "schematic": schematic}[a.cmd](a)


if __name__ == "__main__":
    main()
