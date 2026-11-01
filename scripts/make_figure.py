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
      Fig-6-style training curves: [--ema 0.12] EMA-smoothed solid line over one neutral light-grey raw line (s_0 = x_0, s_t = a*x_t + (1-a)*s_t-1,
      per series per panel, on the seed mean). EMA is DRAWING ONLY and needs >= 20 points per series: with fewer it is not applied (WARN; raw seed
      means with markers), because 10 points never catch up with the data; [--inset last:40 | x0:x1] zoom as an inset with connector lines to the
      grey rectangle (refused when it spans >= half of the series; placed in the corner with the fewest plotted samples; ticks >= 3, house font size);
      [--annotate last --ours ours [--baseline base] [--delta-unit pp]] filled / open circle at the last x both series share, direct end labels
      "ours 37.68" / "base 36.88" and "Δ +0.80". These numbers are the RAW seed means at that x (the caption and the source CSV's kind=summary row,
      column basis, say so). Palette: ours accent red, thick; baseline dark grey dashed, thin; the rest distinct hues with distinct markers;
      [--ncols 3] [--free-y] [--letters] [--legend auto|above|best|none] (auto = inside the axes when a corner is free, else one row above; n of the
      seeds goes to the caption, not the legend). All text in the figure is one size (the house 7.5 pt). Without --ema / --inset / --annotate the
      source columns are unchanged.
      --width-mm defaults to the target venue's text / column width (state.target.venue -> references/latex-templates.csv; CVPR 174.6 / 82.5 mm),
      else 183 / 88 mm; figures.csv registers the width of the saved PDF (bbox-tight adds label margins) so G5 measures print sizes on the real page.
  python make_figure.py stems    --csv results/backbones.csv --item backbone --x baseline_AP --y ours_AP [--group family] --out figures/fig_stems.png
      paired baseline (x) vs ours (y) per item: dashed y = x, one stem from the diagonal to each point, gain label "+d" on top, colour
      by --group (without --group: one colour + marker per item); prints "k/n <item>s above y = x"
  python make_figure.py box      --csv results/auroc.csv --value auroc --group dataset [--whis 5,95] [--vline 0.5] --out figures/fig_box.png
      horizontal box per group (box = quartiles, line = median, whiskers = the given percentiles); source CSV holds the five numbers
  python make_figure.py hbar     --csv results/drop.csv --value dAP --group dataset [--lower] [--fmt "{:+.2f}"] --out figures/fig_hbar.png
      horizontal bars, value printed at the bar end, negative bars extend left of the zero line (rows of one group are averaged)

  python make_figure.py roc      --csv results/preds.csv --y-true label --score score [--group method] [--ours ours] [--ci bootstrap:200] [--seed 0] --out figures/fig_roc.png
      one ROC curve per group + chance diagonal, AUC in the legend; --ci = stratified bootstrap 95 % band, AUC [lo, hi] in legend and source CSV
      (curve points + one summary row per group: auc, ci_lo, ci_hi, n_pos, n_neg); FAIL when a group has one class, WARN when n_pos or n_neg < 10
  python make_figure.py pr       (same inputs)  precision-recall curves, prevalence line, average precision (step-wise area) in the legend, same --ci
  python make_figure.py confusion --csv results/pred.csv --true-col y --pred-col p [--labels a,b,c] [--normalize true|none] | --matrix  (square table CSV)
      heatmap, count + row-normalised % in each cell (n <= 8; counts only up to 12 classes), per-class recall / precision / support rows in the source CSV
  python make_figure.py calibration --csv results/preds.csv --y-true label --prob prob [--group method] [--bins 10] [--strategy quantile|uniform]
      reliability diagram (marker area ~ bin count, hollow = fewer than 5 samples) + prediction histogram strip below (shared x); ECE, Brier in legend / source CSV
  python make_figure.py bland-altman --csv results/agree.csv --a measA --b measB [--group dataset] [--unit HU]
      mean vs difference, bias line, +-1.96 SD limits with numbers, dash-dot regression line (slope +- 95 % CI in the source CSV) when the slope excludes 0

  Provenance watermark (every subcommand, here and in make_motivation.py): a diagonal light-grey "SYNTHETIC DEMO" is drawn across the axes (it is in the PDF
  text layer) and figures.csv `issues` gets `synthetic` when the data CSV lies OUTSIDE the project directory, its path contains synthetic / fake / demo, its
  header (or a leading # comment) names them, or --synthetic is given. A CSV inside the project but outside results/ and runs/ only prints a WARN (source not
  verified). --no-watermark-check skips the whole check (WARN, issues gets `provenance-unchecked`) for projects that keep their data elsewhere.

  --lower m1,m2   metrics where lower is better (unlisted: state.results metric_direction / primary_direction, else the
                  name regex of metric_direction.py, else higher). Only affects which value is called best in
                  the source CSV / caption text; bars and dots are drawn the same either way.

Reads state.results (main_table, ablation_table, group_key, reference_method, metric columns = all numeric columns unless --metrics).
Writes <out>.png (400 dpi at --width-mm), <out>.pdf, <out>.source.csv, and appends/updates a row in figures.csv (path, print width, source).
Style: serif 7.5 pt, no top/right spines, NMI-pastel blues + one red accent (same family as the validated demo_comparison figure).
"""
import argparse, csv, io, os, re, sys, statistics, collections
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
    a._data_paths = [os.path.join(root, res.get("main_table", "results/main.csv"))] + ([ap_] if os.path.exists(ap_) else [])
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

_SYN_NAME = re.compile(r"synthetic|fake|demo(?!g|cr)", re.I)                    # in a file name: figdemo.csv, fake_preds.csv (not demographics.csv)
_SYN_HEAD = re.compile(r"(?<![a-z])(synthetic|fake|demo)(?![a-z])", re.I)       # in a header cell as a word

def provenance(a, root):
    """decide whether a figure's data counts as synthetic -> (watermark?, issue tag or "", [warning lines]).
    --synthetic: yes. --no-watermark-check: no check at all. Otherwise per data CSV: outside the project directory, or synthetic / fake / demo in its
    path, header or leading # comment: yes; inside the project under results/ or runs/: verified; inside the project elsewhere: WARN only."""
    if getattr(a, "synthetic", False): return True, "synthetic", ["--synthetic 已给出，按合成数据加水印"]
    if getattr(a, "no_watermark_check", False): return False, "provenance-unchecked", ["--no-watermark-check：数据来源未核，水印判断已跳过"]
    paths = []
    c = getattr(a, "csv", "")
    if isinstance(c, str) and c: paths.append(os.path.join(root, c))
    paths += list(getattr(a, "_data_paths", []) or [])
    unchecked = []
    for p in paths:
        p = os.path.abspath(p)
        try: rel = os.path.relpath(p, root).replace(os.sep, "/")
        except ValueError: rel = "../" + os.path.basename(p)                      # another drive = outside the project
        if rel.startswith(".."): return True, "synthetic", ["数据不在 results/ 或 runs/ 下，按合成数据加水印"]
        if _SYN_NAME.search(rel): return True, "synthetic", [f"数据文件 {rel} 的路径含 synthetic / fake / demo，按合成数据加水印"]
        try:
            with io.open(p, encoding="utf-8-sig", errors="replace") as f: head = [f.readline() for _ in range(3)]
        except OSError: head = []
        for k, ln in enumerate(head):
            if (ln.lstrip().startswith("#") and _SYN_NAME.search(ln)) or (not ln.lstrip().startswith("#") and k < 2 and _SYN_HEAD.search(ln)):
                return True, "synthetic", [f"数据文件 {rel} 的表头 / 注释含 synthetic / fake / demo，按合成数据加水印"]
        if rel.split("/")[0].lower() not in ("results", "runs"): unchecked.append(rel)
    if unchecked: return False, "", [f"数据 {', '.join(unchecked)} 在项目内但不在 results/ 或 runs/ 下，来源未核（不加水印；正式图的数据请放进 results/ 或 runs/，或加 --no-watermark-check）"]
    return False, "", []

def add_watermark(fig):
    """diagonal light-grey SYNTHETIC DEMO across the union of the visible axes (real text, so it is in the PDF text layer)"""
    axs = [ax for ax in fig.axes if ax.get_visible()]
    if not axs: return
    x0 = min(ax.get_position().x0 for ax in axs); x1 = max(ax.get_position().x1 for ax in axs); y0 = min(ax.get_position().y0 for ax in axs); y1 = max(ax.get_position().y1 for ax in axs)
    W, H = fig.get_size_inches() * 72; w_pt, h_pt = (x1 - x0) * W, (y1 - y0) * H; ang = float(np.clip(np.degrees(np.arctan2(h_pt, w_pt)), 15, 40))
    fs = float(np.clip(0.8 * np.hypot(w_pt, h_pt) / 8.7, 7, 44))              # "SYNTHETIC DEMO" is about 8.7 font sizes wide
    fig.text((x0 + x1) / 2, (y0 + y1) / 2, "SYNTHETIC DEMO", rotation=ang, rotation_mode="anchor", ha="center", va="center", fontsize=fs, color="#b5b5b5", alpha=0.5, fontweight="bold", zorder=100, gid="synthetic-watermark")

def pdf_width_mm(path):
    """width of page 1 of a PDF in mm (PyMuPDF; else the /MediaBox of the raw bytes), None when unreadable"""
    try:
        import fitz
        with fitz.open(path) as d: return d[0].rect.width / 72 * 25.4
    except Exception:
        pass
    try:
        m = re.search(rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]", open(path, "rb").read())
        return (float(m.group(3)) - float(m.group(1))) / 72 * 25.4 if m else None
    except Exception:
        return None

def finish(fig, a, src_rows, src_hdr, root, caption):
    out = os.path.join(root, a.out); os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    issues = audit_layout(fig)
    for sev, msg in issues: print(f"[{sev}] layout: {msg}")
    mark, ptag, pwarn = provenance(a, root)
    for w_ in pwarn: print(f"[WARN] figure: {w_}")
    if mark: add_watermark(fig)
    png = os.path.splitext(out)[0] + ".png"   # raster always .png (--out x.pdf used to crash PIL below)
    fig.savefig(png, dpi=400, bbox_inches="tight"); fig.savefig(os.path.splitext(out)[0] + ".pdf", bbox_inches="tight")
    if os.path.splitext(out)[1].lower() not in (".png", ".pdf"): fig.savefig(out, dpi=400, bbox_inches="tight")
    from PIL import Image
    Image.open(png).convert("L").save(os.path.splitext(out)[0] + "_gray.png")   # grayscale preview: the colour-vision / print-in-B&W check
    wm = pdf_width_mm(os.path.splitext(out)[0] + ".pdf")            # bbox_inches="tight" grows the page: register the width the PDF really has
    if wm and abs(wm - a.width_mm) > 0.05:
        print(f"[INFO] width: the saved PDF is {wm:.1f} mm wide (requested {a.width_mm:g} mm, bbox-tight adds the label margins); figures.csv registers {wm:.1f} mm, so print sizes are measured on the real page. For a page that is exactly {a.width_mm:g} mm re-run with --width-mm {2 * a.width_mm - wm:.1f}")
        a.width_mm = round(wm, 1)
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
    if "issues" in hdr: new["issues"] = "auto: " + caption + ("" if not issues else " | layout: " + "; ".join(f"{sv} {m}" for sv, m in issues)) + (f" | {ptag}" if ptag else "")
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
    rows = list(csv.DictReader(l_ for l_ in open(path, encoding="utf-8-sig") if not l_.startswith("#")))      # leading "# ..." provenance comments are not data
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

CURVE_HUES = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#6a3d9a", "#8c564b", "#999933", "#332288"]   # Okabe-Ito style hues for the series that are neither ours nor the baseline: no red (accent), no shades of one blue
BASE_GREY = "#4b4f55"; RAW_GREY = "#808080"
EMA_MIN_POINTS = 20          # below this the EMA lags the data by ~1/alpha points and its end values are wrong: not drawn, markers instead
_CORNERS = [(True, False), (True, True), (False, False), (False, True)]       # (right, upper): lower right first


def _cover(P, rects):
    """share of the line samples P (axes fractions, N x 2) that lie inside any of the rectangles (x0, y0, x1, y1)"""
    if not len(P) or not rects: return 0.0
    m = np.zeros(len(P), bool)
    for x0, y0, x1, y1 in rects: m |= (P[:, 0] >= x0) & (P[:, 0] <= x1) & (P[:, 1] >= y0) & (P[:, 1] <= y1)
    return float(m.mean())

def _rect_hit(a_, b_): return a_[0] < b_[2] and b_[0] < a_[2] and a_[1] < b_[3] and b_[1] < a_[3]

def _best_corner(P, w, h, obstacles, left_room=0.0, bottom_room=0.0, m=0.03):
    """the corner of the panel where a w x h block (plus `left_room` / `bottom_room` for its tick labels) covers the fewest line samples and
    touches no obstacle -> (score, content box, padded box, (right, upper)); a clash with an obstacle adds 1 to the score"""
    best = None
    for right, up in _CORNERS:
        x0 = 1 - m - w if right else m + left_room; y0 = 1 - m - h if up else m + bottom_room
        box = (x0, y0, x0 + w, y0 + h); padded = (x0 - left_room - 0.01, y0 - bottom_room - 0.01, x0 + w + 0.01, y0 + h + 0.01)
        score = _cover(P, [padded]) + (1.0 if any(_rect_hit(padded, o) for o in obstacles) else 0.0)
        if best is None or score < best[0]: best = (score, box, padded, (right, up))
    return best

def _text_bb(t, rend):
    """window extent of the text alone (an Annotation's own extent also contains its leader arrow)"""
    import matplotlib.text as _mt
    return _mt.Text.get_window_extent(t, rend)

def _axes_fraction_rect(bb, axbb):
    return ((bb.x0 - axbb.x0) / axbb.width, (bb.y0 - axbb.y0) / axbb.height, (bb.x1 - axbb.x0) / axbb.width, (bb.y1 - axbb.y0) / axbb.height)

def _frac_points(ax, rend):
    axbb = ax.get_window_extent(rend); P = _line_samples(ax)
    return np.column_stack([(P[:, 0] - axbb.x0) / axbb.width, (P[:, 1] - axbb.y0) / axbb.height]) if len(P) else np.zeros((0, 2)), axbb


def fig_curves(a):
    """long CSV -> one line per series, seeds averaged with a band, optional small-multiple panels (+ Fig-6 options: EMA, inset, annotation)."""
    FS = plt.rcParams["font.size"]            # ONE size for axes labels, ticks, legend, end labels and inset ticks (the house size)
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
    legend = a.legend or ("auto" if new else "best")

    def collect(sname, pn):
        pts = collections.defaultdict(list)
        for r in rows:
            if (a.series and r.get(a.series, "") != sname) or (pn is not None and r[a.panel] != pn): continue
            try: pts[float(r[a.x])].append(float(r[a.y]))
            except ValueError: continue
        return pts
    npts = [len(collect(s_, pn)) for pn in panels for s_ in series_all if collect(s_, pn)]
    min_pts = min(npts) if npts else 0
    use_ema = a.ema > 0 and min_pts >= EMA_MIN_POINTS
    notes = []
    if a.ema and not use_ema:
        notes.append(f"--ema {a.ema:g} with only {min_pts} points per series (< {EMA_MIN_POINTS}): EMA smoothing is not meaningful here (it lags the data by about 1/alpha = {1 / a.ema:.0f} points "
                     f"and shifts the end values); drawing the raw seed means with markers instead. Annotated numbers are raw seed means either way")
    ncols = a.ncols or len(panels); nrows = -(-len(panels) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(a.width_mm / 25.4, a.height_in), sharey=(not a.logy and not a.free_y), squeeze=False); src = []; summ = []; info = []
    flat = [ax for r_ in axes for ax in r_]
    for ax in flat[len(panels):]: ax.set_visible(False)
    styles = {}; k_cat = 0
    for sname in series_all:
        if sname and sname == a.ours: styles[sname] = dict(color=ACCENT, ls="-", lw=1.8, mk="o", z=5)
        elif paired and sname == base: styles[sname] = dict(color=BASE_GREY, ls="--", lw=0.9, mk="s", z=4)
        else:
            styles[sname] = dict(color=CURVE_HUES[k_cat % len(CURVE_HUES)], ls="-", lw=1.1 if not a.ours else 0.9, mk=MARKS[(k_cat + 2) % len(MARKS)], z=3); k_cat += 1
    n_by = {}
    def draw_line(ax, xs, ys, st, idx, label=None, lw=None):
        sparse = len(xs) < EMA_MIN_POINTS; step = 1 if sparse else max(2, len(xs) // 7)
        ax.plot(xs, ys, lw=lw or st["lw"], color=st["color"], ls=st["ls"], marker=st["mk"], ms=2.8 if sparse else 2.4, markevery=(0, 1) if sparse else (idx * step // max(1, len(series_all)), step),
                markeredgewidth=0, label=label, zorder=st["z"])
    for pi, (ax, pn) in enumerate(zip(flat, panels)):
        cur = collections.OrderedDict()
        for i, sname in enumerate(series_all):
            pts = collect(sname, pn)
            if not pts: continue
            xs = np.array(sorted(pts)); ys = np.array([np.mean(pts[x]) for x in xs]); n = max(len(pts[x]) for x in xs); n_by[sname] = max(n, n_by.get(sname, 0))
            sd = np.array([np.std(pts[x], ddof=1) if len(pts[x]) > 1 else 0.0 for x in xs])
            lo = np.array([np.min(pts[x]) if a.band == "minmax" else m - s_ for x, m, s_ in zip(xs, ys, sd)]); hi = np.array([np.max(pts[x]) if a.band == "minmax" else m + s_ for x, m, s_ in zip(xs, ys, sd)])
            sm, lo_s, hi_s = (ema(ys, a.ema), ema(lo, a.ema), ema(hi, a.ema)) if use_ema else (ys, lo, hi)      # s_0 = first raw value: the line starts where the data start
            cur[sname] = dict(xs=xs, ys=ys, sm=sm, n=n)
            st = styles[sname]
            if use_ema: ax.plot(xs, ys, lw=0.5, color=RAW_GREY, alpha=0.15, zorder=1.5)       # raw records: one neutral light grey for every series
            draw_line(ax, xs, sm, st, i, label=(labels.get(sname, sname) if sname else None) if legend == "best" else None)
            if n > 1 and a.band != "none": ax.fill_between(xs, lo_s, hi_s, color=st["color"], alpha=0.16, lw=0, zorder=2)
            for x, y, y2 in zip(xs, ys, sm):
                row = [pn if pn is not None else "", sname, x, y, np.std(pts[x], ddof=1) if len(pts[x]) > 1 else 0.0, len(pts[x])]
                src.append(row + ([float(y2), "point", "", "", "", ""] if new else []))
        if a.logx: ax.set_xscale("log")
        if a.logy: ax.set_yscale("log")
        ax.set_xlabel(a.xlabel or labels.get(a.x, a.x), fontsize=FS); ax.grid(axis="y", lw=0.4, color="#e6e6e6", zorder=0); ax.tick_params(labelsize=FS)
        if pn is not None:
            ttl = labels.get(pn, pn)
            if a.letters: ax.set_title(f"({chr(97 + pi)}) {ttl}", fontsize=FS, loc="left", fontweight="bold")
            else: ax.set_title(ttl, fontsize=FS)
        if pi % ncols == 0: ax.set_ylabel(a.ylabel or labels.get(a.y, a.y), fontsize=FS)
        if not cur: continue
        allx = sorted({x for c in cur.values() for x in c["xs"]}); ax.set_xlim(allx[0], allx[-1]); ax.margins(x=0)     # x starts at the first epoch, no negative padding
        ann = None; inset = None
        if a.annotate and not (a.ours in cur and base in cur): notes.append(f"panel {pn}: ours or baseline has no data, no annotation")
        elif a.annotate:
            co, cb = cur[a.ours], cur[base]; common = sorted(set(co["xs"]) & set(cb["xs"]))
            if not common: notes.append(f"panel {pn}: ours and baseline share no x, no annotation")
            else:
                xc = common[-1]; vo = float(co["ys"][list(co["xs"]).index(xc)]); vb = float(cb["ys"][list(cb["xs"]).index(xc)]); d = vo - vb      # RAW seed means: the EMA is for drawing only
                ann = (xc, vo, vb, d)
                ax.scatter([xc], [vo], s=16, color=ACCENT, edgecolors="white", linewidths=0.4, zorder=6, clip_on=False)
                ax.scatter([xc], [vb], s=16, facecolors="white", edgecolors=BASE_GREY, linewidths=0.8, zorder=6, clip_on=False)
                src.append([pn if pn is not None else "", f"{a.ours} vs {base}", xc, "", "", "", "", "summary", vo, vb, d, "raw seed mean"]); summ.append((pn, xc, vo, vb, d))
        if a.inset:
            try:
                if a.inset.startswith("last:"): k = max(2, int(a.inset[5:])); x0, x1 = (allx[-k] if len(allx) >= k else allx[0]), allx[-1]
                else: x0, x1 = (float(t) for t in a.inset.split(":"))
            except ValueError: print(f"[FAIL] --inset must be last:N or x0:x1, got {a.inset!r}"); sys.exit(1)
            n_in = max(int(((c["xs"] >= x0) & (c["xs"] <= x1)).sum()) for c in cur.values()); n_all = max(len(c["xs"]) for c in cur.values())
            vals = np.concatenate([c["sm"][(c["xs"] >= x0) & (c["xs"] <= x1)] for c in cur.values()])
            if n_in >= 0.5 * n_all and n_all > 2: notes.append(f"panel {pn}: inset {a.inset} spans {n_in} of {n_all} points (>= half): the zoom would be the whole curve, no inset (use a smaller N or an x0:x1 range)")
            elif len(vals) >= 2 and x1 > x0:
                ylo, yhi = float(vals.min()), float(vals.max()); pad = 0.18 * (yhi - ylo or 1.0); inset = (x0, x1, ylo - pad, yhi + pad)
            else: notes.append(f"panel {pn}: inset range {x0:g}–{x1:g} holds fewer than 2 points, no inset")
        info.append(dict(ax=ax, pn=pn, cur=cur, ann=ann, inset=inset, allx=allx))
    from matplotlib.lines import Line2D
    def handle(s_):
        st = styles[s_]; sparse = min_pts < EMA_MIN_POINTS
        return Line2D([], [], color=st["color"], ls=st["ls"], lw=st["lw"], marker=st["mk"], ms=2.8 if sparse else 2.4, markeredgewidth=0)
    hs = [handle(s_) for s_ in series_all] if a.series else []; ls_ = [labels.get(s_, s_) for s_ in series_all] if a.series else []      # no "(n=3)": n goes into the caption
    if use_ema and hs: hs.append(Line2D([], [], color=RAW_GREY, lw=0.8, alpha=0.4)); ls_.append("Raw seed means")
    # ---- layout, then the overlays that need the final geometry: end labels, insets, legend
    above = legend == "above" and bool(hs)
    def legend_above():
        n = len(hs); ncol = n if len(series_all) <= 6 else -(-n // 2)       # one row; wrap only with more than 6 series
        for cs, hl in ((1.2, 1.6), (0.7, 1.2), (0.4, 0.9)):
            lg = fig.legend(hs, ls_, loc="upper center", ncol=ncol, fontsize=FS, handlelength=hl, columnspacing=cs, bbox_to_anchor=(0.5, 1.0))
            fig.canvas.draw()
            if lg.get_window_extent().width <= 0.985 * fig.bbox.width or ncol == 1: break
            lg.remove()
        else:
            ncol = -(-n // 2); notes.append(f"legend of {n} entries does not fit one row at this width: wrapped into two rows")
            lg = fig.legend(hs, ls_, loc="upper center", ncol=ncol, fontsize=FS, handlelength=1.2, columnspacing=0.7, bbox_to_anchor=(0.5, 1.0)); fig.canvas.draw()
        return lg
    lg_above = None
    if above:
        lg_above = legend_above(); h_fig = lg_above.get_window_extent().height / fig.bbox.height
        fig.tight_layout(pad=0.3, rect=(0, 0, 1, 1 - h_fig - 0.012))
    else: fig.tight_layout(pad=0.3)
    fig.canvas.draw(); rend = fig.canvas.get_renderer()
    label_arts = {}
    def place_end_labels():
        for rec in info:
            if not rec["ann"]: continue
            ax = rec["ax"]; xc, vo, vb, d = rec["ann"]; axbb = ax.get_window_extent(rend); unit = f" {a.delta_unit}" if a.delta_unit else ""
            txt = {a.ours: f"{labels.get(a.ours, a.ours)} {vo:.2f}", base: f"{labels.get(base, base)} {vb:.2f}", "__delta__": f"Δ {d:+.2f}{unit}".replace("-", "−")}
            if id(ax) not in label_arts:
                label_arts[id(ax)] = {}
                for nm, (v, c) in ((a.ours, (vo, ACCENT)), (base, (vb, BASE_GREY)), ("__delta__", (min(vo, vb), "#333333"))):
                    t = ax.annotate(txt[nm], (xc, v), xytext=(5, 0), textcoords="offset points", ha="left", va="center", fontsize=FS, color=c, fontweight="bold" if nm == a.ours else "normal",
                                    linespacing=1.15, zorder=7, annotation_clip=False, gid="end-label",
                                    arrowprops=dict(arrowstyle="-", lw=0.4, color=c, shrinkA=0.5, shrinkB=1.5, relpos=(0, 0.5)))
                    t.arrow_patch.set_visible(False); label_arts[id(ax)][nm] = (t, v)
                # widen the x range so the labels sit inside the axes, to the right of the LAST x of the panel (the markers may be earlier)
                wmax = max(_text_bb(t, rend).width for t, _ in label_arts[id(ax)].values()) + 7 * fig.dpi / 72
                f = np.log10 if a.logx else (lambda z: z); x0 = rec["allx"][0]; xmax = rec["allx"][-1]
                if f(xmax) > f(x0):
                    need = f(x0) + (f(xmax) - f(x0)) * axbb.width / max(axbb.width - wmax, 0.3 * axbb.width)
                    ax.set_xlim(x0, 10 ** need if a.logx else need)
        fig.canvas.draw()
        for rec in info:                                                                 # vertical de-collision of the two labels (display px, top to bottom)
            if not rec["ann"] or id(rec["ax"]) not in label_arts: continue
            ax = rec["ax"]; axbb = ax.get_window_extent(rend); xc = rec["ann"][0]; items = []
            dx_pt = (ax.transData.transform((rec["allx"][-1], 0))[0] - ax.transData.transform((xc, 0))[0]) * 72 / fig.dpi + 5
            for nm, (t, v) in label_arts[id(ax)].items():
                y = ax.transData.transform((xc, v))[1]; h = _text_bb(t, rend).height; items.append([y - (0.01 if nm == "__delta__" else 0.0), h, t])       # the Δ line always sits below the two value labels
            items.sort(key=lambda z: -z[0])
            for it in items: it.append(it[0])
            for _pass in range(3):                       # push down from the top, clamp into the axes, push back up from the bottom
                for k in range(1, len(items)): items[k][3] = min(items[k][3], items[k - 1][3] - items[k - 1][1] / 2 - items[k][1] / 2 - 1.5)
                for it in items: it[3] = min(max(it[3], axbb.y0 + it[1] / 2), axbb.y1 - it[1] / 2)
                for k in range(len(items) - 2, -1, -1): items[k][3] = max(items[k][3], items[k + 1][3] + items[k + 1][1] / 2 + items[k][1] / 2 + 1.5)
            for y, h, t, pos in items:
                t.xyann = (dx_pt, (pos - y) * 72 / fig.dpi); t.arrow_patch.set_visible(not t.get_text().startswith("Δ") and (dx_pt > 9 or abs(pos - y) * 72 / fig.dpi > 4))       # a thin leader only when the label had to move away from its marker
        fig.canvas.draw()
    place_end_labels()
    # insets: the corner with the fewest plotted samples, clear of the end labels
    ins_pad = {}
    for rec in info:
        if not rec["inset"]: continue
        ax = rec["ax"]; P, axbb = _frac_points(ax, rend)
        obs = [_axes_fraction_rect(_text_bb(t, rend), axbb) for t, _ in label_arts.get(id(ax), {}).values()]
        got = None
        for w_, h_ in ((0.40, 0.34), (0.30, 0.28)):
            sc, box, padded, _ = _best_corner(P, w_, h_, obs, left_room=0.19, bottom_room=0.19)
            if sc <= 0.06: got = (box, padded); break
        if got is None: notes.append(f"panel {rec['pn']}: no free corner for the inset (best one would still cover {sc:.0%} of the plotted samples), no inset"); continue
        x0, x1, ylo, yhi = rec["inset"]; box, padded = got; ins_pad[id(ax)] = padded
        ins = ax.inset_axes([box[0], box[1], box[2] - box[0], box[3] - box[1]]); ins.set_zorder(8)
        for i, (sname, c) in enumerate(rec["cur"].items()):
            m = (c["xs"] >= x0) & (c["xs"] <= x1); st = styles[sname]; ins.plot(c["xs"][m], c["sm"][m], lw=st["lw"] * 0.9, color=st["color"], ls=st["ls"], marker=st["mk"], ms=2.2, markeredgewidth=0)
        ins.set_xlim(x0, x1); ins.set_ylim(ylo, yhi)
        xt = np.linspace(x0, x1, 3); xt = np.round(xt) if all(float(v).is_integer() for v in rec["allx"]) else xt
        ins.set_xticks(xt); ins.set_xticklabels([_fx(v) for v in xt]); ins.yaxis.set_major_locator(plt.MaxNLocator(4, min_n_ticks=3))
        ins.tick_params(labelsize=FS, length=1.8, width=0.4, pad=1.2)                                     # inset ticks at the house size (>= 6 pt)
        for sp_ in ins.spines.values(): sp_.set_visible(True); sp_.set_linewidth(0.5); sp_.set_color("#555")
        ind = ax.indicate_inset_zoom(ins, edgecolor="#555555", linewidth=0.6); ind.set_zorder(6)
        for cn in getattr(ind, "connectors", ()) or (): cn.set_linewidth(0.5); cn.set_color("#555555")
    # legend inside the axes when a free corner exists (occupancy test), else one row above the panels
    if legend == "auto" and hs:
        best = None
        for rec in info:
            ax = rec["ax"]; P, axbb = _frac_points(ax, rend)
            obs = [_axes_fraction_rect(_text_bb(t, rend), axbb) for t, _ in label_arts.get(id(ax), {}).values()] + ([ins_pad[id(ax)]] if id(ax) in ins_pad else [])
            tmp = ax.legend(hs, ls_, fontsize=FS, loc="lower left", handlelength=1.4, labelspacing=0.3, borderaxespad=0); fig.canvas.draw()
            bb = tmp.get_window_extent(rend); tmp.remove()
            sc, box, padded, _ = _best_corner(P, bb.width / axbb.width, bb.height / axbb.height, obs)
            if best is None or sc < best[0]: best = (sc, ax, box)
        if best and best[0] <= 0.02:
            sc, ax, box = best; ax.legend(hs, ls_, fontsize=FS, loc="lower left", bbox_to_anchor=(box[0], box[1]), bbox_transform=ax.transAxes, borderaxespad=0, handlelength=1.4, labelspacing=0.3)
        else:
            lg_above = legend_above(); h_fig = lg_above.get_window_extent().height / fig.bbox.height
            fig.tight_layout(pad=0.3, rect=(0, 0, 1, 1 - h_fig - 0.012)); fig.canvas.draw(); place_end_labels()
    elif legend == "best" and a.series: flat[len(panels) - 1].legend(fontsize=FS, loc="best", handlelength=1.2)
    for n_ in notes: print(f"[WARN] curves: {n_}")
    for pn, xc, vo, vb, d in summ: print(f"annotated {pn if pn is not None else 'panel'}: Δ{a.y} @ {a.x} {_fx(xc)} = {d:+.2f} ({a.ours} {vo:.2f}, {base} {vb:.2f}; raw seed means)")
    nmax = max(n_by.values()) if n_by else 1
    band_txt = {"sd": "shaded band = ± s.d. over seeds", "minmax": "shaded band = min–max over seeds", "none": ("no band drawn" if nmax > 1 else "single run per series")}[a.band]
    cap = f"Curves of {a.y} vs. {a.x}; {band_txt}"
    if nmax > 1: cap += f"; n = {nmax} seeds per series" if len(set(n_by.values())) == 1 else "; seeds per series: " + ", ".join(f"{labels.get(k, k)} {v}" for k, v in n_by.items())
    if use_ema: cap += f"; solid lines = EMA smoothing (α = {a.ema:g}, s_0 = first value) of the seed mean, faint grey lines = raw seed means"
    elif a.ema: cap += f"; --ema {a.ema:g} not applied ({min_pts} points per series < {EMA_MIN_POINTS}), lines are the raw seed means"
    if a.inset and any(r_["inset"] for r_ in info): cap += f"; inset and grey rectangle zoom on {a.inset}"
    if a.annotate: cap += f"; circles mark the last {a.x} both series share; end labels and Δ = {a.ours} − {base} are the RAW seed means at that {a.x} (the EMA is for drawing only)"
    hdr = ["panel", "series", a.x, f"{a.y}_mean", f"{a.y}_sd", "n"] + ([f"{a.y}_smooth", "kind", "ours", "baseline", "delta", "basis"] if new else [])
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


# ------------------------------------------------------------------ classification / agreement panels (roc, pr, confusion, calibration, bland-altman)
def _to01(v):
    s = str(v).strip().lower()
    if s in ("1", "1.0", "true", "yes", "pos", "positive"): return 1
    if s in ("0", "0.0", "false", "no", "neg", "negative"): return 0
    raise ValueError(v)

def _ci_spec(a):
    """'--ci bootstrap:200' -> 200 resamples (0 = no interval)"""
    s = getattr(a, "ci", "") or ""
    if not s: return 0
    kind, _, n = s.partition(":")
    try: b = int(n)
    except ValueError: b = 0
    if kind != "bootstrap" or b < 20: print(f"[FAIL] --ci wants bootstrap:N with N >= 20, got {s!r}"); sys.exit(1)
    return b

def _binary_groups(root, a, ycol, scol, gcol, tag):
    """long CSV -> OrderedDict group -> (y in {0,1}, score); rows whose score is not a finite number are dropped and counted"""
    rows = _csv_rows(root, a.csv, [ycol, scol, gcol]); groups = collections.OrderedDict(); bad = 0
    for r in rows:
        try: y = _to01(r[ycol])
        except ValueError: print(f"[FAIL] {tag}: label {r[ycol]!r} in column {ycol} is not binary (0/1, true/false)"); sys.exit(1)
        try: s = float(r[scol])
        except ValueError: bad += 1; continue
        if not np.isfinite(s): bad += 1; continue
        ys, ss = groups.setdefault(r[gcol] if gcol else "", ([], [])); ys.append(y); ss.append(s)
    if bad: print(f"[WARN] {tag}: {bad} row(s) with a non-numeric / non-finite {scol} dropped")
    if not groups: print(f"[FAIL] {tag}: no usable rows in {a.csv}"); sys.exit(1)
    out = collections.OrderedDict()
    for g, (ys, ss) in groups.items():
        y = np.array(ys, int); s = np.array(ss, float); npos = int(y.sum()); nneg = int(len(y) - npos); name = g or "all"
        if npos == 0 or nneg == 0: print(f"[FAIL] {tag}: group {name!r} has only one class (n_pos={npos}, n_neg={nneg}); the curve is undefined"); sys.exit(1)
        if npos < 10 or nneg < 10: print(f"[WARN] {tag}: group {name!r} n_pos={npos}, n_neg={nneg} (< 10): {'AUC' if tag == 'roc' else 'AP'} unstable")
        out[g] = (y, s)
    return out

def _trapz(x, y): return float(np.sum(np.diff(x) * (y[1:] + y[:-1]) / 2.0))

def roc_points(y, s):
    """(fpr, tpr) at every distinct score threshold, starting at (0, 0); tied scores share one point, so the area equals the Mann-Whitney AUC"""
    o = np.argsort(-s, kind="mergesort"); y = y[o]; s = s[o]
    tps = np.cumsum(y); fps = np.cumsum(1 - y); idx = np.r_[np.where(np.diff(s))[0], len(s) - 1]
    return np.r_[0.0, fps[idx] / fps[-1]], np.r_[0.0, tps[idx] / tps[-1]]

def auc_score(y, s):
    f, t = roc_points(y, s); return _trapz(f, t)

def pr_points(y, s):
    """(recall, precision) at every distinct score threshold, recall ascending"""
    o = np.argsort(-s, kind="mergesort"); y = y[o]; s = s[o]
    tps = np.cumsum(y); fps = np.cumsum(1 - y); idx = np.r_[np.where(np.diff(s))[0], len(s) - 1]
    return tps[idx] / tps[-1], tps[idx] / (tps[idx] + fps[idx])

def average_precision(y, s):
    """step-wise area under the PR curve: sum (R_n - R_n-1) * P_n (the scikit-learn definition)"""
    r, p = pr_points(y, s); return float(np.sum(np.diff(np.r_[0.0, r]) * p))

def _interp_precision(r, p, grid):
    pm = np.maximum.accumulate(p[::-1])[::-1]; idx = np.searchsorted(r, grid, side="left")
    return np.where(idx < len(r), pm[np.minimum(idx, len(r) - 1)], 0.0)

def _bootstrap(y, s, kind, B, rng, grid):
    """stratified bootstrap (positives and negatives resampled separately): -> (metric samples, curve samples on `grid`)"""
    pos = np.where(y == 1)[0]; neg = np.where(y == 0)[0]; m = np.empty(B); cur = np.empty((B, len(grid)))
    for b in range(B):
        ix = np.r_[rng.choice(pos, len(pos)), rng.choice(neg, len(neg))]; yb, sb = y[ix], s[ix]
        if kind == "roc":
            f, t = roc_points(yb, sb); m[b] = _trapz(f, t); cur[b] = np.interp(grid, f, t)
        else:
            r, p = pr_points(yb, sb); m[b] = float(np.sum(np.diff(np.r_[0.0, r]) * p)); cur[b] = _interp_precision(r, p, grid)
    return m, cur

def _fig_binary(a, kind):
    """roc / pr: one curve per group, chance / prevalence reference, area in the legend (+ stratified bootstrap 95 % band with --ci)"""
    root = os.path.abspath(a.project); tag = kind; B = _ci_spec(a)
    groups = _binary_groups(root, a, a.y_true, a.score, a.group, tag)
    if a.ours and a.ours not in groups: print(f"[FAIL] {tag}: --ours {a.ours!r} not in groups {list(groups)}"); sys.exit(1)
    rng = np.random.default_rng(a.seed); grid = np.linspace(0, 1, 101); metric = "auc" if kind == "roc" else "ap"; MET = metric.upper()
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, a.height_in)); fig.subplots_adjust(left=0.15, right=0.97, bottom=0.14, top=0.97)
    names = [g for g in groups if not a.ours or g != a.ours] + ([a.ours] if a.ours else []); src = []; summ = []; prevs = []
    if len(names) > len(CAT): print(f"[WARN] {tag}: {len(names)} groups, colours repeat after {len(CAT)}")
    for i, g in enumerate(names):
        y, s = groups[g]; npos = int(y.sum()); nneg = int(len(y) - npos); is_ours = bool(a.ours) and g == a.ours; col = ACCENT if is_ours else CAT[i % len(CAT)]; ls = "-" if is_ours else ["-", "--", "-.", ":"][i % 4]
        if kind == "roc": xs, ys_ = roc_points(y, s); val = _trapz(xs, ys_)
        else: xs, ys_ = pr_points(y, s); val = float(np.sum(np.diff(np.r_[0.0, xs]) * ys_)); xs = np.r_[0.0, xs]; ys_ = np.r_[ys_[0], ys_]; prevs.append(npos / len(y))
        lo = hi = None; label = f"{g or 'all'}  {MET} {val:.3f}"
        if B:
            m, cur = _bootstrap(y, s, kind, B, rng, grid); lo, hi = (float(v) for v in np.percentile(m, [2.5, 97.5]))
            blo, bhi = np.percentile(cur, [2.5, 97.5], axis=0); label += f" [{lo:.3f}, {hi:.3f}]"
            ax.fill_between(grid, blo, bhi, color=col, alpha=0.15, lw=0, zorder=2)
            for gx, l_, h_ in zip(grid, blo, bhi): src.append([g or "all", "band", gx, "", l_, h_, "", "", "", "", ""])
        if kind == "roc": ax.plot(xs, ys_, color=col, ls=ls, lw=1.2 if is_ours else 0.9, label=label, zorder=4 if is_ours else 3)
        else: ax.step(xs, ys_, where="pre", color=col, ls=ls, lw=1.2 if is_ours else 0.9, label=label, zorder=4 if is_ours else 3)
        for x_, y_ in zip(xs, ys_): src.append([g or "all", "curve", x_, y_, "", "", "", "", "", "", ""])
        src.append([g or "all", "summary", "", "", "", "", val, "" if lo is None else lo, "" if hi is None else hi, npos, nneg]); summ.append((g or "all", val, lo, hi, npos, nneg))
        print(f"{kind}: {g or 'all'}: {MET} {val:.4f}" + ("" if lo is None else f" [95% CI {lo:.4f}, {hi:.4f}; bootstrap {B}, seed {a.seed}]") + f" (n_pos={npos}, n_neg={nneg})")
    if kind == "roc":
        ax.plot([0, 1], [0, 1], ls=":", lw=0.7, color="#8a8a8a", zorder=1, label="chance"); ax.set_xlabel(a.xlabel or "False positive rate"); ax.set_ylabel(a.ylabel or "True positive rate"); loc = "lower right"
        ax.set_aspect("equal", adjustable="box")
    else:
        pv_ = sorted({round(p_, 6) for p_ in prevs})
        for k, pv in enumerate(pv_): ax.axhline(pv, ls=":", lw=0.7, color="#8a8a8a", zorder=1, label=(f"prevalence {pv:.2f}" if len(pv_) == 1 else f"prevalence {pv_[0]:.2f}–{pv_[-1]:.2f}") if k == 0 else None)
        ax.set_xlabel(a.xlabel or "Recall"); ax.set_ylabel(a.ylabel or "Precision"); loc = "lower left"
    ax.set_xlim(-0.01, 1.01); ax.set_ylim(-0.01, 1.01); ax.grid(lw=0.4, color="#ececec", zorder=0); ax.legend(fontsize=5.8, loc=loc, handlelength=1.6, labelspacing=0.3)
    cap = (f"{'ROC' if kind == 'roc' else 'Precision–recall'} curves; {MET} in the legend" + (f" with a stratified bootstrap 95 % interval ({B} resamples, seed {a.seed}), band = pointwise 95 % interval" if B else "") + "; "
           + "; ".join(f"{g}: n_pos={p_}, n_neg={n_}" for g, _, _, _, p_, n_ in summ) + ".")
    xn, yn = ("fpr", "tpr") if kind == "roc" else ("recall", "precision")
    finish(fig, a, src, ["group", "kind", xn, yn, f"{yn}_lo", f"{yn}_hi", metric, "ci_lo", "ci_hi", "n_pos", "n_neg"], root, cap)

def fig_roc(a): _fig_binary(a, "roc")
def fig_pr(a): _fig_binary(a, "pr")


def _read_confusion(root, a):
    """-> (labels, integer-valued count matrix, rows = true class, columns = predicted class)"""
    cls = [t.strip() for t in a.labels.split(",") if t.strip()] if a.labels else []
    if a.matrix:
        path = os.path.join(root, a.csv)
        if not os.path.exists(path): print(f"[FAIL] {a.csv} does not exist"); sys.exit(1)
        grid = [r for r in csv.reader(open(path, encoding="utf-8-sig")) if any(c.strip() for c in r)]
        if not grid: print(f"[FAIL] {a.csv} is empty"); sys.exit(1)
        lab_row = not all(_isnum(c) for c in grid[0][1:]) if len(grid[0]) > 1 else False
        if lab_row: names = [c.strip() for c in grid[0][1:]]; body = [r[1:] for r in grid[1:]]
        else: body = grid; names = []
        try: M = np.array([[float(c) for c in r] for r in body])
        except ValueError: print(f"[FAIL] confusion: {a.csv} holds non-numeric cells in the matrix body"); sys.exit(1)
        if M.ndim != 2 or M.shape[0] != M.shape[1]: print(f"[FAIL] confusion: matrix is {M.shape}, a square class x class table is required"); sys.exit(1)
        if (M < 0).any() or not np.isfinite(M).all(): print("[FAIL] confusion: counts must be finite and >= 0"); sys.exit(1)
        n = M.shape[0]; labels = cls or names or [str(i) for i in range(n)]
        if len(labels) != n: print(f"[FAIL] confusion: {len(labels)} labels for a {n} x {n} matrix"); sys.exit(1)
        return labels, M
    if not (a.true_col and a.pred_col): print("[FAIL] confusion: give --true-col and --pred-col (or --matrix for a precomputed table)"); sys.exit(1)
    rows = _csv_rows(root, a.csv, [a.true_col, a.pred_col]); seen = set(); pairs = []
    for r in rows:
        t_, p_ = r[a.true_col].strip(), r[a.pred_col].strip()
        if t_ == "" or p_ == "": continue
        pairs.append((t_, p_)); seen.update((t_, p_))
    if not pairs: print(f"[FAIL] confusion: no complete (true, pred) rows in {a.csv}"); sys.exit(1)
    if cls:
        extra = sorted(seen - set(cls))
        if extra: print(f"[FAIL] confusion: values {extra} in the data are not in --labels {cls}"); sys.exit(1)
        labels = cls
    else: labels = sorted(seen, key=(lambda v: float(v)) if all(_isnum(v) for v in seen) else str)
    ix = {l_: i for i, l_ in enumerate(labels)}; M = np.zeros((len(labels), len(labels)))
    for t_, p_ in pairs: M[ix[t_], ix[p_]] += 1
    return labels, M

def fig_confusion(a):
    """confusion matrix heatmap: count + row-normalised percentage in each cell, per-class recall / precision in the source CSV"""
    root = os.path.abspath(a.project); labels, M = _read_confusion(root, a); n = len(labels); total = float(M.sum())
    if total <= 0: print("[FAIL] confusion: the matrix is empty"); sys.exit(1)
    rs = M.sum(1); cs = M.sum(0); tp = np.diag(M)
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.where(rs[:, None] > 0, M / rs[:, None], np.nan); rec = np.where(rs > 0, tp / rs, np.nan); prec = np.where(cs > 0, tp / cs, np.nan)
    norm = a.normalize == "true"; Z = np.nan_to_num(R, nan=0.0) if norm else M
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, a.height_in))
    im = ax.pcolormesh(np.arange(n + 1) - 0.5, np.arange(n + 1) - 0.5, Z, cmap="Blues", vmin=0, vmax=1.0 if norm else max(1.0, M.max()), edgecolors="white", linewidth=0.6)   # a mesh, not imshow: stays vector
    ax.set_xlim(-0.5, n - 0.5); ax.set_ylim(n - 0.5, -0.5); ax.set_aspect("equal")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03); cb.solids.set_rasterized(False); cb.ax.tick_params(labelsize=6, length=2); cb.set_label("Row-normalised share" if norm else "Count", fontsize=6.3)
    ax.set_xticks(range(n)); ax.set_yticks(range(n)); ax.set_xticklabels(labels, fontsize=6.3, rotation=45 if n > 6 or max(len(l_) for l_ in labels) > 6 else 0, ha="right" if (n > 6 or max(len(l_) for l_ in labels) > 6) else "center")
    ax.set_yticklabels(labels, fontsize=6.3); ax.set_xlabel(a.xlabel or "Predicted"); ax.set_ylabel(a.ylabel or "True"); ax.tick_params(length=0)
    for sp_ in ax.spines.values(): sp_.set_visible(False)
    if n > 12: print(f"[WARN] confusion: {n} classes, cell text would fall below 5 pt and is left out; counts and shares are in the source CSV")
    else:
        fs = 6.3 if n <= 5 else (5.5 if n <= 8 else 5.0)
        for i in range(n):
            for j in range(n):
                frac = Z[i, j] / (1.0 if norm else max(1.0, M.max())); colr = "white" if frac > 0.55 else "#222"
                share = "–" if np.isnan(R[i, j]) else f"{100 * R[i, j]:.1f}%"
                ax.text(j, i, f"{int(round(M[i, j]))}" + (f"\n{share}" if n <= 8 else ""), ha="center", va="center", fontsize=fs, color=colr)
    src = []
    for i in range(n):
        for j in range(n): src.append(["cell", labels[i], labels[j], int(round(M[i, j])), "" if np.isnan(R[i, j]) else 100 * R[i, j], "", "", ""])
    for i in range(n): src.append(["class", labels[i], "", int(round(tp[i])), "", "" if np.isnan(rec[i]) else rec[i], "" if np.isnan(prec[i]) else prec[i], int(round(rs[i]))])
    acc = float(tp.sum() / total); src.append(["accuracy", "", "", int(round(tp.sum())), "", acc, "", int(round(total))])
    weak = [labels[i] for i in range(n) if rs[i] > 0 and rec[i] < 0.5]
    print(f"confusion: n={int(round(total))}, accuracy {acc:.4f}; recall " + ", ".join(f"{l_} {('n/a' if np.isnan(r_) else format(r_, '.3f'))}" for l_, r_ in zip(labels, rec)))
    if weak: print(f"[WARN] confusion: recall below 0.5 for {weak}")
    finish(fig, a, src, ["kind", "true", "pred", "count", "row_pct", "recall", "precision", "support"], root,
           f"Confusion matrix (rows = true class, columns = predicted); each cell: count and row-normalised percentage; n = {int(round(total))}, accuracy {acc:.3f}.")


def calib_bins(p, y, bins, strategy):
    """-> list of (lo, hi, n, mean confidence, observed frequency), empty bins omitted"""
    if strategy == "quantile": edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    else: edges = np.linspace(0, 1, bins + 1)
    if len(edges) < 2: edges = np.array([p.min(), p.max() + 1e-12])
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2); out = []
    for b in range(len(edges) - 1):
        m = idx == b
        if m.any(): out.append((float(edges[b]), float(edges[b + 1]), int(m.sum()), float(p[m].mean()), float(y[m].mean())))
    return out

def ece_score(p, y, bins, strategy):
    bs = calib_bins(p, y, bins, strategy); return float(sum(n / len(p) * abs(acc - conf) for _, _, n, conf, acc in bs))

def fig_calibration(a):
    """reliability diagram + prediction histogram strip (two axes sharing x); ECE and Brier per group"""
    root = os.path.abspath(a.project)
    if a.bins < 2: print("[FAIL] calibration: --bins must be >= 2"); sys.exit(1)
    rows = _csv_rows(root, a.csv, [a.y_true, a.prob, a.group]); groups = collections.OrderedDict(); bad = 0
    for r in rows:
        try: y = _to01(r[a.y_true])
        except ValueError: print(f"[FAIL] calibration: label {r[a.y_true]!r} is not binary (0/1, true/false)"); sys.exit(1)
        try: p = float(r[a.prob])
        except ValueError: bad += 1; continue
        if not np.isfinite(p): bad += 1; continue
        if not 0.0 <= p <= 1.0: print(f"[FAIL] calibration: probability {p} outside [0, 1] in column {a.prob} (give probabilities, not logits)"); sys.exit(1)
        ys, ps = groups.setdefault(r[a.group] if a.group else "", ([], [])); ys.append(y); ps.append(p)
    if bad: print(f"[WARN] calibration: {bad} row(s) with a non-numeric {a.prob} dropped")
    if not groups: print(f"[FAIL] calibration: no usable rows in {a.csv}"); sys.exit(1)
    names = list(groups)
    if a.ours and a.ours not in groups: print(f"[FAIL] calibration: --ours {a.ours!r} not in groups {names}"); sys.exit(1)
    names = [g for g in names if not a.ours or g != a.ours] + ([a.ours] if a.ours else [])
    from matplotlib.lines import Line2D
    fig, (ax, ax2) = plt.subplots(2, 1, sharex=True, figsize=(a.width_mm / 25.4, a.height_in), gridspec_kw=dict(height_ratios=[3.4, 1]))
    fig.subplots_adjust(left=0.15, right=0.97, bottom=0.12, top=0.97, hspace=0.07)
    ax.plot([0, 1], [0, 1], ls=":", lw=0.7, color="#8a8a8a", zorder=1); nmax = max(len(groups[g][0]) for g in names); src = []; hollow = False; hb = np.linspace(0, 1, 21)
    allbins = max(max(b[2] for b in calib_bins(np.array(groups[g][1]), np.array(groups[g][0]), a.bins, a.strategy)) for g in names)
    for i, g in enumerate(names):
        y = np.array(groups[g][0], float); p = np.array(groups[g][1], float); col = ACCENT if (a.ours and g == a.ours) else CAT[i % len(CAT)]
        bs = calib_bins(p, y, a.bins, a.strategy); ece = ece_score(p, y, a.bins, a.strategy); brier = float(np.mean((p - y) ** 2))
        if a.strategy == "quantile" and len(bs) < a.bins: print(f"[WARN] calibration: group {g or 'all'!r}: {a.bins - len(bs)} quantile bin(s) merged because of tied probabilities")
        if len(p) < 50: print(f"[WARN] calibration: group {g or 'all'!r} has only {len(p)} samples; the reliability diagram is mostly noise")
        cx = [b[3] for b in bs]; cy = [b[4] for b in bs]; ax.plot(cx, cy, color=col, lw=0.7, alpha=0.7, zorder=2)
        for lo, hi, n, conf, acc in bs:
            sz = 6 + 50 * n / allbins; small = n < 5; hollow |= small
            ax.scatter([conf], [acc], s=sz, facecolors="white" if small else col, edgecolors=col, linewidths=0.8, zorder=4)
            src.append([g or "all", "bin", f"{lo:.6g}", f"{hi:.6g}", n, conf, acc, "", "", ""])
        ax.plot([], [], color=col, marker="o", ms=3.5, lw=0.7, label=f"{g or 'all'}  ECE {ece:.3f}, Brier {brier:.3f}")
        ax2.hist(p, bins=hb, histtype="step", color=col, lw=0.9); src.append([g or "all", "summary", "", "", "", "", "", ece, brier, len(p)])
        print(f"calibration: {g or 'all'}: ECE {ece:.4f} ({a.bins} {a.strategy} bins), Brier {brier:.4f}, n={len(p)}")
    hs, ls = ax.get_legend_handles_labels()
    if hollow: hs.append(Line2D([], [], marker="o", ls="", mfc="white", mec="#555", ms=3.5)); ls.append("bin with n < 5")
    ax.legend(hs, ls, fontsize=5.8, loc="upper left", handlelength=1.4, labelspacing=0.3)
    ax.set_xlim(-0.01, 1.01); ax.set_ylim(-0.01, 1.01); ax.set_ylabel(a.ylabel or "Observed frequency"); ax.grid(lw=0.4, color="#ececec", zorder=0); ax.tick_params(labelbottom=False)
    ax2.set_xlabel(a.xlabel or "Predicted probability"); ax2.set_ylabel("Count", fontsize=6.3); ax2.yaxis.set_major_locator(plt.MaxNLocator(2)); ax2.grid(axis="y", lw=0.4, color="#ececec", zorder=0)
    finish(fig, a, src, ["group", "kind", "bin_lo", "bin_hi", "n", "mean_conf", "obs_freq", "ece", "brier", "n_total"], root,
           f"Reliability diagram ({a.bins} {a.strategy} bins; marker area ∝ bin count, hollow = fewer than 5 samples); ECE and Brier score in the legend; lower strip = histogram of predicted probabilities (n = {nmax} in the largest group).")


def t_crit(df, conf=0.95):
    """two-sided Student t quantile, Cornish–Fisher expansion about the normal quantile (error < 0.5 % from df = 5)"""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(0.5 + conf / 2); d = float(df)
    return z + (z ** 3 + z) / (4 * d) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * d ** 2) + (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / (384 * d ** 3)

def ba_stats(A, B_):
    """-> dict: n, bias, sd (ddof = 1), limits of agreement, proportional-bias regression of the difference on the mean"""
    m = (A + B_) / 2.0; d = A - B_; n = len(d); bias = float(d.mean()); sd = float(d.std(ddof=1)) if n > 1 else float("nan")
    out = dict(n=n, bias=bias, sd=sd, lo=bias - 1.96 * sd, hi=bias + 1.96 * sd, slope=float("nan"), s_lo=float("nan"), s_hi=float("nan"), icpt=float("nan"), prop=False)
    sxx = float(((m - m.mean()) ** 2).sum())
    if n >= 4 and sxx > 0:
        slope = float(((m - m.mean()) * (d - d.mean())).sum() / sxx); icpt = float(d.mean() - slope * m.mean())
        rss = float(((d - icpt - slope * m) ** 2).sum()); se = float(np.sqrt(rss / (n - 2) / sxx)); tc = t_crit(n - 2)
        out.update(slope=slope, icpt=icpt, s_lo=slope - tc * se, s_hi=slope + tc * se, prop=bool(slope - tc * se > 0 or slope + tc * se < 0))
    return out

def fig_bland_altman(a):
    """mean vs difference with bias and +-1.96 SD limits; regression line of the difference on the mean when its slope is significant"""
    root = os.path.abspath(a.project); rows = _csv_rows(root, a.csv, [a.a, a.b, a.group]); pts = collections.OrderedDict(); bad = 0
    for r in rows:
        try: x, y = float(r[a.a]), float(r[a.b])
        except ValueError: bad += 1; continue
        if not (np.isfinite(x) and np.isfinite(y)): bad += 1; continue
        pts.setdefault(r[a.group] if a.group else "", []).append((x, y))
    if bad: print(f"[WARN] bland-altman: {bad} row(s) with a non-numeric measurement dropped")
    A = np.array([p[0] for g in pts.values() for p in g]); Bv = np.array([p[1] for g in pts.values() for p in g])
    if len(A) < 3: print(f"[FAIL] bland-altman: {len(A)} paired measurement(s); at least 3 are needed for limits of agreement"); sys.exit(1)
    if len(A) < 30: print(f"[WARN] bland-altman: n={len(A)} < 30; the limits of agreement are imprecise (their own 95 % CI is wide)")
    st = ba_stats(A, Bv); unit = f" ({a.unit})" if a.unit else ""; u = f" {a.unit}" if a.unit else ""
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, a.height_in)); fig.subplots_adjust(left=0.15, right=0.97, bottom=0.15, top=0.97)
    names = list(pts)
    if len(names) > len(CAT): print(f"[WARN] bland-altman: {len(names)} groups, colours repeat after {len(CAT)}")
    src = []
    for i, g in enumerate(names):
        xy = np.array(pts[g]); mm = xy.mean(1); dd = xy[:, 0] - xy[:, 1]
        ax.scatter(mm, dd, s=7, color=CAT[i % len(CAT)] if a.group else PALETTE[4], alpha=0.75, linewidths=0, zorder=3, label=(g if a.group else None))
        for m_, d_ in zip(mm, dd): src.append([g or "all", "point", m_, d_, "", "", "", "", len(mm), "", "", "", ""])
        if a.group:
            sg = ba_stats(xy[:, 0], xy[:, 1]); src.append([g, "summary", "", "", sg["bias"], sg["sd"], sg["lo"], sg["hi"], sg["n"], sg["slope"], sg["s_lo"], sg["s_hi"], sg["prop"]])
    src.append(["all", "summary", "", "", st["bias"], st["sd"], st["lo"], st["hi"], st["n"], st["slope"], st["s_lo"], st["s_hi"], st["prop"]])
    for v, ls_, nm in ((st["bias"], "-", "bias"), (st["hi"], "--", "+1.96 SD"), (st["lo"], "--", "−1.96 SD")):
        ax.axhline(v, ls=ls_, lw=0.8, color=ACCENT if nm == "bias" else "#555", zorder=2)
        ax.annotate(f"{nm} {v:+.2f}{u}".replace("-", "−"), (0.985, v), xycoords=ax.get_yaxis_transform(), xytext=(0, 2.2), textcoords="offset points", ha="right", va="bottom", fontsize=5.8, color="#222", zorder=6, bbox=dict(fc="white", ec="none", alpha=0.7, pad=0.3))
    if st["prop"]:
        mx = (A + Bv) / 2; xs = np.array([mx.min(), mx.max()], float); ax.plot(xs, st["icpt"] + st["slope"] * xs, ls="-.", lw=0.8, color="#2b4c6f", zorder=4, label=f"slope {st['slope']:+.3f} [{st['s_lo']:+.3f}, {st['s_hi']:+.3f}]".replace("-", "−"))
        print(f"[WARN] bland-altman: proportional bias, slope of the difference on the mean {st['slope']:+.4f} (95 % CI {st['s_lo']:+.4f} to {st['s_hi']:+.4f}); constant limits of agreement understate the spread at the ends")
    if a.group or st["prop"]: ax.legend(fontsize=5.8, loc="upper left", handlelength=1.2, labelspacing=0.3, markerscale=1.2)
    ax.set_xlabel(a.xlabel or f"Mean of {a.a} and {a.b}{unit}"); ax.set_ylabel(a.ylabel or f"{a.a} − {a.b}{unit}"); ax.grid(lw=0.4, color="#ececec", zorder=0)
    print(f"bland-altman: n={st['n']}, bias {st['bias']:+.4f}{u}, SD {st['sd']:.4f}, limits {st['lo']:+.4f} to {st['hi']:+.4f}" + (f"; slope {st['slope']:+.4f} [{st['s_lo']:+.4f}, {st['s_hi']:+.4f}]" if not np.isnan(st["slope"]) else ""))
    finish(fig, a, src, ["group", "kind", "mean", "diff", "bias", "sd", "loa_lo", "loa_hi", "n", "slope", "slope_lo", "slope_hi", "proportional_bias"], root,
           f"Bland–Altman plot of {a.a} vs. {a.b}: bias {st['bias']:+.2f}{u} (solid), limits of agreement bias ± 1.96 SD = {st['lo']:+.2f} to {st['hi']:+.2f}{u} (dashed); n = {st['n']}.")


_FULL_CMDS = ("main", "ablation", "seeds", "curves")          # full text width (seeds halves it); every other subcommand is a one-column figure

def default_width_mm(root, kind):
    """print width for --width-mm when it is not given: (mm, where it came from). kind = "full" | "col". From state.target.venue / family via
    references/latex-templates.csv (CVPR: 174.6 / 82.5 mm); without a known venue the historical 183 / 88 mm."""
    full, col, src = 183.0, 88.0, ""
    try:
        import yaml
        st = yaml.safe_load(io.open(os.path.join(root, "research-state.yaml"), encoding="utf-8")) or {}
        tgt = st.get("target") or {}
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import latex_check as lc
        tpl = lc.pick_template(tgt.get("venue") or "", tgt.get("family") or "")
        if tpl:
            full = float(tpl["full_width_mm"]); col = float(tpl["single_col_mm"]) if tpl.get("twocolumn", "").lower() == "yes" else min(88.0, full)
            src = f"state.target.venue {tgt.get('venue') or tgt.get('family')} -> latex-templates.csv row {tpl['key']}"
    except Exception:
        pass
    return (full if kind == "full" else col), src

def resolve_width(a):
    if getattr(a, "width_mm", 0):
        return
    a.width_mm, src = default_width_mm(os.path.abspath(a.project), "full" if a.cmd in _FULL_CMDS else "col")
    if src: print(f"[INFO] width: --width-mm not given, {a.width_mm:g} mm from {src}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("main", "ablation", "seeds", "curves"):
        p = sub.add_parser(n); p.add_argument("--project", default="."); p.add_argument("--out", required=True); p.add_argument("--metrics", default=""); p.add_argument("--labels", default="")
        p.add_argument("--width-mm", type=float, default=0.0, help="print width; default = the target venue's full text width (state.target.venue -> references/latex-templates.csv: CVPR 174.6 mm), 183 without a known venue"); p.add_argument("--height-in", type=float, default=2.6); p.add_argument("--logy", action="store_true"); p.add_argument("--ylabel", default=""); p.add_argument("--ours", default="")
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
            p.add_argument("--letters", action="store_true", help="panel titles '(a) name'"); p.add_argument("--legend", choices=["", "auto", "best", "above", "none"], default="", help="default: auto (inside a free corner, else one row above) when --ema/--inset/--annotate is given, else best")
            p.add_argument("--delta-unit", default="", help="unit written after Δ in the annotation (pp)")
    for n, w in (("stems", 88), ("box", 88), ("hbar", 88)):
        p = sub.add_parser(n); p.add_argument("--project", default="."); p.add_argument("--out", required=True); p.add_argument("--labels", default=""); p.add_argument("--csv", required=True)
        p.add_argument("--width-mm", type=float, default=0.0, help="print width; default = the venue's column width (CVPR 82.5 mm), 88 mm without a known venue"); p.add_argument("--height-in", type=float, default=2.8 if n == "stems" else 0.0, help="box / hbar: default grows with the number of groups")
        p.add_argument("--xlabel", default=""); p.add_argument("--ylabel", default="")
        if n == "stems":
            p.add_argument("--item", required=True, help="column naming the item (backbone)"); p.add_argument("--x", required=True, help="baseline value column"); p.add_argument("--y", required=True, help="ours value column")
            p.add_argument("--group", default="", help="column for colour + marker (family); default: one colour per item")
        else:
            p.add_argument("--value", required=True); p.add_argument("--group", required=True)
        if n == "box": p.add_argument("--whis", default="5,95", help="whisker percentiles"); p.add_argument("--vline", type=float, default=None, help="dashed reference line (0.5 for AUROC)")
        if n == "hbar": p.add_argument("--lower", action="store_true", help="lower is better (only changes which group is flagged best in the source CSV)"); p.add_argument("--fmt", default="{:+.2f}", help="value label format")
    for n in ("roc", "pr", "confusion", "calibration", "bland-altman"):
        p = sub.add_parser(n); p.add_argument("--project", default="."); p.add_argument("--out", required=True); p.add_argument("--csv", required=True)
        p.add_argument("--width-mm", type=float, default=0.0, help="print width; default = the venue's column width (CVPR 82.5 mm), 88 mm without a known venue"); p.add_argument("--height-in", type=float, default={"roc": 3.0, "pr": 3.0, "confusion": 3.1, "calibration": 3.6, "bland-altman": 2.8}[n])
        p.add_argument("--xlabel", default=""); p.add_argument("--ylabel", default="")
        if n in ("roc", "pr"):
            p.add_argument("--y-true", required=True, help="0/1 label column"); p.add_argument("--score", required=True, help="score column (higher = more positive)")
            p.add_argument("--group", default="", help="column naming the method / model: one curve per value"); p.add_argument("--ours", default="", help="group drawn in the accent colour, on top")
            p.add_argument("--ci", default="", help="'bootstrap:200': stratified bootstrap 95 %% band and interval"); p.add_argument("--seed", type=int, default=0)
        elif n == "confusion":
            p.add_argument("--true-col", default="", help="true class column (long rows)"); p.add_argument("--pred-col", default="", help="predicted class column")
            p.add_argument("--labels", default="", help="class names in display order, comma list"); p.add_argument("--normalize", choices=["true", "none"], default="true", help="colour by row share (true) or by count (none); both numbers are always printed")
            p.add_argument("--matrix", action="store_true", help="--csv is a precomputed square table (rows = true, columns = predicted; optional label row / column)")
        elif n == "calibration":
            p.add_argument("--y-true", required=True); p.add_argument("--prob", required=True, help="predicted probability column in [0, 1]"); p.add_argument("--group", default=""); p.add_argument("--ours", default="")
            p.add_argument("--bins", type=int, default=10); p.add_argument("--strategy", choices=["quantile", "uniform"], default="quantile")
        else:
            p.add_argument("--a", required=True, help="first measurement column"); p.add_argument("--b", required=True, help="second measurement column"); p.add_argument("--group", default=""); p.add_argument("--unit", default="")
    for p in sub.choices.values():
        p.add_argument("--synthetic", action="store_true", help="simulated / demo data: draw the SYNTHETIC DEMO watermark and tag figures.csv issues")
        p.add_argument("--no-watermark-check", action="store_true", dest="no_watermark_check", help="skip the data-provenance check (data kept outside results/ and runs/)")
    a = ap.parse_args(); resolve_width(a); {"roc": fig_roc, "pr": fig_pr, "confusion": fig_confusion, "calibration": fig_calibration, "bland-altman": fig_bland_altman, "main": fig_main, "ablation": fig_ablation, "seeds": fig_seeds, "curves": fig_curves, "stems": fig_stems, "box": fig_box, "hbar": fig_hbar}[a.cmd](a)

if __name__ == "__main__":
    main()
