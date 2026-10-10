# -*- coding: utf-8 -*-
"""P5/P6 — generate the three standard comparison artefacts from results files. Run by Claude.

  python make_comparison.py sota   --csv results/main.csv --out paper/tab_sota.tex [--group-col family] [--ours "SKYDET-T,SKYDET-C"]
                                   [--metrics AP50,AP75,AP50_95] [--higher AP50,AP75,AP50_95] [--lower Params,FLOPs]
                                   [--caption "..."] [--label tab:sota] [--cite-col ref] [--decimals 3] [--md]
  python make_comparison.py multi  --csv results/main.csv --datasets DOTA,AI-TOD,NWPU --dataset-col dataset ...   (one block per dataset side by side)
  python make_comparison.py ablation --csv results/ablation.csv --components DINOv3,SGA,CFE --metrics AP50,AP75,AP50_95 --out paper/tab_ablation.tex
  python make_comparison.py grid   --root figures/det --methods Origin,YOLOv8,...,SKYDET-C --samples img1,img2 --out figures/fig_det_grid.png
                                   [--inset x,y,w,h] [--cols 12] [--width-mm 183]

Conventions (IEEE/TGRS style, matched against SKYDET TGRS 2026 Tables II–V and Fig. 5):
  * best value per metric in \\textcolor{red}, second-best in \\textcolor{blue}; direction per metric via --higher/--lower
  * rows grouped by --group-col with an italic group header line; "ours" rows bold and separated by \\midrule
  * every number formatted to --decimals; the same CSV drives both the .tex and the .md mirror so the two never diverge
  * ablation: components as ✓/✗ columns (\\checkmark / $\\times$), rows numbered, last row (all ✓) bold
  * grid: rows = samples, cols = methods; optional inset crop drawn at 2× in the top-right of each cell; column labels under each row-pair
  * writes <out>.source.csv next to every artefact so numbers.csv can point at it (G6 numbers gate)
"""
import argparse, csv, io, os, sys, math, collections
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

def read_csv(p):
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    return rows, list(rows[0].keys()) if rows else []

def fnum(v, d):
    try: x = float(v)
    except Exception: return str(v) if v not in (None, "") else "--"
    if abs(x) >= 1000: return f"{x:,.0f}"
    return f"{x:.{d}f}"

def rank_marks(rows, metric, higher):
    """-> {row_index: 'best'|'second'}; ties share a mark."""
    vals = []
    for i, r in enumerate(rows):
        try: vals.append((float(r[metric]), i))
        except Exception: pass
    if len(vals) < 2: return {}
    vals.sort(reverse=higher)
    marks = {}; distinct = sorted({v for v, _ in vals}, reverse=higher)
    for v, i in vals:
        if v == distinct[0]: marks[i] = "best"
        elif len(distinct) > 1 and v == distinct[1]: marks[i] = "second"
    return marks

def tex_cell(s, mark, bold):
    if mark == "best": s = r"\textcolor{red}{" + s + "}"
    elif mark == "second": s = r"\textcolor{blue}{" + s + "}"
    if bold: s = r"\textbf{" + s + "}"
    return s

def md_cell(s, mark, bold):
    if mark == "best": s = f"**{s}**"
    elif mark == "second": s = f"_{s}_"
    return s

def esc(s): return str(s).replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")

LABELS = {}   # column -> display label, filled from --labels "AP50=AP$_{50}$,AP50_95=AP$_{50:95}$"
def lab(c): return LABELS.get(c, esc(c))
def lab_md(c): return LABELS.get(c, c).replace("$", "")

# ------------------------------------------------------------------ sota / multi
def sota_table(rows, cols, a, datasets=None):
    metrics = a.metrics.split(","); higher = set(a.higher.split(",")) if a.higher else set(metrics); lower = set(a.lower.split(",")) if a.lower else set()
    extra = [c for c in (a.extra.split(",") if a.extra else []) if c in cols]
    ours = [o.strip() for o in a.ours.split(",")] if a.ours else []
    name_col = a.name_col
    blocks = [(None, rows)] if not datasets else [(d, [r for r in rows if r.get(a.dataset_col) == d]) for d in datasets]
    # column spec
    ncol = 1 + len(extra) + sum(len(metrics) for _ in blocks)
    spec = "l" + "c" * len(extra) + "".join("|" + "c" * len(metrics) for _ in blocks) if datasets else "l" + "c" * (len(extra) + len(metrics))
    L = [r"\begin{table" + ("*" if datasets and len(blocks) > 1 else "") + "}[t]", r"\centering", r"\caption{" + a.caption + "}", r"\label{" + a.label + "}", r"\small", r"\begin{tabular}{" + spec + "}", r"\toprule"]
    M = []
    if datasets:
        L.append(r"\multirow{2}{*}{\textbf{Model}}" + "".join(" & " for _ in extra) + "".join(r" & \multicolumn{%d}{c}{\textbf{%s}}" % (len(metrics), esc(d)) for d, _ in blocks) + r" \\")
        L.append(" ".join(r"\cmidrule(lr){%d-%d}" % (2 + len(extra) + i * len(metrics), 1 + len(extra) + (i + 1) * len(metrics)) for i in range(len(blocks))))
        L.append(" & ".join([""] + [lab(e) for e in extra] + [lab(m) for _ in blocks for m in metrics]) + r" \\")
        M.append("| Model | " + " | ".join([lab_md(e) for e in extra] + [f"{d} {lab_md(m)}" for d, _ in blocks for m in metrics]) + " |"); M.append("|---|" + "---|" * (len(extra) + len(metrics) * len(blocks)))
    else:
        L.append(r"\textbf{Model} & " + " & ".join([r"\textbf{%s}" % lab(e) for e in extra] + [lab(m) for m in metrics]) + r" \\")
        M.append("| Model | " + " | ".join([lab_md(e) for e in extra] + [lab_md(m) for m in metrics]) + " |"); M.append("|---|" + "---|" * (len(extra) + len(metrics)))
    L.append(r"\midrule")
    # row order = order of first block, grouped
    base = blocks[0][1]
    names = []
    for r in base:
        if r[name_col] not in names: names.append(r[name_col])
    groups = collections.OrderedDict()
    for r in base: groups.setdefault(r.get(a.group_col, "") if a.group_col else "", []).append(r[name_col])
    # marks per (block, metric) computed over non-ours and ours together (paper convention: ours can be best)
    marks = {}
    for bi, (d, brows) in enumerate(blocks):
        by_name = {r[name_col]: r for r in brows}
        ordered = [by_name[n] for n in names if n in by_name]
        for m in metrics:
            mk = rank_marks(ordered, m, m in higher and m not in lower)
            for i, r in enumerate(ordered): marks[(bi, r[name_col], m)] = mk.get(i)
    src = []
    first_group = True
    for g, members in groups.items():
        if g:
            if not first_group: L.append(r"\midrule")
            L.append(r"\multicolumn{%d}{l}{\textit{%s}} \\" % (ncol, esc(g))); M.append(f"| *{g}* |" + " |" * (len(extra) + len(metrics) * len(blocks)))
        first_group = False
        non_ours = [n for n in members if n not in ours]; ours_here = [n for n in members if n in ours]
        for n in non_ours + ours_here:
            if n == ours_here[0] if ours_here else False: L.append(r"\midrule")
            r0 = next(r for r in base if r[name_col] == n); bold = n in ours
            cite = (" [" + esc(r0[a.cite_col]) + "]") if a.cite_col and r0.get(a.cite_col) else ""
            cite_tex = (r"~\cite{" + r0[a.cite_col] + "}") if a.cite_col and r0.get(a.cite_col) else ""
            cells_t = [(r"\textbf{" + esc(n) + "}" if bold else esc(n)) + cite_tex] + [esc(r0.get(e, "") or "--") for e in extra]   # extra columns are quoted verbatim (Params 258.2 stays 258.2)
            cells_m = [("**" + n + "**" if bold else n) + cite] + [(r0.get(e, "") or "--") for e in extra]
            for bi, (d, brows) in enumerate(blocks):
                rr = next((r for r in brows if r[name_col] == n), None)
                for m in metrics:
                    v = fnum(rr.get(m, "") if rr else "", a.decimals); mk = marks.get((bi, n, m))
                    cells_t.append(tex_cell(v, mk, bold)); cells_m.append(md_cell(v, mk, bold))
                    src.append([d or "", n, m, rr.get(m, "") if rr else ""])
            L.append(" & ".join(cells_t) + r" \\"); M.append("| " + " | ".join(cells_m) + " |")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table" + ("*" if datasets and len(blocks) > 1 else "") + "}"]
    return "\n".join(L), "\n".join(M), src

# ------------------------------------------------------------------ ablation
def ablation_table(rows, a):
    comps = a.components.split(","); metrics = a.metrics.split(","); higher = set(a.higher.split(",")) if a.higher else set(metrics)
    def on(v): return str(v).strip().lower() in ("1", "true", "yes", "y", "✓", "on")
    spec = "c|" + "c" * len(comps) + "|" + "c" * len(metrics)
    L = [r"\begin{table}[t]", r"\centering", r"\caption{" + a.caption + "}", r"\label{" + a.label + "}", r"\small", r"\begin{tabular}{" + spec + "}", r"\toprule",
         r"\multirow{2}{*}{\textbf{Group}} & " + " & ".join(r"\multirow{2}{*}{\textbf{%s}}" % esc(c) for c in comps) + r" & \multicolumn{%d}{c}{\textbf{Performance}} \\" % len(metrics),
         r"\cmidrule(lr){%d-%d}" % (2 + len(comps), 1 + len(comps) + len(metrics)),
         " & ".join([""] * (1 + len(comps)) + [lab(m) for m in metrics]) + r" \\", r"\midrule"]
    M = ["| Group | " + " | ".join(comps + [lab_md(m) for m in metrics]) + " |", "|---|" + "---|" * (len(comps) + len(metrics))]
    full = [i for i, r in enumerate(rows) if all(on(r.get(c, "")) for c in comps)]
    marks = {m: rank_marks(rows, m, m in higher) for m in metrics}
    src = []
    for i, r in enumerate(rows):
        bold = i in full
        ct = [str(i + 1)] + [(r"\checkmark" if on(r.get(c, "")) else r"$\times$") for c in comps]
        cm = [str(i + 1)] + [("✓" if on(r.get(c, "")) else "✗") for c in comps]
        for m in metrics:
            v = fnum(r.get(m, ""), a.decimals); mk = marks[m].get(i)
            ct.append(tex_cell(v, None if a.ablation_plain else mk, bold)); cm.append(md_cell(v, None if a.ablation_plain else mk, bold)); src.append(["", f"group{i+1}", m, r.get(m, "")])
        if bold: ct = [r"\textbf{" + c + "}" if not c.startswith("\\") else c for c in ct]; cm = ["**" + c + "**" if c.replace(".", "").isdigit() else c for c in cm]
        L.append(" & ".join(ct) + r" \\"); M.append("| " + " | ".join(cm) + " |")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(L), "\n".join(M), src

# ------------------------------------------------------------------ seeds (Table VII style: per-seed values + mean ± std per setting)
def seeds_table(rows, a):
    """CSV long form: setting,seed,<metric>. One row per setting; columns = seeds..., Mean ± Std. Best mean in bold."""
    import statistics
    metric = a.metrics.split(",")[0]
    settings = collections.OrderedDict()
    for r in rows: settings.setdefault(r[a.setting_col], []).append((r[a.seed_col], float(r[metric])))
    seeds = []
    for v in settings.values():
        for s, _ in v:
            if s not in seeds: seeds.append(s)
    stats = {k: (statistics.mean(x for _, x in v), statistics.stdev(x for _, x in v) if len(v) > 1 else 0.0, len(v)) for k, v in settings.items()}
    best = max(stats, key=lambda k: stats[k][0])
    d = a.decimals
    L = [r"\begin{table}[t]", r"\centering", r"\caption{" + a.caption + "}", r"\label{" + a.label + "}", r"\small", r"\begin{tabular}{l" + "c" * len(seeds) + "|c}", r"\toprule",
         r"\textbf{Setting} & " + " & ".join(r"\textbf{Seed %s}" % esc(s) for s in seeds) + r" & \textbf{Mean $\pm$ Std} \\", r"\midrule"]
    M = ["| Setting | " + " | ".join(f"Seed {s}" for s in seeds) + " | Mean ± Std |", "|---|" + "---|" * (len(seeds) + 1)]
    src = []
    for k, v in settings.items():
        by = dict(v); m, s, n = stats[k]; bold = k == best
        cells = [fnum(by.get(sd, ""), d) for sd in seeds] + [f"{m:.{d}f} $\\pm$ {s:.{d}f}"]
        cm = [fnum(by.get(sd, ""), d) for sd in seeds] + [f"{m:.{d}f} ± {s:.{d}f}"]
        if bold: cells = [r"\textbf{" + c + "}" for c in cells]; cm = ["**" + c + "**" for c in cm]
        L.append((r"\textbf{" + esc(k) + "}" if bold else esc(k)) + " & " + " & ".join(cells) + r" \\")
        M.append("| " + ("**" + k + "**" if bold else k) + " | " + " | ".join(cm) + " |")
        for sd in seeds: src.append(["", k, f"{metric}@seed{sd}", by.get(sd, "")])
        src += [["", k, f"{metric}_mean", m], ["", k, f"{metric}_std", s], ["", k, "n_seeds", n]]
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(L), "\n".join(M), src

def emit_numbers(src, src_csv, out_dir, decimals):
    """Append one provenance row per cell to paper/numbers.csv (G6 numbers gate) — value as printed, key = selector into <out>.source.csv.
    Existing rows for the same source file are replaced so re-running the generator never duplicates."""
    nm = os.path.join(out_dir, "numbers.csv"); rel = os.path.relpath(src_csv, os.getcwd()).replace("\\", "/")
    old = [r for r in csv.DictReader(open(nm, encoding="utf-8"))] if os.path.exists(nm) else []
    old = [r for r in old if r["file"].replace("\\", "/") != rel]
    new = []
    for ds, mth, met, val in src:
        try: v = float(val)
        except Exception: continue
        d = decimals if "." in str(val) or isinstance(val, float) else 0
        new.append({"value": f"{v:.{d}f}" if d else str(int(v)), "file": rel, "key": f"dataset={ds}|method={mth}|metric={met},value", "transform": ""})
    with open(nm, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["value", "file", "key", "transform"]); w.writeheader(); w.writerows(old + new)
    return len(new), nm

def det_grid(a):
    from PIL import Image, ImageDraw, ImageFont
    methods = a.methods.split(","); samples = a.samples.split(","); cols = a.cols or len(methods)
    nrow_groups = math.ceil(len(methods) / cols)
    pad = 4
    cell = a.cell_px or math.ceil((a.dpi * a.width_mm / 25.4 - pad) / cols) - pad   # auto: hit --dpi at print width
    fs = max(14, int(cell * 0.085)); lab_h = int(fs * 1.7)
    W = cols * (cell + pad) + pad; H = nrow_groups * (len(samples) * (cell + pad) + lab_h) + pad
    canvas = Image.new("RGB", (W, H), "white"); draw = ImageDraw.Draw(canvas)
    try: font = ImageFont.truetype("times.ttf", fs)
    except Exception: font = ImageFont.load_default()
    inset = [float(x) for x in a.inset.split(",")] if a.inset else None   # fractions x,y,w,h of the source image
    missing = []
    for gi in range(nrow_groups):
        chunk = methods[gi * cols:(gi + 1) * cols]
        for ci, mth in enumerate(chunk):
            for si, smp in enumerate(samples):
                p = next((os.path.join(a.root, mth, smp + ext) for ext in ("", ".png", ".jpg", ".jpeg") if os.path.exists(os.path.join(a.root, mth, smp + ext))), None)
                x0 = pad + ci * (cell + pad); y0 = pad + gi * (len(samples) * (cell + pad) + lab_h) + si * (cell + pad)
                if not p:
                    missing.append(f"{mth}/{smp}"); draw.rectangle([x0, y0, x0 + cell, y0 + cell], outline="#999"); continue
                im = Image.open(p).convert("RGB"); im = im.resize((cell, cell), Image.LANCZOS); canvas.paste(im, (x0, y0))
                if inset:
                    src = Image.open(p).convert("RGB"); sw, sh = src.size
                    box = (int(inset[0] * sw), int(inset[1] * sh), int((inset[0] + inset[2]) * sw), int((inset[1] + inset[3]) * sh))
                    crop = src.crop(box); isz = int(cell * 0.42); crop = crop.resize((isz, isz), Image.LANCZOS)
                    canvas.paste(crop, (x0 + cell - isz - 2, y0 + 2)); draw.rectangle([x0 + cell - isz - 2, y0 + 2, x0 + cell - 2, y0 + 2 + isz], outline="white", width=2)
                    draw.rectangle([x0 + int(inset[0] * cell), y0 + int(inset[1] * cell), x0 + int((inset[0] + inset[2]) * cell), y0 + int((inset[1] + inset[3]) * cell)], outline="white", width=1)
            tw = draw.textlength(mth, font=font); draw.text((x0 + (cell - tw) / 2, y0 + cell + 4), mth, fill="black", font=font)
    canvas.save(a.out)
    dpi = canvas.size[0] / (a.width_mm / 25.4)
    pdf = os.path.splitext(a.out)[0] + ".pdf"; canvas.save(pdf, "PDF", resolution=dpi)   # LaTeX includes the PDF; the PNG is for inspection
    print(f"-> {pdf} (same raster, {dpi:.0f} dpi at {a.width_mm} mm)")
    print(f"grid {canvas.size} -> {dpi:.0f} dpi at {a.width_mm} mm; cells {len(methods)}×{len(samples)}" + (f"; MISSING {len(missing)}: {missing[:6]}" if missing else ""))
    return dpi

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("sota", "multi", "ablation", "seeds"):
        p = sub.add_parser(n); p.add_argument("--csv", required=True); p.add_argument("--out", required=True); p.add_argument("--metrics", required=True)
        p.add_argument("--higher", default=""); p.add_argument("--lower", default=""); p.add_argument("--caption", default="Caption."); p.add_argument("--label", default="tab:x"); p.add_argument("--decimals", type=int, default=3); p.add_argument("--md", action="store_true")
        p.add_argument("--numbers", action="store_true", help="also register every cell in <out-dir>/numbers.csv for the G6 numbers gate")
        if n in ("sota", "multi"):
            p.add_argument("--name-col", default="method"); p.add_argument("--group-col", default=""); p.add_argument("--ours", default=""); p.add_argument("--extra", default="", help="non-ranked columns e.g. Params,FLOPs"); p.add_argument("--cite-col", default="")
        if n == "multi": p.add_argument("--datasets", required=True); p.add_argument("--dataset-col", default="dataset")
        if n == "ablation": p.add_argument("--components", required=True); p.add_argument("--ablation-plain", action="store_true", help="no red/blue, only bold full row")
        if n == "seeds": p.add_argument("--setting-col", default="setting"); p.add_argument("--seed-col", default="seed")
    g = sub.add_parser("grid"); g.add_argument("--root", required=True); g.add_argument("--methods", required=True); g.add_argument("--samples", required=True); g.add_argument("--out", required=True)
    g.add_argument("--inset", default=""); g.add_argument("--cols", type=int, default=0); g.add_argument("--width-mm", type=float, default=183); g.add_argument("--cell-px", type=int, default=0, help="0 = auto from --dpi"); g.add_argument("--dpi", type=float, default=400)
    ap.add_argument("--labels", default="", help='display labels, e.g. "AP50=AP$_{50}$,AP50_95=AP$_{50:95}$"')
    a = ap.parse_args()
    for kv in filter(None, a.labels.split(",")):
        k, v = kv.split("=", 1); LABELS[k] = v
    if a.cmd == "grid": return det_grid(a)
    rows, cols = read_csv(a.csv)
    if a.cmd == "ablation": tex, md, src = ablation_table(rows, a)
    elif a.cmd == "seeds": tex, md, src = seeds_table(rows, a)
    else: tex, md, src = sota_table(rows, cols, a, datasets=a.datasets.split(",") if a.cmd == "multi" else None)
    io.open(a.out, "w", encoding="utf-8").write(tex + "\n")
    if a.md: io.open(os.path.splitext(a.out)[0] + ".md", "w", encoding="utf-8").write(md + "\n")
    src_csv = os.path.splitext(a.out)[0] + ".source.csv"
    with open(src_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["dataset", "method", "metric", "value"]); w.writerows(src)
    print(f"{a.out}: {len(rows)} rows, {len(src)} cells; source -> {src_csv}" + ("; md mirror written" if a.md else ""))
    if a.numbers:
        n, nm = emit_numbers(src, src_csv, os.path.dirname(a.out) or ".", a.decimals); print(f"numbers: {n} rows registered in {nm}")
    print(md)

if __name__ == "__main__":
    main()
