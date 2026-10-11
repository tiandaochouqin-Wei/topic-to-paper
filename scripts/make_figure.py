# -*- coding: utf-8 -*-
"""P5 — standard data figures from the results tables, so main/ablation figures are generated, not hand-drawn. Run by Claude.

  python make_figure.py main     --project . --out figures/fig_main.png [--metrics rmse_E1,rmse_E2,...] [--labels "rmse_E1=E1 in-dom."] [--logy]
                                 [--ours ours] [--width-mm 183] [--height-in 2.6] [--ylabel "..."]
      grouped bars: x = metric columns (conditions), one bar per method; multi-seed methods -> mean ± s.d. with per-seed dots; ours in accent colour
  python make_figure.py ablation --project . --out figures/fig_abl.png [--metrics ...] [--labels ...]
      Δ vs reference per metric, grey ±2σ_ref√2 band (seed noise), bars inside the band greyed (not resolvable); index row + legend of ablation names
  python make_figure.py seeds    --project . --out figures/fig_seeds.png --methods ours,RCNN [--metrics ...]
      mean ± s.d. with per-seed dots for the named methods only (Table-IV-style stability figure)

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
                     "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False})
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

def finish(fig, a, src_rows, src_hdr, root, caption):
    out = os.path.join(root, a.out); os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fig.savefig(out, dpi=400, bbox_inches="tight"); fig.savefig(os.path.splitext(out)[0] + ".pdf", bbox_inches="tight")
    from PIL import Image
    w = Image.open(out).size[0]; dpi = w / (a.width_mm / 25.4)
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
    if "issues" in hdr: new["issues"] = "auto: " + caption
    rows.append(new)
    with open(fp, "w", newline="", encoding="utf-8") as f: wr = csv.DictWriter(f, fieldnames=hdr); wr.writeheader(); wr.writerows(rows)
    print(f"{rel}: {w}px -> {dpi:.0f} dpi @ {a.width_mm} mm; source {os.path.basename(sp)}; figures.csv updated (inspected=no → 裁图目测后改 yes)")

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
    if a.logy: ax.set_yscale("log")
    ax.set_xticks(x); ax.set_xticklabels([labels.get(m, m) for m in metrics], fontsize=6.8); ax.set_ylabel(a.ylabel or res.get("primary_metric", "")); ax.grid(axis="y", lw=0.4, color="#e6e6e6", zorder=0)
    ax.legend(ncol=min(3, len(methods)), fontsize=6.3, loc="upper left", handlelength=1.0, columnspacing=0.8)
    finish(fig, a, src, ["method", "metric", "mean", "sd", "n"], root, "Main comparison: mean ± s.d. over seeds where n>1; dots = individual seeds.")

def fig_ablation(a):
    root, res, main, abl, gk, ref, metrics, labels = load(a)
    if not abl: print("[FAIL] no ablation table"); sys.exit(1)
    refarr = by_method(main, gk, metrics).get(ref)
    if refarr is None or refarr.shape[0] < 2: print(f"[FAIL] reference {ref} needs ≥2 seeds in main.csv for the noise band"); sys.exit(1)
    ref_m = np.nanmean(refarr, 0); band = 2 * np.nanstd(refarr, 0, ddof=1) * np.sqrt(2)
    names = []; vals = []
    for r in abl:
        n = r.get("ablation") or r.get(gk); names.append(n); vals.append([float(r[m]) if r.get(m, "") != "" else np.nan for m in metrics])
    vals = np.array(vals); fig, ax = plt.subplots(figsize=(a.width_mm / 25.4, a.height_in)); x = np.arange(len(metrics)); w = 0.8 / len(names); src = []
    ax.bar(x, 2 * band, 0.86, bottom=-band, color="#f0f0f0", edgecolor="none", zorder=0, label="±2σ_ref√2 seed noise")
    for i, n in enumerate(names):
        d = vals[i] - ref_m; resolv = np.abs(d) >= band
        xx = x + (i - (len(names) - 1) / 2) * w
        ax.bar(xx, d, w, color=[ACCENT if r else "#c9c9c9" for r in resolv], edgecolor="none", zorder=3)
        for j in range(len(metrics)):
            ax.text(xx[j], -0.02, str(i + 1), ha="center", va="top", fontsize=5.2, color="#444", transform=ax.get_xaxis_transform(), clip_on=False)   # index row just below the axis
            src.append([n, metrics[j], d[j], band[j], bool(resolv[j])])
    ax.axhline(0, lw=0.6, color="#333"); ax.set_xticks(x); ax.set_xticklabels([labels.get(m, m) for m in metrics], fontsize=6.8)
    ax.set_ylabel(a.ylabel or f"Δ {labels.get(res.get('primary_metric',''), res.get('primary_metric',''))} vs. {ref}"); ax.tick_params(axis="x", pad=9); ax.text(0.01, 0.98, "\n".join(f"{i+1}: {n}" for i, n in enumerate(names)), transform=ax.transAxes, fontsize=5.6, va="top", color="#333")
    ax.text(0.99, 0.02, "grey bar: within seed noise\n(not resolvable, single run)", transform=ax.transAxes, fontsize=5.6, ha="right", va="bottom", color="#555")
    finish(fig, a, src, ["ablation", "metric", "delta", "band", "resolvable"], root, f"Ablation Δ vs. {ref}; grey band = ±2σ√2 seed noise of the reference; grey bars not resolvable.")

def fig_seeds(a):
    root, res, main, abl, gk, ref, metrics, labels = load(a)
    data = by_method(main, gk, metrics); methods = [m for m in (a.methods.split(",") if a.methods else [ref]) if m in data]
    fig, ax = plt.subplots(figsize=(a.width_mm / 25.4 * 0.5, a.height_in)); x = np.arange(len(metrics)); src = []
    for i, m in enumerate(methods):
        arr = data[m]; mean = np.nanmean(arr, 0); sd = np.nanstd(arr, 0, ddof=1) if arr.shape[0] > 1 else np.zeros(len(metrics)); off = (i - (len(methods) - 1) / 2) * 0.3
        col = ACCENT if m == ref else PALETTE[3 + i % 3]
        ax.errorbar(x + off, mean, yerr=sd, fmt="o", ms=3, color=col, ecolor=col, elinewidth=0.8, capsize=2, label=f"{m} (n={arr.shape[0]})", zorder=3)
        for j in range(len(metrics)): ax.scatter(np.full(arr.shape[0], x[j] + off), arr[:, j], s=5, color=col, alpha=0.45, zorder=2, linewidths=0); src.append([m, metrics[j], mean[j], sd[j], arr.shape[0]])
    if a.logy: ax.set_yscale("log")
    ax.set_xticks(x); ax.set_xticklabels([labels.get(m, m) for m in metrics], fontsize=6.8); ax.set_ylabel(a.ylabel or f"{res.get('primary_metric','')}, mean ± s.d."); ax.grid(axis="y", lw=0.4, color="#e6e6e6", zorder=0); ax.legend(fontsize=6.3, loc="upper left", handlelength=1.0)
    a.width_mm = a.width_mm * 0.5
    finish(fig, a, src, ["method", "metric", "mean", "sd", "n"], root, "Seed stability: mean ± s.d., dots = seeds.")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("main", "ablation", "seeds"):
        p = sub.add_parser(n); p.add_argument("--project", default="."); p.add_argument("--out", required=True); p.add_argument("--metrics", default=""); p.add_argument("--labels", default="")
        p.add_argument("--width-mm", type=float, default=183); p.add_argument("--height-in", type=float, default=2.6); p.add_argument("--logy", action="store_true"); p.add_argument("--ylabel", default=""); p.add_argument("--ours", default="")
        if n == "seeds": p.add_argument("--methods", default="")
    a = ap.parse_args(); {"main": fig_main, "ablation": fig_ablation, "seeds": fig_seeds}[a.cmd](a)

if __name__ == "__main__":
    main()
