# -*- coding: utf-8 -*-
"""P5/P6 — generate the three standard comparison artefacts from results files. Run by Claude.

  python make_comparison.py sota   --csv results/main.csv --out paper/tab_sota.tex [--group-col family] [--ours "SKYDET-T,SKYDET-C"]
                                   [--metrics AP50,AP75,AP50_95] [--higher AP50,AP75,AP50_95] [--lower Params,FLOPs]
                                   [--caption "..."] [--label tab:sota] [--cite-col ref] [--decimals 3] [--md]
  python make_comparison.py multi  --csv results/main.csv --datasets DOTA,AI-TOD,NWPU --dataset-col dataset ...   (one block per dataset side by side)
  python make_comparison.py ablation --csv results/ablation.csv --components DINOv3,SGA,CFE --metrics AP50,AP75,AP50_95 --out paper/tab_ablation.tex
  python make_comparison.py grid   --root figures/det --methods Origin,YOLOv8,...,SKYDET-C --samples img1,img2 --out figures/fig_det_grid.png
                                   [--inset x,y,w,h] [--cols 12] [--width-mm 183] [--dpi 400] [--project .]
                                   [--row-labels "M3FD,LLVIP"|none] [--col-labels ...] [--label-pos bottom|top] [--highlight Ours[,..]] [--marks marks.csv]
                                   [--labels-dir L --label-fmt yolo|coco|voc|xyxy --gt-col GT --class-names a,b --box-lw 0]
                                   [--overlay-dir O --overlay-alpha 0.55 --cmap jet|magma|viridis --colorbar "Low,High"|none]
                                   [--mask-dir M --palette 6 --mask-alpha 0.6]

Conventions (IEEE/TGRS style, matched against SKYDET TGRS 2026 Tables II–V and Fig. 5):
  * best value per metric in \\textcolor{red}, second-best in \\textcolor{blue}; direction per metric: --lower > --higher (unlisted = lower)
    > research-state.yaml results.metric_direction / primary_direction (with --project) > name regex (metric_direction.py) > higher
  * rows grouped by --group-col with an italic group header line; "ours" rows bold and separated by \\midrule
  * every number formatted to --decimals; the same CSV drives both the .tex and the .md mirror so the two never diverge
  * ablation: components as ✓/✗ columns (\\checkmark / $\\times$), rows numbered, last row (all ✓) bold
  * grid: rows = samples, cols = methods; optional inset crop drawn at 2× in the top-right of each cell; column labels under each row group (--label-pos top
    puts them above, Fig.-4 style). Per cell <dir>/<method>/<sample>: boxes (green in --gt-col, accent elsewhere, ≥0.4 pt printed), CAM overlay with one
    shared colorbar, class-id mask in a fixed palette, accent ellipses (--marks), accent frame round --highlight columns. Photos = one raster at --dpi
    over --width-mm, embedded in the PDF (G5 counts a .pdf as vector and checks the .png row: 400 dpi at --width-mm); labels / frames / boxes are vector.
    A CAM or mask column without its own image sits on the --gt-col image of the same sample. .source.csv: one row per cell (image, overlay, n_boxes, ...)
  * writes <out>.source.csv next to every artefact so numbers.csv can point at it (G6 numbers gate)
"""
import argparse, csv, io, json, os, re, sys, math, collections
import xml.etree.ElementTree as ET
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import metric_direction as mdir
STATE = {}   # research-state.yaml results block, filled from --project
def higher_for(m, a):
    lower = set(filter(None, a.lower.split(","))); higher = set(filter(None, a.higher.split(",")))
    if m in lower: return False
    if m in higher: return True
    if higher: return False   # --higher lists the higher-is-better metrics; the rest are lower
    return not mdir.lower_is_better(m, STATE)

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

def _esc_plain(t): return t.replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")
def esc(s):
    """LaTeX-escape & % _ outside $...$; inline math (a row name with a delta or K_{cal} in it) passes through untouched."""
    return "".join(p if (len(p) > 1 and p.startswith("$") and p.endswith("$")) else _esc_plain(p) for p in re.split(r"(\$[^$]*\$)", str(s)))

LABELS = {}   # column -> display label, filled from --labels "AP50=AP$_{50}$,AP50_95=AP$_{50:95}$"
def lab(c): return LABELS.get(c, esc(c))
def lab_md(c): return LABELS.get(c, c).replace("$", "")
DLABELS = {}   # dataset value -> display label, filled from --dataset-labels "prostate_t1=Prostate ($K{=}6$),..."
def dlab(d): return DLABELS.get(d, esc(d))
def dlab_md(d): return DLABELS.get(d, d).replace("$", "")

# ------------------------------------------------------------------ sota / multi
def sota_table(rows, cols, a, datasets=None):
    metrics = a.metrics.split(",")
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
        L.append(r"\multirow{2}{*}{\textbf{Model}}" + "".join(" & " for _ in extra) + "".join(r" & \multicolumn{%d}{c}{\textbf{%s}}" % (len(metrics), dlab(d)) for d, _ in blocks) + r" \\")
        L.append(" ".join(r"\cmidrule(lr){%d-%d}" % (2 + len(extra) + i * len(metrics), 1 + len(extra) + (i + 1) * len(metrics)) for i in range(len(blocks))))
        L.append(" & ".join([""] + [lab(e) for e in extra] + [lab(m) for _ in blocks for m in metrics]) + r" \\")
        M.append("| Model | " + " | ".join([lab_md(e) for e in extra] + [f"{dlab_md(d)} {lab_md(m)}" for d, _ in blocks for m in metrics]) + " |"); M.append("|---|" + "---|" * (len(extra) + len(metrics) * len(blocks)))
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
            mk = rank_marks(ordered, m, higher_for(m, a))
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
    comps = a.components.split(","); metrics = a.metrics.split(",")
    def on(v): return str(v).strip().lower() in ("1", "true", "yes", "y", "✓", "on")
    spec = "c|" + "c" * len(comps) + "|" + "c" * len(metrics)
    L = [r"\begin{table}[t]", r"\centering", r"\caption{" + a.caption + "}", r"\label{" + a.label + "}", r"\small", r"\begin{tabular}{" + spec + "}", r"\toprule",
         r"\multirow{2}{*}{\textbf{Group}} & " + " & ".join(r"\multirow{2}{*}{\textbf{%s}}" % esc(c) for c in comps) + r" & \multicolumn{%d}{c}{\textbf{Performance}} \\" % len(metrics),
         r"\cmidrule(lr){%d-%d}" % (2 + len(comps), 1 + len(comps) + len(metrics)),
         " & ".join([""] * (1 + len(comps)) + [lab(m) for m in metrics]) + r" \\", r"\midrule"]
    M = ["| Group | " + " | ".join(comps + [lab_md(m) for m in metrics]) + " |", "|---|" + "---|" * (len(comps) + len(metrics))]
    full = [i for i, r in enumerate(rows) if all(on(r.get(c, "")) for c in comps)]
    marks = {m: rank_marks(rows, m, higher_for(m, a)) for m in metrics}
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
    """CSV long form: setting,seed,<metric>. One row per setting; columns = seeds..., Mean ± Std. Best mean in bold (lowest for lower-is-better metrics, see higher_for)."""
    import statistics
    metric = a.metrics.split(",")[0]
    settings = collections.OrderedDict()
    for r in rows: settings.setdefault(r[a.setting_col], []).append((r[a.seed_col], float(r[metric])))
    seeds = []
    for v in settings.values():
        for s, _ in v:
            if s not in seeds: seeds.append(s)
    stats = {k: (statistics.mean(x for _, x in v), statistics.stdev(x for _, x in v) if len(v) > 1 else 0.0, len(v)) for k, v in settings.items()}
    best = (max if higher_for(metric, a) else min)(stats, key=lambda k: stats[k][0])
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

GT_COLOR = "#2ca25f"   # ground-truth boxes; every other column's boxes use make_figure.ACCENT
CLASS_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080",
                "#e6beff", "#9a6324", "#fffac8", "#800000", "#aaffc3", "#808000", "#ffd8b1", "#000075", "#808080", "#ffe119"]   # fixed categorical palette for --mask-dir (class 0 = background, left unpainted)
IMG_EXT = ("", ".png", ".jpg", ".jpeg")
LABEL_EXT = {"yolo": (".txt",), "xyxy": (".txt",), "coco": (".json",), "voc": (".xml", ".txt")}

def _find(d, mth, smp, exts):
    for e in exts:
        p = os.path.join(d, mth, smp + e)
        if os.path.isfile(p): return p
    return None

def read_boxes(path, fmt, iw, ih):
    """-> [(label, x0, y0, x1, y1)] in 0-1 image coordinates. yolo: 'cls cx cy w h' normalised; xyxy / voc txt: 'cls x1 y1 x2 y2 [score]' in pixels
    (taken as 0-1 when every coordinate <= 1.5); coco: json list (or {'annotations': [...]}) of {'bbox': [x, y, w, h], 'category_id'} in pixels; voc: Pascal VOC xml."""
    raw = []   # (label, x0, y0, x1, y1, is_pixel)
    if path.lower().endswith(".json"):
        d = json.load(open(path, encoding="utf-8"))
        for it in (d if isinstance(d, list) else d.get("annotations") or d.get("boxes") or d.get("detections") or []):
            bb, cls = (it.get("bbox"), it.get("category_id", it.get("category", it.get("label", "")))) if isinstance(it, dict) else (it[:4], "")
            x, y, w, h = map(float, bb); raw.append((str(cls), x, y, x + w, y + h, True))
    elif path.lower().endswith(".xml"):
        for ob in ET.parse(path).getroot().iter("object"):
            bb = ob.find("bndbox")
            if bb is not None: raw.append((ob.findtext("name", ""), *[float(bb.findtext(k, "0")) for k in ("xmin", "ymin", "xmax", "ymax")], True))
    else:
        for ln in io.open(path, encoding="utf-8"):
            t = ln.split()
            if len(t) < 5: continue
            v = [float(x) for x in t[1:5]]
            if fmt == "yolo": raw.append((t[0], v[0] - v[2] / 2, v[1] - v[3] / 2, v[0] + v[2] / 2, v[1] + v[3] / 2, False))
            else: raw.append((t[0], *v, max(v) > 1.5))
    out = []
    for c, x0, y0, x1, y1, pix in raw:
        if pix: x0, x1, y0, y1 = x0 / iw, x1 / iw, y0 / ih, y1 / ih
        out.append((c, max(0.0, min(x0, x1)), max(0.0, min(y0, y1)), min(1.0, max(x0, x1)), min(1.0, max(y0, y1))))
    return out

def _fit(fig, txt, max_px, along="x", lo=5.2):
    """shrink a text artist (pt) until its box fits max_px; False when even the floor size overflows"""
    r = fig.canvas.get_renderer()
    while True:
        bb = txt.get_window_extent(r); ext = bb.width if along == "x" else bb.height
        if ext <= max_px: return True
        if txt.get_fontsize() <= lo + 1e-6: return False
        txt.set_fontsize(max(lo, txt.get_fontsize() - 0.25))

def _cell_array(p, ov, mk, cwp, chp, a, cmap, palette):
    """base image (resized to the cell) with the CAM and / or the class mask blended over it -> uint8 (chp, cwp, 3)"""
    import numpy as np
    from PIL import Image
    out = np.asarray(Image.open(p).convert("RGB").resize((cwp, chp), Image.LANCZOS), dtype=np.float32) if p else None
    if ov:
        if ov.lower().endswith(".npy"):
            m = np.nan_to_num(np.squeeze(np.load(ov)).astype(np.float32))
            if m.ndim != 2: raise SystemExit(f"[FAIL] overlay {ov}: expected a 2-D map, got shape {m.shape}")
            m = (m - m.min()) / (m.max() - m.min()) if m.max() > m.min() else np.zeros_like(m)
            m = np.clip(np.asarray(Image.fromarray(m, "F").resize((cwp, chp), Image.BILINEAR)), 0, 1)
            col = cmap(m)[..., :3] * 255.0
        else: col = np.asarray(Image.open(ov).convert("RGB").resize((cwp, chp), Image.BILINEAR), dtype=np.float32)
        out = col if out is None else (1 - a.overlay_alpha) * out + a.overlay_alpha * col
    if mk:
        im = Image.open(mk); ids = np.asarray(im if im.mode in ("P", "L", "I", "I;16") else im.convert("L")).astype(np.int32)
        ids = np.asarray(Image.fromarray(ids, "I").resize((cwp, chp), Image.NEAREST)); fg = ids > 0
        pal = np.array([[int(palette[(k - 1) % len(palette)][i:i + 2], 16) for i in (1, 3, 5)] for k in range(1, max(2, int(ids.max()) + 1))], dtype=np.float32)
        if out is None: out = np.full((chp, cwp, 3), 255.0, dtype=np.float32)
        out[fg] = (1 - a.mask_alpha) * out[fg] + a.mask_alpha * pal[ids[fg] - 1]
    return np.clip(out, 0, 255).astype(np.uint8)

def _min_dpi(project):
    try:
        import yaml
        return int(((yaml.safe_load(io.open(os.path.join(project, "research-state.yaml"), encoding="utf-8")) or {}).get("target") or {}).get("min_dpi") or 300)
    except Exception: return 300

def det_grid(a):
    """rows = samples, cols = methods; optional boxes / CAM overlay + shared colorbar / class masks / marks / highlighted column / inset.
    The photos are one numpy raster at --dpi over the printed width; frames, boxes, marks and every label are vector on top, so the PDF holds
    one embedded image (its dpi at print size is exactly --dpi) plus a real text layer. Written through make_figure.finish (png/pdf/source.csv/_gray.png/figures.csv)."""
    import numpy as np
    from PIL import Image
    import make_figure as mf
    from matplotlib.patches import Rectangle, Ellipse
    plt = mf.plt; plt.rcParams["savefig.pad_inches"] = 0   # finish() saves bbox_inches="tight": no pad, so the page is exactly --width-mm
    root = os.path.abspath(a.project); methods = a.methods.split(","); samples = a.samples.split(","); ncols = a.cols or len(methods); ngroups = math.ceil(len(methods) / ncols)
    nrows = len(samples); notes = []; mm = 25.4; pt = mm / 72   # pt = 1 pt in mm
    col_lab = a.col_labels.split(",") if a.col_labels else list(methods)
    row_lab = [] if a.row_labels == "none" else (a.row_labels.split(",") if a.row_labels else list(samples))
    if len(col_lab) != len(methods) or (row_lab and len(row_lab) != nrows): raise SystemExit(f"[FAIL] --col-labels needs {len(methods)} entries and --row-labels {nrows} (or 'none')")
    hl = {h for h in a.highlight.split(",") if h}; cnames = a.class_names.split(",") if a.class_names else []
    cmap = plt.get_cmap(a.cmap); marks = collections.defaultdict(list)
    if a.marks:
        for r in csv.DictReader(open(a.marks, encoding="utf-8-sig")): marks[(r["sample"], r["method"])].append([float(r[k]) for k in ("cx", "cy", "w", "h")])
    # ---- per-cell lookup: <dir>/<method>/<sample>.<ext>
    cells = {}
    for mth in methods:
        for smp in samples:
            ov = _find(a.overlay_dir, mth, smp, (".npy", ".png")) if a.overlay_dir else None; mk = _find(a.mask_dir, mth, smp, (".png",)) if a.mask_dir else None
            p = _find(a.root, mth, smp, IMG_EXT)
            if not p and (ov or mk) and a.gt_col: p = _find(a.root, a.gt_col, smp, IMG_EXT)   # CAM / mask columns sit on the raw image of the GT column
            cells[(mth, smp)] = dict(img=p, ov=ov, mk=mk, lb=_find(a.labels_dir, mth, smp, LABEL_EXT[a.label_fmt]) if a.labels_dir else None)
    first = next((c["img"] for c in cells.values() if c["img"]), None)
    aspect = float(a.aspect) if a.aspect != "auto" else (Image.open(first).size[1] / Image.open(first).size[0] if first else 1.0)
    cb_on = bool(a.overlay_dir) and a.colorbar != "none" and any(c["ov"] for c in cells.values()); cb_lab = (a.colorbar.split(",") + ["", ""])[:2] if cb_on else ["", ""]
    # ---- layout in mm
    W = a.width_mm; gap = a.gap_mm; strip = 3.4; ggap = 1.2; left = 3.6 if row_lab else 0.6; cbw, cbg = 2.2, 1.4; right = 0.6 + (cbg + cbw + 1.6 if cb_on else 0)
    cw = (W - left - right - (ncols - 1) * gap) / ncols; ch = cw * aspect; rows_h = nrows * ch + (nrows - 1) * gap
    top_m = 0.6 + (strip if cb_on and a.label_pos == "bottom" else 0); bot_m = 0.6 + (strip if cb_on and a.label_pos == "top" else 0)
    H = top_m + ngroups * (rows_h + strip) + (ngroups - 1) * ggap + bot_m
    ppm = (a.cell_px / cw) if a.cell_px else a.dpi / mm
    Wp, Hp = int(round(W * ppm)), int(math.ceil(H * ppm)); cwp, chp = max(2, int(round(cw * ppm))), max(2, int(round(ch * ppm)))
    def cell_xy(gi, ci, si): return left + ci * (cw + gap), top_m + gi * (rows_h + strip + ggap) + (strip if a.label_pos == "top" else 0) + si * (ch + gap)
    lw_box = a.box_lw or max(0.4, min(1.0, cw * 0.035))   # printed pt, scaled to the cell, never thinner than 0.4 pt
    if lw_box < 0.4: lw_box = 0.4; notes.append("--box-lw raised to the 0.4 pt printed floor")
    inset = [float(x) for x in a.inset.split(",")] if a.inset else None
    # ---- raster layer
    canvas = np.full((Hp, Wp, 3), 255, dtype=np.uint8); missing, eff = [], []
    for gi in range(ngroups):
        for ci, mth in enumerate(methods[gi * ncols:(gi + 1) * ncols]):
            for si, smp in enumerate(samples):
                c = cells[(mth, smp)]
                if not (c["img"] or c["ov"] or c["mk"]): missing.append(f"{mth}/{smp}"); continue
                arr = _cell_array(c["img"], c["ov"], c["mk"], cwp, chp, a, cmap, CLASS_COLORS[:max(1, a.palette - 1)] if a.palette else CLASS_COLORS)
                if c["img"]: eff.append(Image.open(c["img"]).size[0] / (cw / mm))
                if inset and c["img"]:
                    sim = Image.open(c["img"]).convert("RGB"); sw, sh = sim.size; isz = int(cwp * 0.42)
                    crop = sim.crop((int(inset[0] * sw), int(inset[1] * sh), int((inset[0] + inset[2]) * sw), int((inset[1] + inset[3]) * sh))).resize((isz, isz), Image.LANCZOS)
                    arr[2:2 + isz, cwp - isz - 2:cwp - 2] = np.asarray(crop)
                x, y = cell_xy(gi, ci, si); xp, yp = int(round(x * ppm)), int(round(y * ppm))
                canvas[yp:yp + chp, xp:xp + cwp] = arr[:Hp - yp, :Wp - xp]
    cbx = W - right + cbg; cb_top = top_m + (strip if a.label_pos == "top" else 0); cb_bot = cell_xy(ngroups - 1, 0, nrows - 1)[1] + ch
    if cb_on:
        x0p, x1p, y0p, y1p = int(round(cbx * ppm)), int(round((cbx + cbw) * ppm)), int(round(cb_top * ppm)), int(round(cb_bot * ppm))
        canvas[y0p:y1p, x0p:x1p] = (cmap(np.linspace(1, 0, y1p - y0p))[:, None, :3] * 255).astype(np.uint8)
    # ---- vector layer (axes in mm, y down)
    fig = plt.figure(figsize=(W / mm, H / mm)); ax = fig.add_axes([0, 0, 1, 1]); ax.imshow(canvas, extent=(0, W, H, 0), interpolation="none", aspect="auto", zorder=0)
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    src = []
    for gi in range(ngroups):
        for ci, mth in enumerate(methods[gi * ncols:(gi + 1) * ncols]):
            k = gi * ncols + ci; x0 = cell_xy(gi, ci, 0)[0]
            ty = cell_xy(gi, 0, 0)[1] - 0.7 if a.label_pos == "top" else cell_xy(gi, 0, nrows - 1)[1] + ch + 0.7
            t = ax.text(x0 + cw / 2, ty, col_lab[k], ha="center", va="bottom" if a.label_pos == "top" else "top", fontsize=6.5, fontweight="bold" if mth in hl else "normal", color=mf.ACCENT if mth in hl else "black")
            if not _fit(fig, t, cw * 0.98 / mm * fig.dpi): notes.append(f"column label '{col_lab[k]}' wider than its cell at the 5.2 pt floor: shorten it via --col-labels")
            for si, smp in enumerate(samples):
                c = cells[(mth, smp)]; x, y = cell_xy(gi, ci, si); nb = 0; bcol = ""; mk_ = marks.get((smp, mth), [])
                if not (c["img"] or c["ov"] or c["mk"]):
                    ax.add_patch(Rectangle((x, y), cw, ch, fill=False, ec="#999999", lw=0.4))
                elif c["lb"]:
                    iw, ih = Image.open(c["img"]).size if c["img"] else (1, 1); bcol = GT_COLOR if mth == a.gt_col else mf.ACCENT
                    for lab_, bx0, by0, bx1, by1 in read_boxes(c["lb"], a.label_fmt, iw, ih):
                        ax.add_patch(Rectangle((x + bx0 * cw, y + by0 * ch), (bx1 - bx0) * cw, (by1 - by0) * ch, fill=False, ec=bcol, lw=lw_box, zorder=3)); nb += 1
                        if cnames:
                            nm = cnames[int(lab_)] if lab_.isdigit() and int(lab_) < len(cnames) else lab_; up = by0 * ch > 2.4
                            ax.text(x + bx0 * cw, y + by0 * ch - (0.1 if up else -lw_box * pt), nm, fontsize=5.2, color="white", ha="left", va="bottom" if up else "top", zorder=4, bbox=dict(fc=bcol, ec="none", pad=0.25))
                if inset and c["img"]:   # white frames: the zoomed crop (top-right) and the region it was cut from
                    isz = int(cwp * 0.42) / ppm; ax.add_patch(Rectangle((x + cw - isz - 2 / ppm, y + 2 / ppm), isz, isz, fill=False, ec="white", lw=0.6, zorder=3))
                    ax.add_patch(Rectangle((x + inset[0] * cw, y + inset[1] * ch), inset[2] * cw, inset[3] * ch, fill=False, ec="white", lw=0.4, zorder=3))
                for mx, my, mw, mh in mk_: ax.add_patch(Ellipse((x + mx * cw, y + my * ch), mw * cw, mh * ch, fill=False, ec=mf.ACCENT, lw=max(0.6, lw_box), zorder=3))
                src.append([smp, mth, c["img"] or "", c["ov"] or "", c["mk"] or "", nb, bcol, len(mk_), "yes" if mth in hl else "no"])
            if mth in hl:
                fy0, fy1 = cell_xy(gi, ci, 0)[1] - gap / 2, cell_xy(gi, ci, nrows - 1)[1] + ch + gap / 2
                ax.add_patch(Rectangle((x0 - gap / 2, fy0), cw + gap, fy1 - fy0, fill=False, ec=mf.ACCENT, lw=1.0, zorder=5))
    for si, lab_ in enumerate(row_lab):
        for gi in range(ngroups):
            t = ax.text(left / 2 - 0.2, cell_xy(gi, 0, si)[1] + ch / 2, lab_, rotation=90, ha="center", va="center", fontsize=6.5)
            if not _fit(fig, t, ch * 0.98 / mm * fig.dpi, "y"): notes.append(f"row label '{lab_}' longer than its cell at the 5.2 pt floor: shorten it via --row-labels")
    if cb_on:
        ax.add_patch(Rectangle((cbx, cb_top), cbw, cb_bot - cb_top, fill=False, ec="#333333", lw=0.4, zorder=5))
        ax.text(cbx + cbw / 2, cb_top - 0.5, cb_lab[1], ha="center", va="bottom", fontsize=6.0, fontweight="bold"); ax.text(cbx + cbw / 2, cb_bot + 0.5, cb_lab[0], ha="center", va="top", fontsize=6.0, fontweight="bold")
    min_dpi = _min_dpi(root); emb = Wp / (W / mm)
    if emb < min_dpi * 0.985: notes.append(f"embedded raster {emb:.0f} dpi < target.min_dpi {min_dpi}: raise --dpi")
    if eff and min(eff) < min_dpi * 0.5: notes.append(f"source images give only {min(eff):.0f} dpi at print size (< half of min_dpi {min_dpi}): the grid is upsampled, not sharper; use larger source images or fewer columns")
    cap = (f"Qualitative grid, {nrows} samples × {len(methods)} methods; photos embedded as one {Wp}×{Hp}px raster ({emb:.0f} dpi at {W:g} mm), frames/boxes/labels vector."
           + (f" Boxes: green = {a.gt_col}, red = predictions." if any(r[6] == GT_COLOR for r in src) else "") + (f" Overlay: {a.cmap} map blended at alpha {a.overlay_alpha:g}." if cb_on else ""))
    print(f"grid {Wp}×{Hp}px -> {emb:.0f} dpi embedded @ {W:g} mm; cell {cw:.1f}×{ch:.1f} mm; box line {lw_box:.2f} pt; cells {len(methods)}×{nrows}"
          + (f"; MISSING {len(missing)}: {missing[:6]}" if missing else "") + (f"; source images ≥ {min(eff):.0f} dpi" if eff else ""))
    for n in notes: print(f"[WARN] grid: {n}")
    mf.finish(fig, a, src, ["sample", "method", "image", "overlay", "mask", "n_boxes", "box_color", "n_marks", "highlight"], root, cap)
    return emb

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("sota", "multi", "ablation", "seeds"):
        p = sub.add_parser(n); p.add_argument("--csv", required=True); p.add_argument("--out", required=True); p.add_argument("--metrics", required=True)
        p.add_argument("--higher", default=""); p.add_argument("--lower", default=""); p.add_argument("--project", default="", help="read results.metric_direction / primary_direction from <project>/research-state.yaml"); p.add_argument("--caption", default="Caption."); p.add_argument("--label", default="tab:x"); p.add_argument("--decimals", type=int, default=3); p.add_argument("--md", action="store_true")
        p.add_argument("--numbers", action="store_true", help="also register every cell in <out-dir>/numbers.csv for the G6 numbers gate")
        if n in ("sota", "multi"):
            p.add_argument("--name-col", default="method"); p.add_argument("--group-col", default=""); p.add_argument("--ours", default=""); p.add_argument("--extra", default="", help="non-ranked columns e.g. Params,FLOPs"); p.add_argument("--cite-col", default="")
        if n == "multi": p.add_argument("--datasets", required=True); p.add_argument("--dataset-col", default="dataset"); p.add_argument("--dataset-labels", default="", help='display names for the dataset headers, e.g. "prostate_t1=Prostate ($K{=}6$),kidney_t1=Kidney"')
        if n == "ablation": p.add_argument("--components", required=True); p.add_argument("--ablation-plain", action="store_true", help="no red/blue, only bold full row")
        if n == "seeds": p.add_argument("--setting-col", default="setting"); p.add_argument("--seed-col", default="seed")
    g = sub.add_parser("grid"); g.add_argument("--root", required=True); g.add_argument("--methods", required=True); g.add_argument("--samples", required=True); g.add_argument("--out", required=True)
    g.add_argument("--inset", default=""); g.add_argument("--cols", type=int, default=0); g.add_argument("--width-mm", type=float, default=183); g.add_argument("--cell-px", type=int, default=0, help="0 = auto from --dpi"); g.add_argument("--dpi", type=float, default=400)
    g.add_argument("--project", default=".", help="where figures.csv / research-state.yaml (target.min_dpi) live; --out is relative to it")
    g.add_argument("--labels-dir", default="", help="<dir>/<method>/<sample>.txt|json|xml"); g.add_argument("--label-fmt", choices=["yolo", "coco", "voc", "xyxy"], default="yolo"); g.add_argument("--gt-col", default="GT", help="column whose boxes are green (and whose image is the base for CAM / mask columns without their own image)")
    g.add_argument("--class-names", default=""); g.add_argument("--box-lw", type=float, default=0, help="printed pt; 0 = scaled to the cell (0.4-1.0 pt)")
    g.add_argument("--overlay-dir", default="", help="<dir>/<method>/<sample>.npy (2-D map, min-max normalised, colour-mapped) or .png (used as is)"); g.add_argument("--overlay-alpha", type=float, default=0.55); g.add_argument("--cmap", default="jet")
    g.add_argument("--colorbar", default="Low,High", help="'bottom,top' end labels of the shared vertical colorbar; 'none' = no bar")
    g.add_argument("--row-labels", default="", help="comma list; default = sample names; 'none' = no row labels"); g.add_argument("--col-labels", default="", help="comma list; default = method names"); g.add_argument("--label-pos", choices=["bottom", "top"], default="bottom", help="column labels under each row group (default) or above it")
    g.add_argument("--highlight", default="", help="method(s) framed in the accent colour (Fig. 4 'Ours' column)"); g.add_argument("--marks", default="", help="csv sample,method,cx,cy,w,h (0-1 cell coords): accent ellipses")
    g.add_argument("--mask-dir", default="", help="<dir>/<method>/<sample>.png with class ids (0 = background, unpainted)"); g.add_argument("--palette", type=int, default=0, help="number of classes incl. background (0 = whole 20-colour palette)"); g.add_argument("--mask-alpha", type=float, default=0.6)
    g.add_argument("--gap-mm", type=float, default=0.4); g.add_argument("--aspect", default="auto", help="cell height / width; auto = first image")
    ap.add_argument("--labels", default="", help='display labels, e.g. "AP50=AP$_{50}$,AP50_95=AP$_{50:95}$"')
    a = ap.parse_args()
    for kv in filter(None, a.labels.split(",")):
        k, v = kv.split("=", 1); LABELS[k] = v
    for kv in filter(None, (getattr(a, "dataset_labels", "") or "").split(",")):
        k, v = kv.split("=", 1); DLABELS[k] = v
    if a.cmd == "grid": return det_grid(a)
    if a.project:
        import yaml
        sp = os.path.join(a.project, "research-state.yaml")
        if os.path.exists(sp): STATE.update((yaml.safe_load(io.open(sp, encoding="utf-8")) or {}).get("results") or {})
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
