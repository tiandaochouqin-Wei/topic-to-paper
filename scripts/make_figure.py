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
    ticks = {id(t) for ax in fig.axes for t in (*ax.get_xticklabels(), *ax.get_yticklabels(), *ax.get_xticklabels(minor=True), *ax.get_yticklabels(minor=True))}
    axboxes = [(ax, ax.get_window_extent(renderer)) for ax in fig.axes if ax.get_subplotspec() is not None]
    clipped = []
    for t in fig.findobj(_mtext.Text):
        if id(t) in ticks or not t.get_visible() or not t.get_text().strip(): continue
        try: bb = t.get_window_extent(renderer)
        except Exception: continue
        owner = t.axes
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


def fig_curves(a):
    """long CSV -> one line per series, seeds averaged with a band, optional small-multiple panels."""
    root = os.path.abspath(a.project); path = os.path.join(root, a.csv)
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if not rows: print(f"[FAIL] {a.csv} is empty"); sys.exit(1)
    for c in (a.x, a.y):
        if c not in rows[0]: print(f"[FAIL] column {c} not in {a.csv}: {list(rows[0])}"); sys.exit(1)
    labels = dict(kv.split("=", 1) for kv in a.labels.split(",") if "=" in kv) if a.labels else {}
    panels = sorted({r[a.panel] for r in rows}, key=str) if a.panel and a.panel in rows[0] else [None]
    series_all = []
    for r in rows:
        sname = r.get(a.series, "") if a.series else ""
        if sname not in series_all: series_all.append(sname)
    fig, axes = plt.subplots(1, len(panels), figsize=(a.width_mm / 25.4, a.height_in), sharey=not a.logy, squeeze=False); src = []
    for ax, pn in zip(axes[0], panels):
        for i, sname in enumerate(series_all):
            sub = [r for r in rows if (not a.series or r.get(a.series, "") == sname) and (pn is None or r[a.panel] == pn)]
            pts = collections.defaultdict(list)
            for r in sub:
                try: pts[float(r[a.x])].append(float(r[a.y]))
                except ValueError: continue
            if not pts: continue
            xs = np.array(sorted(pts)); ys = np.array([np.mean(pts[x]) for x in xs]); n = max(len(pts[x]) for x in xs)
            col = ACCENT if sname and sname == a.ours else PALETTE[(2 + i) % len(PALETTE)]
            ax.plot(xs, ys, lw=1.1, color=col, label=(labels.get(sname, sname) + (f" (n={n})" if n > 1 else "")) if sname else None, zorder=3)
            if n > 1 and a.band != "none":
                lo = np.array([np.min(pts[x]) if a.band == "minmax" else np.mean(pts[x]) - np.std(pts[x], ddof=1) for x in xs])
                hi = np.array([np.max(pts[x]) if a.band == "minmax" else np.mean(pts[x]) + np.std(pts[x], ddof=1) for x in xs])
                ax.fill_between(xs, lo, hi, color=col, alpha=0.18, lw=0, zorder=2)
            for x, y in zip(xs, ys): src.append([pn if pn is not None else "", sname, x, y, np.std(pts[x], ddof=1) if len(pts[x]) > 1 else 0.0, len(pts[x])])
        if a.logx: ax.set_xscale("log")
        if a.logy: ax.set_yscale("log")
        ax.set_xlabel(a.xlabel or labels.get(a.x, a.x), fontsize=6.8); ax.grid(axis="y", lw=0.4, color="#e6e6e6", zorder=0)
        if pn is not None: ax.set_title(labels.get(pn, pn), fontsize=7.2)
    axes[0][0].set_ylabel(a.ylabel or labels.get(a.y, a.y))
    if a.series: axes[0][-1].legend(fontsize=6.3, loc="best", handlelength=1.2)
    fig.tight_layout(pad=0.3)
    band_txt = {"sd": "shaded band = ± s.d. over seeds", "minmax": "shaded band = min–max over seeds", "none": "single run per series"}[a.band]
    finish(fig, a, src, ["panel", "series", a.x, f"{a.y}_mean", f"{a.y}_sd", "n"], root, f"Curves of {a.y} vs. {a.x}; {band_txt}.")

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
    a = ap.parse_args(); {"main": fig_main, "ablation": fig_ablation, "seeds": fig_seeds, "curves": fig_curves}[a.cmd](a)

if __name__ == "__main__":
    main()
