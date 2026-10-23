# -*- coding: utf-8 -*-
"""P5 — standard data figures from the results tables, so main/ablation figures are generated, not hand-drawn. Run by Claude.

  python make_figure.py main     --project . --out figures/fig_main.png [--metrics rmse_E1,rmse_E2,...] [--labels "rmse_E1=E1 in-dom."] [--logy]
                                 [--ours ours] [--width-mm 183] [--height-in 2.6] [--ylabel "..."]
      grouped bars: x = metric columns (conditions), one bar per method; multi-seed methods -> mean ± s.d. with per-seed dots; ours in accent colour
  python make_figure.py ablation --project . --out figures/fig_abl.png [--metrics ...] [--labels ...]
      Δ vs reference per metric, grey ±2σ_ref√2 band (seed noise), bars inside the band greyed (not resolvable); index row + legend of ablation names
  python make_figure.py seeds    --project . --out figures/fig_seeds.png --methods ours,RCNN [--metrics ...]
      mean ± s.d. with per-seed dots for the named methods only (Table-IV-style stability figure)
  python make_figure.py curves   --project . --csv results/curves.csv --out figures/fig_curves.png --x epoch --y val_loss [--series method]
                                 [--seed seed] [--panel dataset] [--xlabel ...] [--band sd|minmax|none] [--logx]
      one line per series; seeds collapse to mean with a shaded s.d. (or min–max) band; optional one panel per --panel value
      (training curves, horizon / threshold sweeps, trade-off curves). Reads a long CSV, not state.results.
      Fig-6-style training curves: [--ema 0.12] EMA-smoothed solid line over a faint raw line (s_t = a*x_t + (1-a)*s_t-1, per series
      per panel, on the seed mean); [--inset last:40 | x0:x1] zoom of the last N points as an inset + grey rectangle on the panel;
      [--annotate last --ours ours [--baseline base] [--delta-unit pp]] filled / open circle at the last epoch both series share and
      the text "Δy @ epoch N: +d | ours a | base b" (numbers from the smoothed curves, also written to the source CSV as a
      kind=summary row); [--ncols 3] [--free-y] [--letters] [--legend above|best|none]. Without these options the output is unchanged.
  python make_figure.py stems    --csv results/backbones.csv --item backbone --x baseline_AP --y ours_AP [--group family] --out figures/fig_stems.png
      paired baseline (x) vs ours (y) per item: dashed y = x, one stem from the diagonal to each point, gain label "+d" on top, colour
      by --group (without --group: one colour + marker per item); prints "k/n <item>s above y = x"
  python make_figure.py box      --csv results/auroc.csv --value auroc --group dataset [--whis 5,95] [--vline 0.5] --out figures/fig_box.png
      horizontal box per group (box = quartiles, line = median, whiskers = the given percentiles); source CSV holds the five numbers
  python make_figure.py hbar     --csv results/drop.csv --value dAP --group dataset [--lower] [--fmt "{:+.2f}"] --out figures/fig_hbar.png
      horizontal bars, value printed at the bar end, negative bars extend left of the zero line (rows of one group are averaged)

  --lower m1,m2   metrics where lower is better (unlisted: state.results metric_direction / primary_direction, else the
                  name regex of metric_direction.py, else higher). Only affects which value is called best in
                  the source CSV / caption text; bars and dots are drawn the same either way.

Reads state.results (main_table, ablation_table, group_key, reference_method, metric columns = all numeric columns unless --metrics).
Writes <out>.png (400 dpi at --width-mm), <out>.pdf, <out>.source.csv, and appends/updates a row in figures.csv (path, print width, source).
Style: serif 7.5 pt, no top/right spines, NMI-pastel blues + one red accent (same family as the validated demo_comparison figure).
"""
import argparse, csv, io, os, sys, statistics, collections
import numpy as np
import matplotlib
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.size": 7.5, "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"], "mathtext.fontset": "stix",
                     "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
                     "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42, "ps.fonttype": 42, "axes.unicode_minus": False})   # 42 = TrueType outlines; Type 3 (the default) is rejected by IEEE / Elsevier production
CAT = ["#3d6a94", "#e8833a", "#6c8e7a", "#5fb3b3", "#8c7aa9", "#b8873a", "#7a7a7a", "#a0c4e0", "#2b4c6f", "#c8a2c8", "#8fbf6a", "#a35f4a"]   # categorical fills (datasets, families); no red, which is the accent
MARKS = ["o", "s", "^", "v", "D", "P", "X", "h"]
PALETTE = ["#9aa5b1", "#b8c4d0", "#7fa7c9", "#5b8bb5", "#3d6a94", "#2b4c6f", "#8c7aa9", "#6c8e7a"]; ACCENT = "#d1495b"

def load(a):
    import yaml
    root = os.path.abspath(a.project); st = yaml.safe_load(io.open(os.path.join(root, "research-state.yaml"), encoding="utf-8")) or {}
    res = st.get("results") or {}
    main = list(csv.DictReader(open(os.path.join(root, res.get("main_table", "results/main.csv")), encoding="utf-8-sig")))
    ap_ = os.path.join(root, res.get("ablation_table", "results/ablation.csv"))
    abl = list(csv.DictReader(open(ap_, encoding="utf-8-sig"))) if os.path.exists(ap_) else []
    gk = res.get("group_key", "method"); ref = res.get("reference_method", "ours")
    skip = {"run_id", gk, "seed", "table", "hardware", "ablation"}
    metrics = a.metrics.split(",") if a.metrics else [c for c in main[0].keys() if c not in skip and all(_isnum(r.get(c, "")) for r in main if r.get(c, "") != "")]
    labels = dict(kv.split("=", 1) for kv in a.labels.split(",") if "=" in kv) if a.labels else {}
    return root, res, main, abl, gk, ref, metrics, labels

def _isnum(x):
    try: float(x); return True
    except Exception: return False

def by_method(rows, gk, metrics):
    d = collections.OrderedDict()
    for r in rows:
        if r.get(gk) is None: continue
        d.setdefault(r[gk], []).append([float(r[m]) if r.get(m, "") != "" else np.nan for m in metrics])
    return {k: np.array(v) for k, v in d.items()}


def audit_layout(fig, clip_tol_px=2.0, overlap_tol_px=1.0):
    """in-memory layout audit before saving (after scipilot-figure-skill visual_qa): -> [(severity, msg)].
    FAIL on missing glyphs (boxes in the output); WARN on user text outside the canvas and on adjacent tick labels overlapping."""
    import logging, warnings, io as _io
    import matplotlib.text as _mtext
    issues = []
    got = []
    class _H(logging.Handler):
        def emit(self, r): got.append(r.getMessage())
    h = _H(); lg = logging.getLogger("matplotlib"); lvl = lg.level; lg.setLevel(logging.WARNING); lg.addHandler(h)
    try:
        with warnings.catch_warnings(record=True) as wl:
            warnings.simplefilter("always"); fig.savefig(_io.BytesIO(), format="png", dpi=100)
        got += [str(w.message) for w in wl]
    finally:
        lg.removeHandler(h); lg.setLevel(lvl)
    glyph = [m for m in got if "Glyph" in m or "missing from font" in m or "missing from current font" in m]
    if glyph: issues.append(("FAIL", "missing glyphs (boxes in output): " + " | ".join(dict.fromkeys(glyph))[:200]))
    renderer = fig.canvas.get_renderer()
    # finish() saves with bbox_inches="tight", which grows the page to the artists' union; a label hanging below the
    # nominal canvas is therefore fine. What tight cannot rescue is text that overlaps ANOTHER axes' data area, so
    # clipping is defined as: a non-tick text whose box intrudes into a different axes' bbox.
    kids = {id(ch): ax for ax in fig.axes for ch in ax.child_axes}      # inset axes sit inside their parent: not "another panel"
    ticks = {id(t) for ax in (*fig.axes, *(c for a_ in fig.axes for c in a_.child_axes)) for t in (*ax.get_xticklabels(), *ax.get_yticklabels(), *ax.get_xticklabels(minor=True), *ax.get_yticklabels(minor=True))}
    axboxes = [(ax, ax.get_window_extent(renderer)) for ax in fig.axes if ax.get_subplotspec() is not None]
    clipped = []
    for t in fig.findobj(_mtext.Text):
        if id(t) in ticks or not t.get_visible() or not t.get_text().strip(): continue
        try: bb = t.get_window_extent(renderer)
        except Exception: continue
        owner = kids.get(id(t.axes), t.axes)
        for ax, ab in axboxes:
            if ax is owner: continue
            ix = min(bb.x1, ab.x1) - max(bb.x0, ab.x0); iy = min(bb.y1, ab.y1) - max(bb.y0, ab.y0)
            if ix > clip_tol_px and iy > clip_tol_px:
                clipped.append(t.get_text().strip().replace("\n", " ")[:24]); break
    if clipped: issues.append(("WARN", "text overlaps another panel's plotting area: " + str(list(dict.fromkeys(clipped))[:5])))
    def _overlap(labels, axis):
        bbs = [l.get_window_extent(renderer) for l in labels if l.get_visible() and l.get_text().strip()]
        bbs.sort(key=lambda b: b.x0 if axis == "x" else b.y0)
        for a_, b_ in zip(bbs, bbs[1:]):
            if axis == "x" and b_.x0 < a_.x1 - overlap_tol_px: return True
            if axis == "y" and b_.y0 < a_.y1 - overlap_tol_px: return True
        return False
    n_ov = sum(1 for ax in fig.axes if ax.get_subplotspec() is not None and (_overlap(ax.get_xticklabels(), "x") or _overlap(ax.get_yticklabels(), "y")))
    if n_ov: issues.append(("WARN", f"{n_ov} axes with overlapping tick labels: rotate x ticks, thin ticks, or widen the panel"))
    # an inset or annotation block must not sit on the plotted lines: share of the parent's line samples (resampled densely along x) under it
    over = []
    for ax in fig.axes:
        blocks = [("inset", ch.get_tightbbox(renderer)) for ch in ax.child_axes] + [("annotation", t.get_window_extent(renderer)) for t in ax.texts if t.get_gid() == "stat-annotation"]
        if not blocks: continue
        P = _line_samples(ax)
        for kind, bb in blocks:
            if len(P) and bb is not None:
                f = float(((P[:, 0] >= bb.x0) & (P[:, 0] <= bb.x1) & (P[:, 1] >= bb.y0) & (P[:, 1] <= bb.y1)).mean())
                if f > (0.10 if kind == "inset" else 0.04): over.append(f"{kind} {f:.0%}")      # a text block is small, so a few % of the samples already means it sits on a line
    if over: issues.append(("WARN", "inset/annotation covers plotted lines: " + ", ".join(over)))
    return issues

def finish(fig, a, src_rows, src_hdr, root, caption):
    out = os.path.join(root, a.out); os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    issues = audit_layout(fig)
    for sev, msg in issues: print(f"[{sev}] layout: {msg}")
    png = os.path.splitext(out)[0] + ".png"   # raster always .png (--out x.pdf used to crash PIL below)
    fig.savefig(png, dpi=400, bbox_inches="tight"); fig.savefig(os.path.splitext(out)[0] + ".pdf", bbox_inches="tight")
    if os.path.splitext(out)[1].lower() not in (".png", ".pdf"): fig.savefig(out, dpi=400, bbox_inches="tight")
    from PIL import Image
    Image.open(png).convert("L").save(os.path.splitext(out)[0] + "_gray.png")   # grayscale preview: the colour-vision / print-in-B&W check
    w = Image.open(png).size[0]; dpi = w / (a.width_mm / 25.4)
    sp = os.path.splitext(out)[0] + ".source.csv"
    with open(sp, "w", newline="", encoding="utf-8") as f: wr = csv.writer(f); wr.writerow(src_hdr); wr.writerows(src_rows)
    # figures.csv
    fp = os.path.join(root, "figures.csv"); rel = os.path.relpath(out, root).replace("\\", "/")
    rows = list(csv.DictReader(open(fp, encoding="utf-8-sig"))) if os.path.exists(fp) else []
    hdr = list(rows[0].keys()) if rows else ["file", "print_width_mm", "source_data", "inspected", "issues"]   # = templates/figures.csv
    # t2p.py init copies templates/figures.csv with a placeholder row (figures/fig1.png); a fresh project would FAIL G5 on a
    # figure that never existed. Drop rows whose file does not exist and was never inspected (= placeholders).
    rows = [r for r in rows if r.get("file") != rel and not (r.get("inspected", "no") != "yes" and not os.path.exists(os.path.join(root, r.get("file", ""))))]
    new = {h: "" for h in hdr}; new.update({"file": rel, "print_width_mm": str(a.width_mm), "inspected": "no"})
    for k in ("source_data", "source"):
        if k in hdr: new[k] = os.path.relpath(sp, root).replace("\\", "/")
    if "issues" in hdr: new["issues"] = "auto: " + caption + ("" if not issues else " | layout: " + "; ".join(f"{sv} {m}" for sv, m in issues))
    rows.append(new)
    with open(fp, "w", newline="", encoding="utf-8") as f: wr = csv.DictWriter(f, fieldnames=hdr); wr.writeheader(); wr.writerows(rows)
    print(f"{rel}: {w}px -> {dpi:.0f} dpi @ {a.width_mm} mm; source {os.path.basename(sp)}; grayscale {os.path.basename(os.path.splitext(out)[0])}_gray.png; layout audit {'clean' if not issues else str(len(issues)) + ' issue(s)'}; figures.csv updated (inspected=no → 裁图目测后改 yes)")
    if any(sv == "FAIL" for sv, _ in issues): sys.exit(1)


def _mark_best(src, metrics, a, res=None):
    """append a best flag per source row: lowest mean for lower-is-better metrics (--lower, else state.results
    metric_direction / primary_direction, else the name regex of metric_direction.py), highest otherwise"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import metric_direction as mdir
    lower = set(a.lower.split(",")) if getattr(a, "lower", "") else set()
    for mt in metrics:
        rows = [r for r in src if r[1] == mt]
        if not rows: continue
        pick = min(rows, key=lambda r: r[2]) if (mt in lower or mdir.lower_is_better(mt, res)) else max(rows, key=lambda r: r[2])
        for r in rows: r.append(r is pick)

def fig_main(a):
    root, res, main, abl, gk, ref, metrics, labels = load(a)
    data = by_method(main, gk, metrics); methods = [m for m in data if m != ref] + ([ref] if ref in data else [])
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, a.height_in)); x = np.arange(len(metrics)); w = 0.8 / len(methods); src = []
    for i, m in enumerate(methods):
        arr = data[m]; mean = np.nanmean(arr, 0); sd = np.nanstd(arr, 0, ddof=1) if arr.shape[0] > 1 else np.zeros(len(metrics))
        col = ACCENT if m == ref or m == a.ours else PALETTE[i % len(PALETTE)]
        xx = x + (i - (len(methods) - 1) / 2) * w
        ax.bar(xx, mean, w, color=col, label=f"{m} (n={arr.shape[0]})" if arr.shape[0] > 1 else m, edgecolor="none", zorder=3, yerr=sd if arr.shape[0] > 1 else None, error_kw=dict(elinewidth=0.6, capsize=1.5, ecolor="#333"))
        if arr.shape[0] > 1:
            for j in range(len(metrics)): ax.scatter(np.full(arr.shape[0], xx[j]), arr[:, j], s=4, color="#222", alpha=0.5, zorder=4, linewidths=0)
        for j, mt in enumerate(metrics): src.append([m, mt, mean[j], sd[j], arr.shape[0]])
    _mark_best(src, metrics, a, res)
    if a.logy: ax.set_yscale("log")
    ax.set_xticks(x); ax.set_xticklabels([labels.get(m, m) for m in metrics], fontsize=6.8); ax.set_ylabel(a.ylabel or res.get("primary_metric", "")); ax.grid(axis="y", lw=0.4, color="#e6e6e6", zorder=0)
    ax.legend(ncol=min(3, len(methods)), fontsize=6.3, loc="upper left", handlelength=1.0, columnspacing=0.8)
    finish(fig, a, src, ["method", "metric", "mean", "sd", "n", "best"], root, "Main comparison: mean ± s.d. over seeds where n>1; dots = individual seeds.")

def fig_ablation(a):
    root, res, main, abl, gk, ref, metrics, labels = load(a)
    if not abl: print("[FAIL] no ablation table"); sys.exit(1)
    refarr = by_method(main, gk, metrics).get(ref)
    if refarr is None or refarr.shape[0] < 2: print(f"[FAIL] reference {ref} needs ≥2 seeds in main.csv for the noise band"); sys.exit(1)
    ref_m = np.nanmean(refarr, 0); sig = np.nanstd(refarr, 0, ddof=1); n_ref = refarr.shape[0]
    # rows sharing an ablation label are per-seed runs (averaged, n = count); else n = n_seeds column or 1 (single run)
    order, groups = [], {}
    for r in abl:
        n = r.get("ablation") or r.get(gk)
        if n not in groups: order.append(n); groups[n] = []
        groups[n].append([float(r[m]) if r.get(m, "") != "" else np.nan for m in metrics])
    names = order; vals = np.array([np.nanmean(np.array(groups[n]), 0) for n in names]); ns = []
    for n in names:
        if len(groups[n]) > 1: ns.append(len(groups[n]))
        else:
            row = next(r for r in abl if (r.get("ablation") or r.get(gk)) == n)
            try: ns.append(max(1, int(float(row.get("n_seeds") or 1))))
            except ValueError: ns.append(1)
    bands = [2 * sig * (np.sqrt(2) if k <= 1 else np.sqrt(1.0 / k + 1.0 / n_ref)) for k in ns]
    single = all(k <= 1 for k in ns)
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, a.height_in)); x = np.arange(len(metrics)); w = 0.8 / len(names); src = []
    if single:
        ax.bar(x, 2 * bands[0], 0.86, bottom=-bands[0], color="#f0f0f0", edgecolor="none", zorder=0, label="±2σ_ref√2 seed noise")
    for i, n in enumerate(names):
        band = bands[i]; d = vals[i] - ref_m; resolv = np.abs(d) >= band
        xx = x + (i - (len(names) - 1) / 2) * w
        if not single:
            ax.bar(xx, 2 * band, w * 0.98, bottom=-band, color="#f0f0f0", edgecolor="none", zorder=0)
        ax.bar(xx, d, w, color=[ACCENT if r else "#c9c9c9" for r in resolv], edgecolor="none", zorder=3)
        for j in range(len(metrics)):
            ax.text(xx[j], -0.02, str(i + 1), ha="center", va="top", fontsize=5.2, color="#444", transform=ax.get_xaxis_transform(), clip_on=False)   # index row just below the axis
            src.append([n, metrics[j], d[j], band[j], bool(resolv[j]), ns[i]])
    ax.axhline(0, lw=0.6, color="#333"); ax.set_xticks(x); ax.set_xticklabels([labels.get(m, m) for m in metrics], fontsize=6.8)
    ax.set_ylabel(a.ylabel or f"Δ {labels.get(res.get('primary_metric',''), res.get('primary_metric',''))} vs. {ref}"); ax.tick_params(axis="x", pad=9); ax.text(0.01, 0.98, "\n".join(f"{i+1}: {n}" for i, n in enumerate(names)), transform=ax.transAxes, fontsize=5.6, va="top", color="#333")
    ax.text(0.99, 0.02, "grey bar: within seed noise\n(not resolvable" + (", single run)" if single else ")"), transform=ax.transAxes, fontsize=5.6, ha="right", va="bottom", color="#555")
    cap = (f"Ablation Δ vs. {ref}; grey band = ±2σ√2 seed noise of the reference (single runs); grey bars not resolvable." if single else
           f"Ablation Δ vs. {ref}; bars are means over n seeds per ablation ({', '.join(f'{nm}: n={k}' for nm, k in zip(names, ns))}), reference n={n_ref}; "
           f"grey band per bar = ±2σ_ref·√(1/n+1/n_ref) (±2σ√2 for single runs); grey bars not resolvable.")
    finish(fig, a, src, ["ablation", "metric", "delta", "band", "resolvable", "n_seeds"], root, cap)

def fig_seeds(a):
    root, res, main, abl, gk, ref, metrics, labels = load(a)
    data = by_method(main, gk, metrics); methods = [m for m in (a.methods.split(",") if a.methods else [ref]) if m in data]
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4 * 0.5, a.height_in)); x = np.arange(len(metrics)); src = []
    for i, m in enumerate(methods):
        arr = data[m]; mean = np.nanmean(arr, 0); sd = np.nanstd(arr, 0, ddof=1) if arr.shape[0] > 1 else np.zeros(len(metrics)); off = (i - (len(methods) - 1) / 2) * 0.3
        col = ACCENT if m == ref else PALETTE[3 + i % 3]
        ax.errorbar(x + off, mean, yerr=sd, fmt="o", ms=3, color=col, ecolor=col, elinewidth=0.8, capsize=2, label=f"{m} (n={arr.shape[0]})", zorder=3)
        for j in range(len(metrics)): ax.scatter(np.full(arr.shape[0], x[j] + off), arr[:, j], s=5, color=col, alpha=0.45, zorder=2, linewidths=0); src.append([m, metrics[j], mean[j], sd[j], arr.shape[0]])
    _mark_best(src, metrics, a, res)
    if a.logy: ax.set_yscale("log")
    ax.set_xticks(x); ax.set_xticklabels([labels.get(m, m) for m in metrics], fontsize=6.8); ax.set_ylabel(a.ylabel or f"{res.get('primary_metric','')}, mean ± s.d."); ax.grid(axis="y", lw=0.4, color="#e6e6e6", zorder=0); ax.legend(fontsize=6.3, loc="upper left", handlelength=1.0)
    a.width_mm = a.width_mm * 0.5
    finish(fig, a, src, ["method", "metric", "mean", "sd", "n", "best"], root, "Seed stability: mean ± s.d., dots = seeds.")


OFFS8 = [((4, 3), "left", "bottom"), ((4, -3), "left", "top"), ((-4, 3), "right", "bottom"), ((-4, -3), "right", "top"),
         ((0, 6), "center", "bottom"), ((0, -6), "center", "top"), ((7, 0), "left", "center"), ((-7, 0), "right", "center")]

def marker_bbox(fig, ax, x, y, s, lw_pt=0.5):
    """display-space Bbox of a scatter marker of area s (pt^2) at data point (x, y): the square around its circle (diameter sqrt(s) pt)"""
    from matplotlib.transforms import Bbox
    cx, cy = ax.transData.transform((x, y)); r = (np.sqrt(s) / 2 + lw_pt) * fig.dpi / 72
    return Bbox([[cx - r, cy - r], [cx + r, cy + r]])

def place_labels(fig, ax, items, offsets=OFFS8, fontsize=5.8, obstacles=(), pad_px=1.0, markers=()):
    """text labels without label-on-label overlap, greedy in priority order. items = (x, y, text, colour, bold[, offsets[, own]]) in data
    coordinates of `ax`; every item tries its offsets (8 around the point by default) and keeps the first whose box stays inside
    the axes and hits neither an earlier label, an `obstacles` box (display px) nor a marker. `markers` = [(x, y, area_pt2), ...]
    in data coordinates: a candidate that touches any marker other than the item's own (`own` = index into `markers`; default: the
    marker at the item's own x, y) is rejected. If no offset fits the label is dropped.
    Returns one entry per item, in order: the display-space Bbox of the placed label, or None when dropped."""
    fig.canvas.draw(); rend = fig.canvas.get_renderer(); box = ax.get_window_extent(rend); taken = list(obstacles); out = []
    mk = [marker_bbox(fig, ax, mx, my, ms) for mx, my, ms in markers]
    def hit(a_, b_, pad=pad_px): return a_.x0 < b_.x1 + pad and b_.x0 < a_.x1 + pad and a_.y0 < b_.y1 + pad and b_.y0 < a_.y1 + pad
    for it in items:
        x, y, txt, c, bold = it[:5]; offs = it[5] if len(it) > 5 and it[5] else offsets; got = None
        own = it[6] if len(it) > 6 and it[6] is not None else next((k for k, m in enumerate(markers) if m[0] == x and m[1] == y), None)
        others = [b for k, b in enumerate(mk) if k != own]
        for (dx, dy), ha, va in offs:
            t = ax.annotate(txt, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=fontsize, color=c, fontweight="bold" if bold else "normal", zorder=7, annotation_clip=False)
            bb = t.get_window_extent(rend)
            if box.x0 <= bb.x0 and bb.x1 <= box.x1 and box.y0 <= bb.y0 and bb.y1 <= box.y1 and not any(hit(bb, p) for p in taken) and not any(hit(bb, m, 0.0) for m in others):
                taken.append(bb); got = bb; break
            t.remove()
        out.append(got)
    return out

def ema(values, alpha):
    """exponential moving average, s_0 = x_0, s_t = alpha * x_t + (1 - alpha) * s_(t-1); alpha = 1 returns the input, small alpha = heavy smoothing"""
    if not 0 < alpha <= 1: raise ValueError(f"EMA alpha must be in (0, 1], got {alpha}")
    out = []; s = None
    for v in values:
        s = float(v) if s is None else alpha * float(v) + (1 - alpha) * s; out.append(s)
    return np.array(out)

def _csv_rows(root, rel, need):
    path = os.path.join(root, rel)
    if not os.path.exists(path): print(f"[FAIL] {rel} does not exist"); sys.exit(1)
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if not rows: print(f"[FAIL] {rel} is empty"); sys.exit(1)
    for c in need:
        if c and c not in rows[0]: print(f"[FAIL] column {c} not in {rel}: {list(rows[0])}"); sys.exit(1)
    return rows

def _fx(v): return f"{v:g}"


def _line_samples(ax, n=200):
    """every visible Line2D of `ax`, resampled densely along x, in display pixels (N x 2): what 'plotted data' means for occupancy checks"""
    out = []
    for ln in ax.lines:
        try: xy = np.asarray(ln.get_xydata(), float)
        except Exception: continue
        if not ln.get_visible() or len(xy) < 2: continue
        xy = xy[np.isfinite(xy).all(axis=1)]
        if len(xy) < 2: continue
        d = ax.transData.transform(xy); d = d[np.argsort(d[:, 0])]
        if d[-1, 0] - d[0, 0] < 1e-9: out.append(d); continue
        gx = np.linspace(d[0, 0], d[-1, 0], n); out.append(np.column_stack([gx, np.interp(gx, d[:, 0], d[:, 1])]))
    return np.vstack(out) if out else np.zeros((0, 2))

def _place_blocks(fig, ax, cur, styles, inset, text):
    """inset zoom and annotation text, each in the corner of the panel where the fewest plotted samples (all series, raw and smoothed)
    would be covered. The inset (with its tick labels) and the text must not share a row unless stacked on one side. If even the best
    inset covers > 25 % of the samples it is shrunk to 30 % width; if it still does, return a warning string."""
    rend = fig.canvas.get_renderer(); axbb = ax.get_window_extent(rend); P = _line_samples(ax)
    P = np.column_stack([(P[:, 0] - axbb.x0) / axbb.width, (P[:, 1] - axbb.y0) / axbb.height]) if len(P) else np.zeros((0, 2))
    def frac(rects):
        if not len(P) or not rects: return 0.0
        m = np.zeros(len(P), bool)
        for x0, y0, x1, y1 in rects: m |= (P[:, 0] >= x0) & (P[:, 0] <= x1) & (P[:, 1] >= y0) & (P[:, 1] <= y1)
        return float(m.mean())
    corners = [(True, False), (True, True), (False, False), (False, True)]       # (right, upper): lower right first
    tw = th = 0.0; tt = None
    if text:
        tt = ax.text(0.5, 0.5, text, transform=ax.transAxes, fontsize=5.6, ha="right", va="bottom", color="#333", linespacing=1.25, zorder=7, gid="stat-annotation")
        bb = tt.get_window_extent(rend); tw, th = bb.width / axbb.width, bb.height / axbb.height
    def tbox(c):
        right, up = c; x1 = 0.97 if right else 0.03 + tw; y0 = 0.97 - th if up else 0.03
        return (x1 - tw - 0.01, y0 - 0.01, x1 + 0.01, y0 + th + 0.01), (x1, 0.97 if up else 0.03)
    def ibox(c, w, h, stack):
        right, up = c; x0 = 0.97 - w if right else 0.14
        if stack: y0 = 0.97 - th - 0.03 - h if up else 0.03 + th + 0.03 + 0.10
        else: y0 = 0.97 - h if up else 0.12
        return (x0, y0, w, h), (x0 - 0.11, y0 - 0.10, x0 + w, y0 + h)
    def options(w, h):
        opts = []
        if inset and text:
            for tc in corners:
                for ic, stack in ([(tc, True)] + [((r, not tc[1]), False) for r in (True, False)]):
                    ib, irect = ibox(ic, w, h, stack); tr, _ = tbox(tc); opts.append((frac([irect, tr]), frac([irect]), ib, tc))
        elif inset:
            for ic in corners: ib, irect = ibox(ic, w, h, False); opts.append((frac([irect]), frac([irect]), ib, None))
        else:
            for tc in corners: tr, _ = tbox(tc); opts.append((frac([tr]), 0.0, None, tc))
        return min(opts, key=lambda o: o[0])
    best = options(0.50, 0.30); warn = None
    if inset and best[1] > 0.25:
        best = options(0.30, 0.30)
        if best[1] > 0.25: warn = f"inset overlaps data ({best[1]:.0%} of the plotted samples lie under it)"
    if tt is not None:
        right, up = best[3]; tt.set_position((0.97 if right else 0.03, 0.97 if up else 0.03)); tt.set_ha("right" if right else "left"); tt.set_va("top" if up else "bottom")
    if inset:
        x0, x1, ylo, yhi = inset; ins = ax.inset_axes(list(best[2])); ins.set_zorder(8)
        for sname, c in cur.items():
            m = (c["xs"] >= x0) & (c["xs"] <= x1); st = styles[sname]; ins.plot(c["xs"][m], c["sm"][m], lw=0.9, color=st["color"], ls=st["ls"])
        ins.set_xlim(x0, x1); ins.set_ylim(ylo, yhi); ins.set_xticks([x0, x1]); ins.set_xticklabels([_fx(x0), _fx(x1)])
        ins.yaxis.set_major_locator(plt.MaxNLocator(2)); ins.tick_params(labelsize=5, length=1.5, width=0.4, pad=1)
        for sp_ in ins.spines.values(): sp_.set_visible(True); sp_.set_linewidth(0.5); sp_.set_color("#555")
        ax.add_patch(plt.Rectangle((x0, ylo), x1 - x0, yhi - ylo, fill=False, ec="#555", lw=0.6, zorder=6))
    return warn


def fig_curves(a):
    """long CSV -> one line per series, seeds averaged with a band, optional small-multiple panels (+ Fig-6 options: EMA, inset, annotation)."""
    root = os.path.abspath(a.project); rows = _csv_rows(root, a.csv, [a.x, a.y])
    labels = dict(kv.split("=", 1) for kv in a.labels.split(",") if "=" in kv) if a.labels else {}
    panels = sorted({r[a.panel] for r in rows}, key=str) if a.panel and a.panel in rows[0] else [None]
    series_all = []
    for r in rows:
        sname = r.get(a.series, "") if a.series else ""
        if sname not in series_all: series_all.append(sname)
    new = a.ema > 0 or bool(a.inset) or bool(a.annotate)
    if a.ema and not 0 < a.ema <= 1: print("[FAIL] --ema must be in (0, 1]"); sys.exit(1)
    paired = bool(a.ours and (a.baseline or a.annotate)); base = ""
    if a.annotate and not a.ours: print("[FAIL] --annotate needs --ours <series>"); sys.exit(1)
    if a.ours and a.ours not in series_all and (paired or a.annotate): print(f"[FAIL] --ours {a.ours} not in series: {series_all}"); sys.exit(1)
    if paired:
        base = a.baseline or next((s_ for s_ in series_all if s_ != a.ours), "")
        if base not in series_all or base == a.ours: print(f"[FAIL] baseline {base!r} must be a series other than ours: {series_all}"); sys.exit(1)
    legend = a.legend or ("above" if new else "best")
    ncols = a.ncols or len(panels); nrows = -(-len(panels) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(a.width_mm / 25.4, a.height_in), sharey=(not a.logy and not a.free_y), squeeze=False); src = []; notes = []; summ = []; blocks = []
    flat = [ax for r_ in axes for ax in r_]
    for ax in flat[len(panels):]: ax.set_visible(False)
    styles = {}
    for i, sname in enumerate(series_all):
        if sname and sname == a.ours: styles[sname] = dict(color=ACCENT, ls="-", lw=1.1)
        elif paired and sname == base: styles[sname] = dict(color="#7d838b", ls="--", lw=1.0)
        else: styles[sname] = dict(color=PALETTE[(2 + i) % len(PALETTE)], ls="-", lw=1.1 if not paired else 0.9)
    n_by = {}
    for pi, (ax, pn) in enumerate(zip(flat, panels)):
        cur = collections.OrderedDict()
        for i, sname in enumerate(series_all):
            sub = [r for r in rows if (not a.series or r.get(a.series, "") == sname) and (pn is None or r[a.panel] == pn)]
            pts = collections.defaultdict(list)
            for r in sub:
                try: pts[float(r[a.x])].append(float(r[a.y]))
                except ValueError: continue
            if not pts: continue
            xs = np.array(sorted(pts)); ys = np.array([np.mean(pts[x]) for x in xs]); n = max(len(pts[x]) for x in xs); n_by[sname] = max(n, n_by.get(sname, 0))
            sd = np.array([np.std(pts[x], ddof=1) if len(pts[x]) > 1 else 0.0 for x in xs])
            lo = np.array([np.min(pts[x]) if a.band == "minmax" else m - s_ for x, m, s_ in zip(xs, ys, sd)]); hi = np.array([np.max(pts[x]) if a.band == "minmax" else m + s_ for x, m, s_ in zip(xs, ys, sd)])
            sm, lo_s, hi_s = (ema(ys, a.ema), ema(lo, a.ema), ema(hi, a.ema)) if a.ema else (ys, lo, hi)
            cur[sname] = dict(xs=xs, ys=ys, sm=sm, n=n)
            st = styles[sname]; ln = (labels.get(sname, sname) + (f" (n={n})" if n > 1 else "")) if sname else None
            if a.ema: ax.plot(xs, ys, lw=0.5, color=st["color"], alpha=0.25, zorder=2)
            ax.plot(xs, sm, lw=st["lw"], color=st["color"], ls=st["ls"], label=ln if legend == "best" else None, zorder=3)
            if n > 1 and a.band != "none": ax.fill_between(xs, lo_s, hi_s, color=st["color"], alpha=0.18, lw=0, zorder=2)
            for x, y, y2 in zip(xs, ys, sm):
                row = [pn if pn is not None else "", sname, x, y, np.std(pts[x], ddof=1) if len(pts[x]) > 1 else 0.0, len(pts[x])]
                src.append(row + ([float(y2), "point", "", "", ""] if new else []))
        if a.logx: ax.set_xscale("log")
        if a.logy: ax.set_yscale("log")
        ax.set_xlabel(a.xlabel or labels.get(a.x, a.x), fontsize=6.8); ax.grid(axis="y", lw=0.4, color="#e6e6e6", zorder=0)
        if pn is not None:
            ttl = labels.get(pn, pn)
            if a.letters: ax.set_title(f"({chr(97 + pi)}) {ttl}", fontsize=7.2, loc="left", fontweight="bold")
            else: ax.set_title(ttl, fontsize=7.2)
        if pi % ncols == 0: ax.set_ylabel(a.ylabel or labels.get(a.y, a.y))
        if not cur: continue
        ann = bool(a.annotate and a.ours in cur and base in cur); inset = None; text = None
        if a.annotate and not ann: notes.append(f"panel {pn}: ours or baseline has no data, no annotation")
        if a.inset:
            allx = sorted({x for c in cur.values() for x in c["xs"]})
            try:
                if a.inset.startswith("last:"): k = max(2, int(a.inset[5:])); x0, x1 = (allx[-k] if len(allx) >= k else allx[0]), allx[-1]
                else: x0, x1 = (float(t) for t in a.inset.split(":"))
            except ValueError: print(f"[FAIL] --inset must be last:N or x0:x1, got {a.inset!r}"); sys.exit(1)
            vals = np.concatenate([c["sm"][(c["xs"] >= x0) & (c["xs"] <= x1)] for c in cur.values()])
            if len(vals) >= 2 and x1 > x0:
                ylo, yhi = float(vals.min()), float(vals.max()); pad = 0.18 * (yhi - ylo or 1.0); inset = (x0, x1, ylo - pad, yhi + pad)
            else: notes.append(f"panel {pn}: inset range {x0:g}–{x1:g} holds fewer than 2 points, no inset")
        if ann:
            co, cb = cur[a.ours], cur[base]; common = sorted(set(co["xs"]) & set(cb["xs"]))
            if not common: notes.append(f"panel {pn}: ours and baseline share no x, no annotation")
            else:
                xc = common[-1]; vo = float(co["sm"][list(co["xs"]).index(xc)]); vb = float(cb["sm"][list(cb["xs"]).index(xc)]); d = vo - vb
                ax.scatter([xc], [vo], s=16, color=ACCENT, edgecolors="white", linewidths=0.4, zorder=6, clip_on=False)
                ax.scatter([xc], [vb], s=16, facecolors="white", edgecolors="#555", linewidths=0.8, zorder=6, clip_on=False)
                unit = f" {a.delta_unit}" if a.delta_unit else ""; yl = labels.get(a.y, a.y)
                text = f"Δ{yl}{' (EMA)' if a.ema else ''} @ {a.x} {_fx(xc)}: " + f"{d:+.2f}".replace("-", "−") + f"{unit}\n{labels.get(a.ours, a.ours)} {vo:.2f} | {labels.get(base, base)} {vb:.2f}"
                src.append([pn if pn is not None else "", f"{a.ours} vs {base}", xc, "", "", "", "", "summary", vo, vb, d]); summ.append((pn, xc, vo, vb, d))
        if inset or text: blocks.append((ax, pn, cur, styles, inset, text))
    if legend == "above" and a.series:
        from matplotlib.lines import Line2D
        hs = [Line2D([], [], color=styles[s_]["color"], ls=styles[s_]["ls"], lw=styles[s_]["lw"]) for s_ in series_all]
        ls_ = [labels.get(s_, s_) + (f" (n={n_by[s_]})" if n_by.get(s_, 0) > 1 else "") for s_ in series_all]
        if a.ema: hs.append(Line2D([], [], color="#9a9a9a", lw=0.5, alpha=0.5)); ls_.append("Raw records (faint)")
        fig.legend(hs, ls_, loc="upper center", ncol=min(len(hs), 6), fontsize=6.3, handlelength=1.6, bbox_to_anchor=(0.5, 1.0))
        fig.tight_layout(pad=0.3, rect=(0, 0, 1, 0.94))
    else:
        if legend == "best" and a.series: flat[len(panels) - 1].legend(fontsize=6.3, loc="best", handlelength=1.2)
        fig.tight_layout(pad=0.3)
    if blocks:
        fig.canvas.draw()
        for ax, pn, cur, styles_, inset, text in blocks:
            w_ = _place_blocks(fig, ax, cur, styles_, inset, text)
            if w_: notes.append(f"panel {pn}: {w_}")
    for n_ in notes: print(f"[WARN] curves: {n_}")
    for pn, xc, vo, vb, d in summ: print(f"annotated {pn if pn is not None else 'panel'}: Δ{a.y} @ {a.x} {_fx(xc)} = {d:+.2f} ({a.ours} {vo:.2f}, {base} {vb:.2f})")
    band_txt = {"sd": "shaded band = ± s.d. over seeds", "minmax": "shaded band = min–max over seeds", "none": "single run per series"}[a.band]
    cap = f"Curves of {a.y} vs. {a.x}; {band_txt}"
    if a.ema: cap += f"; solid lines = EMA smoothing (α = {a.ema:g}) of the seed mean, faint lines = raw records"
    if a.inset: cap += f"; inset and grey rectangle zoom on {a.inset}"
    if a.annotate: cap += f"; circles mark the last {a.x} both series share, Δ = {a.ours} − {base} read from the {'smoothed ' if a.ema else ''}curves"
    hdr = ["panel", "series", a.x, f"{a.y}_mean", f"{a.y}_sd", "n"] + ([f"{a.y}_smooth", "kind", "ours", "baseline", "delta"] if new else [])
    finish(fig, a, src, hdr, root, cap + ".")


def _stats_group(rows, gcol, vcol):
    vals = collections.OrderedDict()
    for r in rows:
        try: v = float(r[vcol])
        except ValueError: continue
        vals.setdefault(r[gcol], []).append(v)
    if not vals: print(f"[FAIL] column {vcol} holds no numbers"); sys.exit(1)
    return vals

def fig_stems(a):
    """paired baseline (x) vs ours (y) per item: y = x diagonal, stems from the diagonal, gain labels."""
    root = os.path.abspath(a.project); labels = dict(kv.split("=", 1) for kv in a.labels.split(",") if "=" in kv) if a.labels else {}
    rows = _csv_rows(root, a.csv, [a.item, a.x, a.y, a.group])
    items = collections.OrderedDict()
    for r in rows:
        try: items.setdefault(r[a.item], []).append((float(r[a.x]), float(r[a.y]), r[a.group] if a.group else r[a.item]))
        except ValueError: continue
    if not items: print(f"[FAIL] no numeric rows in {a.csv}"); sys.exit(1)
    names = list(items); X = np.array([np.mean([p[0] for p in items[k]]) for k in names]); Y = np.array([np.mean([p[1] for p in items[k]]) for k in names]); G = [items[k][0][2] for k in names]
    gain = Y - X; groups = list(dict.fromkeys(G))
    if len(groups) > len(CAT): print(f"[WARN] stems: {len(groups)} groups, colours repeat after {len(CAT)}")
    cm = {g: CAT[i % len(CAT)] for i, g in enumerate(groups)}; mk = {g: MARKS[i % len(MARKS)] for i, g in enumerate(groups)}
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, a.height_in)); fig.subplots_adjust(left=0.14, right=0.97, bottom=0.17, top=0.96)
    xs_ = max(X.max() - X.min(), 1e-9); lo = min(X.min(), Y.min()); hi = max(X.max(), Y.max()); ys_ = max(hi - lo, 1e-9)
    ax.set_xlim(X.min() - 0.08 * xs_ - 0.02 * ys_, X.max() + 0.08 * xs_ + 0.02 * ys_); ax.set_ylim(lo - 0.06 * ys_, hi + 0.16 * ys_)
    ax.axline((lo, lo), slope=1, ls="--", lw=0.7, color="#8a8a8a", zorder=1, label="y = x")
    ax.vlines(X, X, Y, colors=[cm[g] for g in G], lw=0.8, zorder=2)
    for g in groups:
        m = [i for i, gg in enumerate(G) if gg == g]; ax.scatter(X[m], Y[m], s=22, marker=mk[g], color=cm[g], edgecolors="white", linewidths=0.4, zorder=4, label=labels.get(g, g))
    up = [((0, 4), "center", "bottom"), ((0, 10), "center", "bottom"), ((-7, 6), "right", "bottom"), ((7, 6), "left", "bottom"), ((0, 16), "center", "bottom"), ((-7, 13), "right", "bottom"), ((7, 13), "left", "bottom")]
    dn = [((0, -4), "center", "top"), ((0, -10), "center", "top"), ((-7, -6), "right", "top"), ((7, -6), "left", "top"), ((0, -16), "center", "top")]
    placed = place_labels(fig, ax, [(x, y, f"{d:+.2f}".replace("-", "−"), cm[g], False, up if d >= 0 else dn) for x, y, d, g in zip(X, Y, gain, G)], fontsize=5.8)
    dropped = [k for k, p in zip(names, placed) if p is None]
    if dropped: print(f"[WARN] stems: gain label dropped (no free spot): {dropped}; the value is in the source CSV")
    n_up = int((gain > 0).sum()); n = len(names)
    ax.set_xlabel(a.xlabel or labels.get(a.x, a.x)); ax.set_ylabel(a.ylabel or labels.get(a.y, a.y)); ax.grid(lw=0.4, color="#ececec", zorder=0)
    ax.legend(fontsize=5.8, loc="lower right" if n_up * 2 >= n else "upper left", handlelength=1.2, labelspacing=0.3, ncol=1 if len(groups) <= 6 else 2)
    print(f"{n_up}/{n} {a.item}s above y = x (gain {gain.min():+.2f} to {gain.max():+.2f}, mean {gain.mean():+.2f})")
    src = [[k, g, x, y, d, bool(d > 0), p is not None] for k, g, x, y, d, p in zip(names, G, X, Y, gain, placed)]
    finish(fig, a, src, [a.item, a.group or "group", a.x, a.y, "gain", "above_diagonal", "label_placed"], root,
           f"{labels.get(a.y, a.y)} vs. {labels.get(a.x, a.x)} for {n} {a.item}s; dashed = y = x, stems = gain ({n_up}/{n} above the diagonal, mean {gain.mean():+.2f}).")

def fig_box(a):
    """horizontal box per group; whiskers at percentiles"""
    root = os.path.abspath(a.project); labels = dict(kv.split("=", 1) for kv in a.labels.split(",") if "=" in kv) if a.labels else {}
    rows = _csv_rows(root, a.csv, [a.value, a.group]); vals = _stats_group(rows, a.group, a.value)
    try: wl, wh = (float(t) for t in a.whis.split(","))
    except ValueError: print("[FAIL] --whis wants two percentiles, e.g. 5,95"); sys.exit(1)
    names = list(vals); st = []
    for g in names:
        v = np.array(vals[g]); st.append((len(v), *np.percentile(v, [wl, 25, 50, 75, wh])))
    h = a.height_in or max(1.3, 0.3 * len(names) + 0.75)
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, h)); fig.subplots_adjust(left=0.2, right=0.96, bottom=0.8 / h, top=0.97)
    for i, (n, lo, q1, md, q3, hi) in enumerate(st):
        ax.add_patch(plt.Rectangle((q1, i - 0.3), q3 - q1, 0.6, fc="#7fa7c9", ec="#2b4c6f", lw=0.6, zorder=3))
        ax.plot([md, md], [i - 0.3, i + 0.3], color=ACCENT, lw=1.2, zorder=4, solid_capstyle="butt")
        ax.plot([lo, q1], [i, i], color="#2b4c6f", lw=0.6, zorder=2); ax.plot([q3, hi], [i, i], color="#2b4c6f", lw=0.6, zorder=2)
        for e in (lo, hi): ax.plot([e, e], [i - 0.14, i + 0.14], color="#2b4c6f", lw=0.6, zorder=2)
    few = [g for g, s_ in zip(names, st) if s_[0] < 5]
    if few: print(f"[WARN] box: {few} have fewer than 5 values; quartiles and percentile whiskers are not meaningful there")
    if a.vline is not None: ax.axvline(a.vline, ls="--", lw=0.6, color="#8a8a8a", zorder=1)
    allv = [s_[1] for s_ in st] + [s_[5] for s_ in st] + ([a.vline] if a.vline is not None else []); pad = 0.05 * (max(allv) - min(allv) or 1.0)
    ax.set_xlim(min(allv) - pad, max(allv) + pad); ax.set_ylim(len(names) - 0.5, -0.5); ax.set_yticks(range(len(names))); ax.set_yticklabels([labels.get(g, g) for g in names])
    ax.set_xlabel(a.xlabel or labels.get(a.value, a.value)); ax.grid(axis="x", lw=0.4, color="#ececec", zorder=0); ax.tick_params(axis="y", length=0)
    if a.ylabel: ax.set_ylabel(a.ylabel)
    src = [[g, *s_] for g, s_ in zip(names, st)]
    finish(fig, a, src, [a.group, "n", f"whisker_lo_p{wl:g}", "q1", "median", "q3", f"whisker_hi_p{wh:g}"], root,
           f"{labels.get(a.value, a.value)} per {a.group}: boxes = interquartile range, line = median, whiskers = {wl:g}th–{wh:g}th percentiles.")

def fig_hbar(a):
    """horizontal bars with the value at the bar end; negative values extend left of the zero line"""
    root = os.path.abspath(a.project); labels = dict(kv.split("=", 1) for kv in a.labels.split(",") if "=" in kv) if a.labels else {}
    rows = _csv_rows(root, a.csv, [a.value, a.group]); vals = _stats_group(rows, a.group, a.value)
    names = list(vals); m = np.array([np.mean(vals[g]) for g in names]); ns = [len(vals[g]) for g in names]
    h = a.height_in or max(1.3, 0.3 * len(names) + 0.75)
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, h)); fig.subplots_adjust(left=0.2, right=0.96, bottom=0.8 / h, top=0.97)
    ax.barh(range(len(names)), m, height=0.62, color=PALETTE[3], edgecolor="none", zorder=3)
    lo, hi = min(0.0, m.min()), max(0.0, m.max()); span = (hi - lo) or 1.0
    for i, v in enumerate(m): ax.text(v + (0.015 * span if v >= 0 else -0.015 * span), i, a.fmt.format(v).replace("-", "−"), ha="left" if v >= 0 else "right", va="center", fontsize=6.3, color="#222", zorder=5)
    ax.set_xlim(lo - (0.24 * span if m.min() < 0 else 0.02 * span), hi + (0.24 * span if m.max() > 0 else 0.02 * span))
    ax.axvline(0, lw=0.7, color="#333", zorder=4); ax.set_ylim(len(names) - 0.5, -0.5); ax.set_yticks(range(len(names))); ax.set_yticklabels([labels.get(g, g) for g in names]); ax.tick_params(axis="y", length=0)
    ax.set_xlabel(a.xlabel or labels.get(a.value, a.value)); ax.grid(axis="x", lw=0.4, color="#ececec", zorder=0)
    if a.ylabel: ax.set_ylabel(a.ylabel)
    best = int(np.argmin(m) if a.lower else np.argmax(m))
    src = [[g, v, n, i == best] for i, (g, v, n) in enumerate(zip(names, m, ns))]
    finish(fig, a, src, [a.group, a.value, "n", "best"], root, f"{labels.get(a.value, a.value)} per {a.group}" + (" (mean over rows per group)" if max(ns) > 1 else "") + "; bars left of the zero line are negative.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("main", "ablation", "seeds", "curves"):
        p = sub.add_parser(n); p.add_argument("--project", default="."); p.add_argument("--out", required=True); p.add_argument("--metrics", default=""); p.add_argument("--labels", default="")
        p.add_argument("--width-mm", type=float, default=183); p.add_argument("--height-in", type=float, default=2.6); p.add_argument("--logy", action="store_true"); p.add_argument("--ylabel", default=""); p.add_argument("--ours", default="")
        p.add_argument("--lower", default="", help="metrics where lower is better (comma list); default all higher")
        if n == "seeds": p.add_argument("--methods", default="")
        if n == "curves":
            p.add_argument("--csv", required=True, help="long CSV with one row per point"); p.add_argument("--x", required=True); p.add_argument("--y", required=True)
            p.add_argument("--series", default="", help="column naming the line (method); empty = one line"); p.add_argument("--seed", default="seed")
            p.add_argument("--panel", default="", help="column -> one panel per distinct value"); p.add_argument("--xlabel", default="")
            p.add_argument("--band", choices=["sd", "minmax", "none"], default="sd"); p.add_argument("--logx", action="store_true")
            p.add_argument("--ema", type=float, default=0.0, help="EMA weight on the new value (0.12 = heavy smoothing); smoothed line solid, raw records faint behind it")
            p.add_argument("--inset", default="", help="'last:40' (last 40 points of the panel) or 'x0:x1': zoom inset + grey rectangle on each panel")
            p.add_argument("--annotate", choices=["", "last"], default="", help="'last': markers + Δ text at the last x shared by --ours and the baseline")
            p.add_argument("--baseline", default="", help="baseline series, drawn dashed grey (default with --ours/--annotate: first series that is not ours)")
            p.add_argument("--ncols", type=int, default=0, help="panels per row (default: all in one row)"); p.add_argument("--free-y", action="store_true", help="every panel its own y range")
            p.add_argument("--letters", action="store_true", help="panel titles '(a) name'"); p.add_argument("--legend", choices=["", "best", "above", "none"], default="", help="default: above when --ema/--inset/--annotate is given, else best")
            p.add_argument("--delta-unit", default="", help="unit written after Δ in the annotation (pp)")
    for n, w in (("stems", 88), ("box", 88), ("hbar", 88)):
        p = sub.add_parser(n); p.add_argument("--project", default="."); p.add_argument("--out", required=True); p.add_argument("--labels", default=""); p.add_argument("--csv", required=True)
        p.add_argument("--width-mm", type=float, default=w); p.add_argument("--height-in", type=float, default=2.8 if n == "stems" else 0.0, help="box / hbar: default grows with the number of groups")
        p.add_argument("--xlabel", default=""); p.add_argument("--ylabel", default="")
        if n == "stems":
            p.add_argument("--item", required=True, help="column naming the item (backbone)"); p.add_argument("--x", required=True, help="baseline value column"); p.add_argument("--y", required=True, help="ours value column")
            p.add_argument("--group", default="", help="column for colour + marker (family); default: one colour per item")
        else:
            p.add_argument("--value", required=True); p.add_argument("--group", required=True)
        if n == "box": p.add_argument("--whis", default="5,95", help="whisker percentiles"); p.add_argument("--vline", type=float, default=None, help="dashed reference line (0.5 for AUROC)")
        if n == "hbar": p.add_argument("--lower", action="store_true", help="lower is better (only changes which group is flagged best in the source CSV)"); p.add_argument("--fmt", default="{:+.2f}", help="value label format")
    a = ap.parse_args(); {"main": fig_main, "ablation": fig_ablation, "seeds": fig_seeds, "curves": fig_curves, "stems": fig_stems, "box": fig_box, "hbar": fig_hbar}[a.cmd](a)

if __name__ == "__main__":
    main()
