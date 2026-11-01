# -*- coding: utf-8 -*-
"""P5/P6 — generate the three standard comparison artefacts from results files. Run by Claude.

  python make_comparison.py sota   --csv results/main.csv --out paper/tab_sota.tex [--group-col family] [--ours "SKYDET-T,SKYDET-C"]
                                   [--metrics AP50,AP75,AP50_95] [--higher AP50,AP75,AP50_95] [--lower Params,FLOPs]
                                   [--caption "..."] [--label tab:sota] [--cite-col ref] [--decimals 3] [--md]
                                   [--ci-style bracket|pm|none] [--sig-test "paired bootstrap, 10k resamples"] [--alpha 0.05]
                                   [--delta best|<method>] [--fit auto|linewidth|columnwidth|none] [--width-mm 88] [--font-pt 9]
  python make_comparison.py multi  --csv results/main.csv --datasets DOTA,AI-TOD,NWPU --dataset-col dataset ...   (one block per dataset side by side)
  python make_comparison.py ablation --csv results/ablation.csv --components DINOv3,SGA,CFE --metrics AP50,AP75,AP50_95 --out paper/tab_ablation.tex
  python make_comparison.py grid   --root figures/det --methods Origin,YOLOv8,...,SKYDET-C --samples img1,img2 --out figures/fig_det_grid.png
                                   [--inset x,y,w,h] [--cols 12] [--width-mm <venue text width, else 183>] [--dpi 400] [--project .]
                                   [--row-labels "M3FD,LLVIP"|none] [--col-labels ...] [--label-pos bottom|top] [--highlight Ours[,..]] [--marks marks.csv]
                                   [--labels-dir L --label-fmt yolo|coco|voc|xyxy --gt-col GT --class-names a,b --box-lw 0 --min-score 0.25 --box-status]
                                   [--overlay-dir O --overlay-alpha 0.55 --cmap viridis --colorbar "Low,High"|none]
                                   [--mask-dir M --palette 6 --mask-alpha 0.6] [--cell-counts samples.csv] [--display-gamma 0.5] [--allow-code-labels]

Conventions (IEEE/TGRS style, matched against SKYDET TGRS 2026 Tables II–V and Fig. 5):
  * best value per metric in \\textcolor{red}, second-best in \\textcolor{blue}; direction per metric: --lower > --higher (unlisted = lower)
    > research-state.yaml results.metric_direction / primary_direction (with --project) > name regex (metric_direction.py) > higher
  * rows grouped by --group-col with an italic group header line; "ours" rows bold and separated by \\midrule
  * method / setting / component names go through the figure style registry (figure_style.py; ours rows bold); a name that reads like code (rec_quantile, chgate) is a FAIL
    unless --allow-code-labels (register a label in research-state.yaml figures.style instead)
  * every number formatted to --decimals; the same CSV drives both the .tex and the .md mirror so the two never diverge
  * ablation: components as ✓/✗ columns (\\checkmark / $\\times$), rows numbered, last row (all ✓) bold
  * grid: rows = samples, cols = methods; optional inset crop drawn at 2× in the top-right of each cell; column labels under each row group (--label-pos top
    puts them above, Fig.-4 style). Per cell <dir>/<method>/<sample>: boxes (--gt-col in the gt role colour, other columns in that method's colour, >= 0.8 pt printed), CAM overlay with one
    shared colorbar (cmap = figures.style.cmap, viridis; jet only with roles.allow_jet), class-id mask in a fixed palette, ellipses in the ours colour (--marks), ours_frame frame round the
    --highlight columns (default: figures.style.ours). Column labels come from the figure style registry (figure_style.py; the method directory names are its keys; a label that reads like code
    FAILs unless --allow-code-labels); the colours of the roles gt / tp / fp / fn / ours_frame and font_pt come from it too. --cell-counts samples.csv (select_samples.py) prints
    'TP 5 · FP 1 · FN 0' (det) or 'in-box 62 %' (cam) under every cell; --display-gamma 0.5 brightens dark photos for display only. Every grid writes <out>.meta.json (what was drawn:
    roles actually used, selection rule, gamma, counts kind) and <out>.caption.md (caption draft, caption_draft.py). Photos = one raster at --dpi
    over --width-mm, embedded in the PDF (G5 counts a .pdf as vector and checks the .png row: 400 dpi at --width-mm); labels / frames / boxes are vector.
    A CAM or mask column without its own image sits on the --gt-col image of the same sample. .source.csv: one row per cell (image, overlay, n_boxes, ..., label, color, line, marker, counts)
    --box-status (with --labels-dir and the --gt-col column among --methods): predicted boxes coloured by match against the --gt-col boxes (IoU >= 0.5,
    class-aware, greedy): TP / FP / missed ground truth in the roles tp / fp / fn (green solid, orange dashed, light grey dotted by default) on the prediction's cell; legend strip at the bottom;
    per-method TP/FP/FN totals printed. --min-score drops boxes below a confidence (6th column of yolo / xyxy lines, 'score' of coco json).
    Method directories that differ only by case (ir / IR) are refused: on Windows / macOS they are one folder. --width-mm defaults to the venue's text width.
  * uncertainty in cells (sota / multi / ablation; seeds already prints Mean ± Std): a `<metric>_lo` + `<metric>_hi` column pair is printed as
    `x\\,{\\scriptsize[lo, hi]}` (md `x [lo, hi]`), a `<metric>_sd` column as `x\\,{\\scriptsize$\\pm$sd}`; --ci-style pm turns a lo/hi pair into
    +- half-width, none switches it off. Best / second-best colouring stays on the point estimate. With --numbers the bounds / sd are registered as
    their own rows (`<metric>_lo`, `_hi`, `_sd`, pm half-width as `_halfwidth` with its formula in the transform column).
  * significance: a `sig_<metric>` column (0/1/true/yes/y or a p-value, significant when p < --alpha; a bare 0 or 1 is a flag, not a p) puts `$^\\dagger$` on
    the cell and adds the footnote "dagger significantly different from <first --ours> (<--sig-test text>, alpha = 0.05)". THIS SCRIPT NEVER TESTS ANYTHING:
    it only renders what the project's analysis wrote into the csv, so significance columns without --sig-test text are a WARN (the footnote would not
    say which test).
  * --delta best|<method> (sota / multi): final row "Delta vs best baseline" (or vs the named method) = first --ours row minus the strongest non-ours row
    per metric and dataset (direction as above), `+x.xx` / `-x.xx` (raw difference ours - reference, so a negative number is an improvement for lower-is-better
    metrics); tex writes a negative as `$-x.xx$`, md uses ASCII `-` so the numbers gate finds it. Registered with --numbers as `<metric>_delta`
    (method `delta_vs_best`), the formula `metric[ours] - metric[reference]` goes into the transform column.
  * width fitting: the tabular's width is estimated (max visible characters per column x 0.52 em at --font-pt (\\small = 9 pt by default; \\scriptsize CI text
    at 7/9 of it) + 12 pt padding per column) against the target: --width-mm, else the target column of the venue template (state.target via --project:
    single column for `table` in a two-column class, full width for `table*` or one-column classes), else 88 mm (cs_conf) / 170 mm. --fit auto wraps in
    \\resizebox{\\linewidth}{!}{...} when the estimate is wider and prints the effective printed font size (< 5 pt: FAIL, no resizebox emitted, split the table;
    5-6 pt: WARN); linewidth / columnwidth force the wrapper, none never wraps (WARN if too wide). \\resizebox needs graphicx: WARN when main.tex does not load it.
    The estimate is a heuristic; latex_check.py check (G6d) reads the real Overfull \\hbox warnings from main.log.
  * exit code = number of [FAIL] lines (the files are still written)
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
import figure_style as fs, caption_draft as cd
STATE = {}   # research-state.yaml results block, filled from --project
STYLE = fs.Style(None)   # figures.style of research-state.yaml (figure_style.py): method names / colours / roles / cmap / font_pt; loaded in main() / det_grid()
ALLOW_CODE = False       # --allow-code-labels: a code-like final label is only a WARN
_SEEN = set()
def load_style(project):
    global STYLE
    STYLE = fs.load(os.path.abspath(project or ".")); _SEEN.clear(); return STYLE
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
def dlab(d):
    if d in DLABELS: return DLABELS[d]
    reg = next((v.get("label") for k, v in STYLE.datasets.items() if fs._norm(k) == fs._norm(d) or fs._norm(v.get("label", "")) == fs._norm(d)), None)   # registered dataset: its label (a hue is never involved)
    return esc(reg) if reg else esc(d)
def dlab_md(d): return DLABELS.get(d, d).replace("$", "")

# ------------------------------------------------------------------ uncertainty, significance, delta row, width fitting (tables only; the grid does not use these)
FAILS = 0
TARGET = {}   # research-state.yaml target block, filled from --project (venue / family / latex_dir -> the target width)
def say(lv, msg):
    global FAILS
    if lv == "FAIL": FAILS += 1
    print(f"[{lv}] {msg}")

def _code(label):
    """a method / setting name that reads like code; a lone x / y is a legitimate name (method X), 'value' is not"""
    return fs.looks_like_code(label, placeholders=False) or str(label).strip().lower() in ("value", "values", "val")

def mname(n, what="method"):
    """display name of a method / setting / component through the figure-style registry (figure_style.py): the registered label; an unregistered name stays as written
    (WARN when a registry exists); a final label that reads like code (chgate, F6R, rec_quantile, out0) is a FAIL unless --allow-code-labels. Inline math is kept as written."""
    n = str(n); k = STYLE.key(n)
    lab = STYLE.label(n) if (k is not None and STYLE.methods[k].get("label")) else n
    if n not in _SEEN:
        _SEEN.add(n)
        if k is None and not STYLE.empty(): say("WARN", f"{what} name {n!r} is not registered in figures.style (figure_style.py init)")
        if _code(lab): say("WARN" if ALLOW_CODE else "FAIL", f"{what} name {n!r} reads like code" + (f" (suggested label {fs.humanise(n)!r})" if lab == n else "") + ": register a label for it (figure_style.py init, figures.style.methods) or pass --allow-code-labels")
    return lab

def _num(x):
    try: v = float(x)
    except Exception: return None
    return v if v == v else None

_YES = ("1", "true", "yes", "y", "t", "on", "✓"); _NO = ("0", "false", "no", "n", "f", "off", "✗", "", "nan", "na", "none", "-", "--")
def is_sig(v, alpha):
    """Flag (0/1/true/yes/...) or a p-value (< alpha). A bare 0 / 1 is a flag. This function only reads what the analysis wrote; nothing is tested here."""
    s = str(v).strip().lower()
    if s in _YES: return True
    if s in _NO: return False
    p = _num(s)
    return p is not None and p < alpha

def cell_suffix(rr, m, cols, a, ds, name, src, st):
    """-> (tex, md) text that follows the point estimate: the dagger mark and the uncertainty. Registers the shown bounds / sd in src."""
    t = md = ""
    if rr is None: return t, md
    if f"sig_{m}" in cols:
        st["sig_cols"] = True
        if is_sig(rr.get(f"sig_{m}", ""), a.alpha): t += r"$^\dagger$"; md += "†"; st["sig_used"] = True
    if a.ci_style == "none": return t, md
    g = lambda s: _num(rr.get(f"{m}_{s}")) if f"{m}_{s}" in cols else None
    lo, hi, sd = g("lo"), g("hi"), g("sd"); d = a.decimals
    if a.ci_style == "bracket" and lo is not None and hi is not None:
        ls, hs = fnum(lo, d), fnum(hi, d)
        t += r"\,{\scriptsize[%s, %s]}" % (ls, hs); md += f" [{ls}, {hs}]"
        src += [[ds or "", name, f"{m}_lo", rr[f"{m}_lo"]], [ds or "", name, f"{m}_hi", rr[f"{m}_hi"]]]
    elif sd is not None:
        t += r"\,{\scriptsize$\pm$%s}" % fnum(sd, d); md += f" ± {fnum(sd, d)}"; src.append([ds or "", name, f"{m}_sd", rr[f"{m}_sd"]])
    elif a.ci_style == "pm" and lo is not None and hi is not None:
        half = (hi - lo) / 2
        t += r"\,{\scriptsize$\pm$%s}" % fnum(half, d); md += f" ± {fnum(half, d)}"
        src.append([ds or "", name, f"{m}_halfwidth", f"{half:.{d}f}", f"({m}_hi - {m}_lo)/2"])
    return t, md

def sig_footnote(st, a, ours_name):
    """-> (tex, md) footnote for the dagger, or ("", "")."""
    if st.get("sig_cols") and not a.sig_test:
        say("WARN", "sig_<metric> columns present but no --sig-test text: the footnote cannot say which test produced the marks (the script never tests anything itself)")
    if not st.get("sig_used"): return "", ""
    who = (mname(ours_name) if ours_name else "") or "the proposed method"; a_s = f"{a.alpha:g}"
    test = (esc(a.sig_test) + ", ") if a.sig_test else ""
    return (r"$^\dagger$ significantly different from %s (%s$\alpha = %s$)." % (esc(who), test, a_s),
            f"† significantly different from {who} ({(a.sig_test + ', ') if a.sig_test else ''}α = {a_s}).")

def delta_row(blocks, ours, name_col, metrics, extra, a, src):
    """Final row 'Delta vs best baseline': first ours row minus the strongest non-ours row (or the named method), per dataset block and metric.
    -> (tex cells, md cells) or None."""
    names = [r[name_col] for r in blocks[0][1]]
    on = next((n for n in names if n in ours), None)
    if on is None:
        say("WARN", "--delta needs an --ours row present in the table; no Delta row written"); return None
    d = a.decimals; label = "best baseline" if a.delta == "best" else mname(a.delta)
    tc = [r"$\Delta$ vs " + esc(label)] + [""] * len(extra); mc = [f"Δ vs {label}"] + [""] * len(extra); refs = []
    for bi, (ds, brows) in enumerate(blocks):
        by = {r[name_col]: r for r in brows}; o = by.get(on)
        for m in metrics:
            ov = _num(o.get(m)) if o else None; ref = None
            if a.delta == "best":
                cand = [(_num(r.get(m)), r[name_col]) for r in brows if r[name_col] not in ours and _num(r.get(m)) is not None]
                if cand: ref = (max if higher_for(m, a) else min)(cand, key=lambda t: t[0])
            elif by.get(a.delta) and _num(by[a.delta].get(m)) is not None: ref = (_num(by[a.delta].get(m)), a.delta)
            if ov is None or ref is None: tc.append("--"); mc.append("--"); continue
            diff = ov - ref[0]; rd = round(diff, d)
            s = f"{rd:+.{d}f}" if rd != 0 else f"{0:.{d}f}"
            tc.append(f"${s}$" if s.startswith("-") else s); mc.append(s)
            src.append([ds or "", "delta_vs_" + ("best" if a.delta == "best" else a.delta), f"{m}_delta", f"{rd + 0.0:.{d}f}", f"{m}[{on}] - {m}[{ref[1]}]"])
            refs.append(f"{(ds + ' ') if ds else ''}{m} -> {ref[1]}")
    say("INFO", f"Delta row: {on} minus " + "; ".join(refs))
    return tc, mc

# --- width estimate
CHAR_EM = 0.52; COL_PAD_PT = 12.0; PT_MM = 25.4 / 72.27
def _vis(t):
    t = re.sub(r"\\(?:textbf|textit|textcolor\{[^}]*\}|small|scriptsize|footnotesize|cite|multirow\{\d+\}\{\*\})", "", t)
    return re.sub(r"[{}$^_\\]", "", re.sub(r"\\[A-Za-z]+", "x", t))

def _cell_pt(cell, font_pt):
    small = 0.0
    def cut(m):
        nonlocal small; small += len(_vis(m.group(1))) * CHAR_EM * font_pt * 7 / 9; return ""
    main = re.sub(r"\{\\scriptsize(.*?)\}", cut, cell)
    return len(_vis(main)) * CHAR_EM * font_pt + small

def est_width_mm(W, font_pt):
    """Heuristic tabular width: widest cell per column + 2 x \\tabcolsep (12 pt) per column."""
    n = max((len(r) for r in W), default=0); tot = 0.0
    for c in range(n): tot += max((_cell_pt(r[c], font_pt) for r in W if c < len(r)), default=0.0) + COL_PAD_PT
    return tot * PT_MM

def target_width_mm(a, env):
    if a.width_mm: return a.width_mm, "--width-mm"
    try:
        import latex_check as lc
        tpl = lc.pick_template(TARGET.get("venue") or "", TARGET.get("family") or "")
    except Exception: tpl = None
    if tpl:
        two = tpl.get("twocolumn", "").lower() == "yes"
        mm = float(tpl["single_col_mm"]) if (two and env == "table") else float(tpl["full_width_mm"])
        return mm, f"{tpl['key']} template, {'single column' if (two and env == 'table') else 'full text width'}"
    if (TARGET.get("family") or "") == "cs_conf" and env == "table": return 88.0, "cs_conf two-column default, single column"
    return 170.0, "default 170 mm (no venue template: give --project with state.target or --width-mm)"

def _graphicx_state(a):
    """True / False if a main.tex (or a local .sty / .cls next to it) was found, None if there is no main.tex to look at."""
    cands = []
    if a.project: cands.append(os.path.join(a.project, TARGET.get("latex_dir") or "paper/latex", "main.tex"))
    d = os.path.dirname(os.path.abspath(a.out))
    for _ in range(3): cands += [os.path.join(d, "main.tex"), os.path.join(d, "latex", "main.tex"), os.path.join(d, "paper", "latex", "main.tex")]; d = os.path.dirname(d)
    main = next((c for c in cands if os.path.isfile(c)), None)
    if main is None: return None
    txt = io.open(main, encoding="utf-8", errors="replace").read()
    for f in os.listdir(os.path.dirname(main)):
        if f.endswith((".sty", ".cls")): txt += io.open(os.path.join(os.path.dirname(main), f), encoding="utf-8", errors="replace").read()
    return bool(re.search(r"graphicx", txt))

def finish_tex(L, W, a, env, foot=""):
    """Width fitting (--fit) and the significance footnote. L = table lines containing one \\begin{tabular} ... \\end{tabular}."""
    i = next(k for k, l in enumerate(L) if l.startswith(r"\begin{tabular}")); j = max(k for k, l in enumerate(L) if l == r"\end{tabular}")
    est = est_width_mm(W, a.font_pt); tgt, why = target_width_mm(a, env); wrap = None
    if a.fit == "none":
        if est > tgt: say("WARN", f"table width ~{est:.0f} mm > {tgt:.0f} mm ({why}) and --fit none: expect an Overfull \\hbox (G6d reads main.log)")
    elif est <= tgt and a.fit == "auto":
        say("PASS", f"table width ~{est:.0f} mm fits {tgt:.0f} mm ({why}); no \\resizebox")
    else:
        scale = tgt / est if est else 1.0; eff = a.font_pt * scale
        if eff < 5.0:
            say("FAIL", f"table width ~{est:.0f} mm vs {tgt:.0f} mm ({why}): \\resizebox would print the text at {eff:.1f} pt (< 5 pt); split the table (e.g. multi -> one block per row group, drop --extra columns) - no \\resizebox emitted")
        else:
            wrap = r"\resizebox{\columnwidth}{!}{%" if a.fit == "columnwidth" else r"\resizebox{\linewidth}{!}{%"
            msg = f"table width ~{est:.0f} mm vs {tgt:.0f} mm ({why}): wrapped in {wrap[:-1]}; effective printed font size {eff:.1f} pt"
            if scale > 1.15: say("WARN", msg + f" (scaled UP x{scale:.2f} by --fit {a.fit})")
            elif eff < 6.0: say("WARN", msg + " (< 6 pt, hard to read in print; consider splitting the table)")
            else: say("PASS", msg)
            gx = _graphicx_state(a)
            if gx is False: say("WARN", "\\resizebox needs graphicx but main.tex (and the .sty / .cls next to it) do not mention it: add \\usepackage{graphicx} unless the class loads it")
            elif gx is None: say("INFO", "no main.tex found near --out/--project: graphicx for \\resizebox not checked")
    out = L[:i] + ([wrap] if wrap else []) + L[i:j] + [r"\end{tabular}}" if wrap else r"\end{tabular}"] + L[j + 1:]
    if foot:
        k = max(n for n, l in enumerate(out) if l.startswith(r"\end{table"))
        out[k:k] = [r"\par\smallskip{\raggedright\footnotesize " + foot + r"\par}"]
    return out

# ------------------------------------------------------------------ sota / multi
def sota_table(rows, cols, a, datasets=None):
    metrics = a.metrics.split(",")
    extra = [c for c in (a.extra.split(",") if a.extra else []) if c in cols]
    ours = [o.strip() for o in a.ours.split(",")] if a.ours else []
    name_col = a.name_col
    ours += [n for n in dict.fromkeys(r[name_col] for r in rows if r.get(name_col)) if STYLE.is_ours(n) and n not in ours]   # figures.style.ours: bold rows without repeating --ours
    blocks = [(None, rows)] if not datasets else [(d, [r for r in rows if r.get(a.dataset_col) == d]) for d in datasets]
    # column spec
    ncol = 1 + len(extra) + sum(len(metrics) for _ in blocks)
    spec = "l" + "c" * len(extra) + "".join("|" + "c" * len(metrics) for _ in blocks) if datasets else "l" + "c" * (len(extra) + len(metrics))
    env = "table*" if datasets and len(blocks) > 1 else "table"; st = {}
    W = [["Model"] + [lab(e) for e in extra] + [lab(m) for _ in blocks for m in metrics]]   # width estimate rows (data + header)
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
            nl = mname(n)                                                                                       # the registry label (figure_style.py); the key n stays the source.csv / numbers.csv selector
            cells_t = [(r"\textbf{" + esc(nl) + "}" if bold else esc(nl)) + cite_tex] + [esc(r0.get(e, "") or "--") for e in extra]   # extra columns are quoted verbatim (Params 258.2 stays 258.2)
            cells_m = [("**" + nl + "**" if bold else nl) + cite] + [(r0.get(e, "") or "--") for e in extra]
            for bi, (d, brows) in enumerate(blocks):
                rr = next((r for r in brows if r[name_col] == n), None)
                for m in metrics:
                    v = fnum(rr.get(m, "") if rr else "", a.decimals); mk = marks.get((bi, n, m))
                    src.append([d or "", n, m, rr.get(m, "") if rr else ""])
                    sx_t, sx_m = cell_suffix(rr, m, cols, a, d, n, src, st)
                    cells_t.append(tex_cell(v, mk, bold) + sx_t); cells_m.append(md_cell(v, mk, bold) + sx_m)
            L.append(" & ".join(cells_t) + r" \\"); M.append("| " + " | ".join(cells_m) + " |"); W.append(cells_t)
    dr = delta_row(blocks, ours, name_col, metrics, extra, a, src) if getattr(a, "delta", "") else None
    if dr:
        L += [r"\midrule", " & ".join(dr[0]) + r" \\"]; M.append("| " + " | ".join(dr[1]) + " |"); W.append(dr[0])
    ftex, fmd = sig_footnote(st, a, ours[0] if ours else "")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table" + ("*" if datasets and len(blocks) > 1 else "") + "}"]
    L = finish_tex(L, W, a, env, ftex)
    if fmd: M += ["", fmd]
    return "\n".join(L), "\n".join(M), src

# ------------------------------------------------------------------ ablation
def ablation_table(rows, a):
    comps = a.components.split(","); metrics = a.metrics.split(","); cl = {c: mname(c, "component") for c in comps}
    def on(v): return str(v).strip().lower() in ("1", "true", "yes", "y", "✓", "on")
    spec = "c|" + "c" * len(comps) + "|" + "c" * len(metrics)
    cols = list(rows[0].keys()) if rows else []; st = {}
    W = [["Group"] + [cl[c] for c in comps] + [lab(m) for m in metrics]]
    L = [r"\begin{table}[t]", r"\centering", r"\caption{" + a.caption + "}", r"\label{" + a.label + "}", r"\small", r"\begin{tabular}{" + spec + "}", r"\toprule",
         r"\multirow{2}{*}{\textbf{Group}} & " + " & ".join(r"\multirow{2}{*}{\textbf{%s}}" % esc(cl[c]) for c in comps) + r" & \multicolumn{%d}{c}{\textbf{Performance}} \\" % len(metrics),
         r"\cmidrule(lr){%d-%d}" % (2 + len(comps), 1 + len(comps) + len(metrics)),
         " & ".join([""] * (1 + len(comps)) + [lab(m) for m in metrics]) + r" \\", r"\midrule"]
    M = ["| Group | " + " | ".join([cl[c] for c in comps] + [lab_md(m) for m in metrics]) + " |", "|---|" + "---|" * (len(comps) + len(metrics))]
    full = [i for i, r in enumerate(rows) if all(on(r.get(c, "")) for c in comps)]
    marks = {m: rank_marks(rows, m, higher_for(m, a)) for m in metrics}
    src = []
    for i, r in enumerate(rows):
        bold = i in full
        ct = [str(i + 1)] + [(r"\checkmark" if on(r.get(c, "")) else r"$\times$") for c in comps]
        cm = [str(i + 1)] + [("✓" if on(r.get(c, "")) else "✗") for c in comps]
        for m in metrics:
            v = fnum(r.get(m, ""), a.decimals); mk = marks[m].get(i)
            src.append(["", f"group{i+1}", m, r.get(m, "")]); sx_t, sx_m = cell_suffix(r, m, cols, a, "", f"group{i+1}", src, st)
            ct.append(tex_cell(v, None if a.ablation_plain else mk, bold) + sx_t); cm.append(md_cell(v, None if a.ablation_plain else mk, bold) + sx_m)
        if bold: ct = [r"\textbf{" + c + "}" if not c.startswith("\\") else c for c in ct]; cm = ["**" + c + "**" if c.replace(".", "").isdigit() else c for c in cm]
        L.append(" & ".join(ct) + r" \\"); M.append("| " + " | ".join(cm) + " |"); W.append(ct)
    ftex, fmd = sig_footnote(st, a, "the full model (all components)")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    L = finish_tex(L, W, a, "table", ftex)
    if fmd: M += ["", fmd]
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
    W = [["Setting"] + [f"Seed {s}" for s in seeds] + ["Mean Std"]]
    L = [r"\begin{table}[t]", r"\centering", r"\caption{" + a.caption + "}", r"\label{" + a.label + "}", r"\small", r"\begin{tabular}{l" + "c" * len(seeds) + "|c}", r"\toprule",
         r"\textbf{Setting} & " + " & ".join(r"\textbf{Seed %s}" % esc(s) for s in seeds) + r" & \textbf{Mean $\pm$ Std} \\", r"\midrule"]
    M = ["| Setting | " + " | ".join(f"Seed {s}" for s in seeds) + " | Mean ± Std |", "|---|" + "---|" * (len(seeds) + 1)]
    src = []
    for k, v in settings.items():
        by = dict(v); m, s, n = stats[k]; bold = k == best
        cells = [fnum(by.get(sd, ""), d) for sd in seeds] + [f"{m:.{d}f} $\\pm$ {s:.{d}f}"]
        cm = [fnum(by.get(sd, ""), d) for sd in seeds] + [f"{m:.{d}f} ± {s:.{d}f}"]
        if bold: cells = [r"\textbf{" + c + "}" for c in cells]; cm = ["**" + c + "**" for c in cm]
        kl = mname(k, "setting")
        L.append((r"\textbf{" + esc(kl) + "}" if bold else esc(kl)) + " & " + " & ".join(cells) + r" \\"); W.append([esc(kl)] + cells)
        M.append("| " + ("**" + kl + "**" if bold else kl) + " | " + " | ".join(cm) + " |")
        for sd in seeds: src.append(["", k, f"{metric}@seed{sd}", by.get(sd, "")])
        src += [["", k, f"{metric}_mean", m], ["", k, f"{metric}_std", s], ["", k, "n_seeds", n]]
    L += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    L = finish_tex(L, W, a, "table")
    return "\n".join(L), "\n".join(M), src

def emit_numbers(src, src_csv, out_dir, decimals):
    """Append one provenance row per cell to paper/numbers.csv (G6 numbers gate) — value as printed, key = selector into <out>.source.csv.
    Existing rows for the same source file are replaced so re-running the generator never duplicates."""
    nm = os.path.join(out_dir, "numbers.csv"); rel = os.path.relpath(src_csv, os.getcwd()).replace("\\", "/")
    old = [r for r in csv.DictReader(open(nm, encoding="utf-8"))] if os.path.exists(nm) else []
    old = [r for r in old if r["file"].replace("\\", "/") != rel]
    new = []
    for row in src:
        ds, mth, met, val = row[:4]; tr = row[4] if len(row) > 4 else ""     # optional 5th element = formula for the transform column (delta rows, pm half-width)
        try: v = float(val)
        except Exception: continue
        d = decimals if "." in str(val) or isinstance(val, float) else 0
        new.append({"value": f"{v:.{d}f}" if d else str(int(v)), "file": rel, "key": f"dataset={ds}|method={mth}|metric={met},value", "transform": tr})
    with open(nm, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["value", "file", "key", "transform"]); w.writeheader(); w.writerows(old + new)
    return len(new), nm

ROLE_LS = {"gt": "-", "tp": "-", "fp": "--", "fn": ":"}      # box line styles (colours come from figures.style.roles): GT and TP solid, FP dashed, missed ground truth dotted
CLASS_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080",
                "#e6beff", "#9a6324", "#fffac8", "#800000", "#aaffc3", "#808000", "#ffd8b1", "#000075", "#808080", "#ffe119"]   # fixed categorical palette for --mask-dir (class 0 = background, left unpainted)
IMG_EXT = ("", ".png", ".jpg", ".jpeg")
LABEL_EXT = {"yolo": (".txt",), "xyxy": (".txt",), "coco": (".json",), "voc": (".xml", ".txt")}

def _find(d, mth, smp, exts):
    for e in exts:
        p = os.path.join(d, mth, smp + e)
        if os.path.isfile(p): return p
    return None

def read_boxes(path, fmt, iw, ih, min_score=None):
    """-> [(label, x0, y0, x1, y1)] in 0-1 image coordinates. yolo: 'cls cx cy w h' normalised; xyxy / voc txt: 'cls x1 y1 x2 y2 [score]' in pixels
    (taken as 0-1 when every coordinate <= 1.5); coco: json list (or {'annotations': [...]}) of {'bbox': [x, y, w, h], 'category_id'} in pixels; voc: Pascal VOC xml.
    min_score: drop boxes whose confidence (6th column of a yolo / xyxy line, 'score' of a coco item) is below it; boxes without a score are kept."""
    raw = []   # (label, x0, y0, x1, y1, is_pixel)
    if path.lower().endswith(".json"):
        d = json.load(open(path, encoding="utf-8"))
        for it in (d if isinstance(d, list) else d.get("annotations") or d.get("boxes") or d.get("detections") or []):
            bb, cls = (it.get("bbox"), it.get("category_id", it.get("category", it.get("label", "")))) if isinstance(it, dict) else (it[:4], "")
            if min_score is not None and isinstance(it, dict) and it.get("score") is not None and float(it["score"]) < min_score: continue
            x, y, w, h = map(float, bb); raw.append((str(cls), x, y, x + w, y + h, True))
    elif path.lower().endswith(".xml"):
        for ob in ET.parse(path).getroot().iter("object"):
            bb = ob.find("bndbox")
            if bb is not None: raw.append((ob.findtext("name", ""), *[float(bb.findtext(k, "0")) for k in ("xmin", "ymin", "xmax", "ymax")], True))
    else:
        for ln in io.open(path, encoding="utf-8"):
            t = ln.split()
            if len(t) < 5: continue
            if min_score is not None and len(t) >= 6 and float(t[5]) < min_score: continue
            v = [float(x) for x in t[1:5]]
            if fmt == "yolo": raw.append((t[0], v[0] - v[2] / 2, v[1] - v[3] / 2, v[0] + v[2] / 2, v[1] + v[3] / 2, False))
            else: raw.append((t[0], *v, max(v) > 1.5))
    out = []
    for c, x0, y0, x1, y1, pix in raw:
        if pix: x0, x1, y0, y1 = x0 / iw, x1 / iw, y0 / ih, y1 / ih
        out.append((c, max(0.0, min(x0, x1)), max(0.0, min(y0, y1)), min(1.0, max(x0, x1)), min(1.0, max(y0, y1))))
    return out

def _iou(a_, b_):
    ix = max(0.0, min(a_[3], b_[3]) - max(a_[1], b_[1])); iy = max(0.0, min(a_[4], b_[4]) - max(a_[2], b_[2])); inter = ix * iy
    ua = (a_[3] - a_[1]) * (a_[4] - a_[2]) + (b_[3] - b_[1]) * (b_[4] - b_[2]) - inter
    return inter / ua if ua > 0 else 0.0

def match_boxes(gt, pred, thr=0.5):
    """greedy one-to-one matching of predictions to ground truth at IoU >= thr, same class when both carry one, best IoU first
    -> (status per prediction: "tp" | "fp", indices of unmatched ground-truth boxes = missed). Boxes are (label, x0, y0, x1, y1)."""
    cand = sorted(((_iou(g, p_), gi, pi) for gi, g in enumerate(gt) for pi, p_ in enumerate(pred) if _iou(g, p_) >= thr and (not g[0] or not p_[0] or g[0] == p_[0])), reverse=True)
    used_g, used_p = set(), set()
    for v, gi, pi in cand:
        if gi in used_g or pi in used_p: continue
        used_g.add(gi); used_p.add(pi)
    return ["tp" if i in used_p else "fp" for i in range(len(pred))], [gi for gi in range(len(gt)) if gi not in used_g]

def _on(hexc):
    """text colour (black / white) that reads on a filled tag of this colour"""
    r, g, b = fs._rgb(hexc); return "#111111" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55 else "white"

def _gamma(arr, g):
    """display-only brightening: 255 * (x / 255) ** g, g < 1 lifts dark inputs; nothing but the pixels shown changes"""
    import numpy as np
    return arr if not g or abs(g - 1.0) < 1e-9 else 255.0 * np.power(np.clip(np.asarray(arr, dtype=np.float32) / 255.0, 0, 1), g)

def read_cell_counts(path, methods):
    """samples.csv of select_samples.py -> ({sample: {method: text}}, kind 'det' | 'cam' | None, selection dict | None). det cell text 'TP 5 · FP 1 · FN 0', cam 'in-box 62 %'."""
    rows = list(csv.DictReader(io.open(path, encoding="utf-8-sig", newline="")))
    if not rows: return {}, None, None
    hdr = {h.lower(): h for h in rows[0] if h}; key = next((hdr[c] for c in ("image", "sample", "frame", "id") if c in hdr), list(rows[0])[0])
    out = {}; kinds = set()
    for r in rows:
        smp = os.path.splitext(os.path.basename((r.get(key) or "").strip()))[0]
        for m in methods:
            t, f, n_, ib = (hdr.get(f"{p}_{m}".lower()) for p in ("tp", "fp", "fn", "inbox"))
            if t and f and n_ and (r.get(t) or "") != "":
                out.setdefault(smp, {})[m] = f"TP {int(float(r[t]))} · FP {int(float(r[f]))} · FN {int(float(r[n_]))}"; kinds.add("det")
            elif ib and (r.get(ib) or "") != "":
                out.setdefault(smp, {})[m] = f"in-box {100 * float(r[ib]):.0f} %"; kinds.add("cam")
    mp = os.path.splitext(path)[0] + ".meta.json"; sel = None
    if os.path.isfile(mp):
        try: sel = json.load(io.open(mp, encoding="utf-8-sig"))
        except Exception: sel = None
    return out, ("det" if "det" in kinds else ("cam" if kinds else None)), sel

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
    if out is not None: out = _gamma(out, getattr(a, "display_gamma", 1.0))      # --display-gamma: brighten dark inputs for display only (before the overlay is blended)
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
    if not a.width_mm:
        a.width_mm, _src = mf.default_width_mm(os.path.abspath(a.project), "full")
        if _src: print(f"[INFO] width: --width-mm not given, {a.width_mm:g} mm from {_src}")
    plt = mf.plt; plt.rcParams["savefig.pad_inches"] = 0   # finish() saves bbox_inches="tight": no pad, so the page is exactly --width-mm
    root = os.path.abspath(a.project); methods = a.methods.split(","); samples = a.samples.split(","); ncols = a.cols or len(methods); ngroups = math.ceil(len(methods) / ncols)
    nrows = len(samples); notes = []; mm = 25.4; pt = mm / 72   # pt = 1 pt in mm
    ST = load_style(root); fpt = ST.font_pt                      # figures.style: column labels / roles / cmap / font size (the directory names are the registry keys)
    explicit = bool(a.col_labels)
    col_lab = a.col_labels.split(",") if a.col_labels else [mname(m_) for m_ in methods]
    row_lab = [] if a.row_labels == "none" else (a.row_labels.split(",") if a.row_labels else list(samples))
    if len(col_lab) != len(methods) or (row_lab and len(row_lab) != nrows): raise SystemExit(f"[FAIL] --col-labels needs {len(methods)} entries and --row-labels {nrows} (or 'none')")
    if explicit:
        for m_, l_ in zip(methods, col_lab):
            if l_ not in _SEEN and _code(l_): _SEEN.add(l_); say("WARN" if ALLOW_CODE else "FAIL", f"column label {l_!r} reads like code: write a name a reader knows (figures.style.methods.{m_}.label) or pass --allow-code-labels")
    low_ = collections.Counter(m_.lower() for m_ in methods)
    dup_ = sorted(m_ for m_ in methods if low_[m_.lower()] > 1)
    if dup_: raise SystemExit(f"[FAIL] method directories {dup_} differ only by case: on Windows / macOS they are the same folder and one column would show the other's images; rename one (e.g. IRraw)")
    hl = {h for h in a.highlight.split(",") if h} or {m_ for m_ in methods if ST.is_ours(m_)}      # the framed column: --highlight, else the registry's ours
    cnames = a.class_names.split(",") if a.class_names else []
    cmap_name = a.cmap or ST.cmap
    if a.overlay_dir and cmap_name.lower().startswith(("jet", "rainbow", "gist_rainbow", "hsv")) and not ST.allow_jet:
        say("FAIL", f"--cmap {cmap_name} is a rainbow map (not perceptually uniform, unreadable in grayscale): refused, drawn with viridis; set figures.style.roles.allow_jet: true to keep it"); cmap_name = "viridis"
    cmap = plt.get_cmap(cmap_name); marks = collections.defaultdict(list)
    roles = {r_: ST.role(r_) for r_ in ("gt", "tp", "fp", "fn", "ours_frame")}
    counts_txt, cc_kind, selection = {}, None, None
    if a.cell_counts:
        if not os.path.isfile(a.cell_counts): raise SystemExit(f"[FAIL] --cell-counts {a.cell_counts} not found (samples.csv of select_samples.py)")
        counts_txt, cc_kind, selection = read_cell_counts(a.cell_counts, methods)
        if cc_kind is None: notes.append(f"--cell-counts {os.path.basename(a.cell_counts)} has no tp_<method>/fp_/fn_ or inbox_<method> column for any of --methods: no counts printed")
        else:
            lost = [s_ for s_ in samples if s_ not in counts_txt]
            if lost: notes.append(f"--cell-counts has no row for sample(s) {lost[:4]}: their cells print no counts")
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
    cw = (W - left - right - (ncols - 1) * gap) / ncols; ch = cw * aspect
    cnt_h = 1.45 * fpt * pt if cc_kind else 0.0; ph = ch + cnt_h        # a text line under every image (cell counts) makes the row pitch ph
    rows_h = nrows * ph + (nrows - 1) * gap
    top_m = 0.6 + (strip if cb_on and a.label_pos == "bottom" else 0); leg_on = bool(a.box_status and a.labels_dir and a.gt_col in methods)
    legend = ([("gt", "Ground truth")] if a.gt_col in methods else []) + [("tp", "TP (IoU >= 0.5)"), ("fp", "FP"), ("fn", "FN (missed ground truth)")]
    leg_rows, _lx = 1, left
    for _k, _nm in legend:                                                    # how many strip rows the legend needs at this width and font size
        _w = 6.0 + len(_nm) * 0.55 * fpt * pt + 3.0
        if _lx + _w > W - 0.6 and _lx > left: leg_rows += 1; _lx = left
        _lx += _w
    leg_h = (3.8 + 3.4 * (leg_rows - 1)) if leg_on else 0.0
    bot_m = 0.6 + (strip if cb_on and a.label_pos == "top" else 0) + leg_h
    H = top_m + ngroups * (rows_h + strip) + (ngroups - 1) * ggap + bot_m
    ppm = (a.cell_px / cw) if a.cell_px else a.dpi / mm
    Wp, Hp = int(round(W * ppm)), int(math.ceil(H * ppm)); cwp, chp = max(2, int(round(cw * ppm))), max(2, int(round(ch * ppm)))
    def cell_xy(gi, ci, si): return left + ci * (cw + gap), top_m + gi * (rows_h + strip + ggap) + (strip if a.label_pos == "top" else 0) + si * (ph + gap)
    bstat = bool(a.box_status)
    if bstat and not (a.labels_dir and a.gt_col in methods and any(cells[(a.gt_col, smp_)]["lb"] for smp_ in samples)):
        notes.append(f"--box-status needs --labels-dir and the --gt-col column ({a.gt_col}) among --methods with label files: ignored"); bstat = False
    lw_box = a.box_lw or max(0.8, min(1.0, cw * 0.035))   # printed pt, scaled to the cell, never thinner than 0.8 pt (thinner boxes vanish in print)
    if lw_box < 0.8: lw_box = 0.8; notes.append("--box-lw raised to the 0.8 pt printed floor")
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
                    arr[2:2 + isz, cwp - isz - 2:cwp - 2] = np.clip(_gamma(np.asarray(crop), getattr(a, "display_gamma", 1.0)), 0, 255)
                x, y = cell_xy(gi, ci, si); xp, yp = int(round(x * ppm)), int(round(y * ppm))
                canvas[yp:yp + chp, xp:xp + cwp] = arr[:Hp - yp, :Wp - xp]
    cbx = W - right + cbg; cb_top = top_m + (strip if a.label_pos == "top" else 0); cb_bot = cell_xy(ngroups - 1, 0, nrows - 1)[1] + ch
    if cb_on:
        x0p, x1p, y0p, y1p = int(round(cbx * ppm)), int(round((cbx + cbw) * ppm)), int(round(cb_top * ppm)), int(round(cb_bot * ppm))
        canvas[y0p:y1p, x0p:x1p] = (cmap(np.linspace(1, 0, y1p - y0p))[:, None, :3] * 255).astype(np.uint8)
    # ---- vector layer (axes in mm, y down)
    fig = plt.figure(figsize=(W / mm, H / mm)); ax = fig.add_axes([0, 0, 1, 1]); ax.imshow(canvas, extent=(0, W, H, 0), interpolation="none", aspect="auto", zorder=0)
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    src = []; counts = {}; sty = {}
    for gi in range(ngroups):
        for ci, mth in enumerate(methods[gi * ncols:(gi + 1) * ncols]):
            k = gi * ncols + ci; x0 = cell_xy(gi, ci, 0)[0]
            sty[mth] = dict(ST.columns(mth), label=col_lab[k])                       # what the source.csv records: the registry's color / line / marker, the label as drawn
            ty = cell_xy(gi, 0, 0)[1] - 0.7 if a.label_pos == "top" else cell_xy(gi, 0, nrows - 1)[1] + ph + 0.7
            t = ax.text(x0 + cw / 2, ty, col_lab[k], ha="center", va="bottom" if a.label_pos == "top" else "top", fontsize=fpt, fontweight="bold" if mth in hl else "normal", color=roles["ours_frame"] if mth in hl else "black")
            if not _fit(fig, t, cw * 0.98 / mm * fig.dpi): notes.append(f"column label '{col_lab[k]}' wider than its cell at the 5.2 pt floor: shorten it via --col-labels")
            for si, smp in enumerate(samples):
                c = cells[(mth, smp)]; x, y = cell_xy(gi, ci, si); nb = 0; bcol = ""; mk_ = marks.get((smp, mth), []); missed = []
                if not (c["img"] or c["ov"] or c["mk"]):
                    ax.add_patch(Rectangle((x, y), cw, ch, fill=False, ec="#999999", lw=0.4))
                elif c["lb"]:
                    iw, ih = Image.open(c["img"]).size if c["img"] else (1, 1)
                    base_col = roles["gt"] if mth == a.gt_col else ST.color(mth)             # GT: the gt role; a prediction column without match status: that method's registry colour
                    bcol = "status" if (bstat and mth != a.gt_col) else base_col
                    bxs = read_boxes(c["lb"], a.label_fmt, iw, ih, a.min_score or None); stat = [None] * len(bxs)
                    gcell = cells[(a.gt_col, smp)] if (bstat and mth != a.gt_col) else None
                    if gcell and gcell["lb"]:
                        giw, gih = Image.open(gcell["img"]).size if gcell["img"] else (iw, ih)
                        gtb = read_boxes(gcell["lb"], a.label_fmt, giw, gih); stat, mi = match_boxes(gtb, bxs, 0.5); missed = [gtb[i] for i in mi]
                        cnt = counts.setdefault(mth, [0, 0, 0]); cnt[0] += stat.count("tp"); cnt[1] += stat.count("fp"); cnt[2] += len(missed)
                    for (lab_, bx0, by0, bx1, by1), st_ in zip(bxs, stat):
                        ec_, ls_ = (roles[st_], ROLE_LS[st_]) if st_ else (base_col, "-")
                        ax.add_patch(Rectangle((x + bx0 * cw, y + by0 * ch), (bx1 - bx0) * cw, (by1 - by0) * ch, fill=False, ec=ec_, ls=ls_, lw=lw_box, zorder=3)); nb += 1
                        if cnames:
                            nm = cnames[int(lab_)] if lab_.isdigit() and int(lab_) < len(cnames) else lab_; up = by0 * ch > 2.4
                            ax.text(x + bx0 * cw, y + by0 * ch - (0.1 if up else -lw_box * pt), nm, fontsize=5.2, color=_on(ec_), ha="left", va="bottom" if up else "top", zorder=4, bbox=dict(fc=ec_, ec="none", pad=0.25))
                for lab_, bx0, by0, bx1, by1 in missed:                                   # ground truth this method missed: the fn role, dotted
                    ax.add_patch(Rectangle((x + bx0 * cw, y + by0 * ch), (bx1 - bx0) * cw, (by1 - by0) * ch, fill=False, ec=roles["fn"], ls=ROLE_LS["fn"], lw=lw_box, zorder=3))
                if inset and c["img"]:   # white frames: the zoomed crop (top-right) and the region it was cut from
                    isz = int(cwp * 0.42) / ppm; ax.add_patch(Rectangle((x + cw - isz - 2 / ppm, y + 2 / ppm), isz, isz, fill=False, ec="white", lw=0.6, zorder=3))
                    ax.add_patch(Rectangle((x + inset[0] * cw, y + inset[1] * ch), inset[2] * cw, inset[3] * ch, fill=False, ec="white", lw=0.4, zorder=3))
                for mx, my, mw, mh in mk_: ax.add_patch(Ellipse((x + mx * cw, y + my * ch), mw * cw, mh * ch, fill=False, ec=ST.ours_color, lw=max(0.6, lw_box), zorder=3))
                ctext = counts_txt.get(smp, {}).get(mth, "") if (cc_kind and mth != a.gt_col) else ""
                if ctext:                                                                 # "TP 5 · FP 1 · FN 0" / "in-box 62 %" under the image, at the registry's font size
                    t2 = ax.text(x + cw / 2, y + ch + 0.35, ctext, ha="center", va="top", fontsize=fpt, color="black", zorder=4)
                    if not _fit(fig, t2, cw * 0.98 / mm * fig.dpi): notes.append(f"cell text '{ctext}' wider than its cell at the 5.2 pt floor: use fewer columns or a wider --width-mm")
                src.append([smp, mth, c["img"] or "", c["ov"] or "", c["mk"] or "", nb, bcol, len(mk_), "yes" if mth in hl else "no",
                            sty[mth]["label"], sty[mth]["color"], sty[mth]["line"], sty[mth]["marker"], ctext])
            if mth in hl:
                fy0, fy1 = cell_xy(gi, ci, 0)[1] - gap / 2, cell_xy(gi, ci, nrows - 1)[1] + ph + gap / 2
                ax.add_patch(Rectangle((x0 - gap / 2, fy0), cw + gap, fy1 - fy0, fill=False, ec=roles["ours_frame"], lw=1.0, zorder=5))
    for si, lab_ in enumerate(row_lab):
        for gi in range(ngroups):
            t = ax.text(left / 2 - 0.2, cell_xy(gi, 0, si)[1] + ch / 2, lab_, rotation=90, ha="center", va="center", fontsize=fpt)
            if not _fit(fig, t, ch * 0.98 / mm * fig.dpi, "y"): notes.append(f"row label '{lab_}' longer than its cell at the 5.2 pt floor: shorten it via --row-labels")
    if cb_on:
        ax.add_patch(Rectangle((cbx, cb_top), cbw, cb_bot - cb_top, fill=False, ec="#333333", lw=0.4, zorder=5))
        ax.text(cbx + cbw / 2, cb_top - 0.5, cb_lab[1], ha="center", va="bottom", fontsize=fpt, fontweight="bold"); ax.text(cbx + cbw / 2, cb_bot + 0.5, cb_lab[0], ha="center", va="top", fontsize=fpt, fontweight="bold")
    if bstat:                                                                    # legend strip at the bottom, each swatch on a mid-grey chip (the light fn colour would vanish on white)
        lx = left; ly = H - leg_h + 1.9
        for key, name in legend:
            iw_ = 6.0 + len(name) * 0.55 * fpt * pt + 3.0
            if lx + iw_ > W - 0.6 and lx > left: lx = left; ly += 3.4
            ax.add_patch(Rectangle((lx - 0.4, ly - 0.9), 5.8, 1.8, fc="#6e6e6e", ec="none", zorder=5)); ax.plot([lx, lx + 5.0], [ly, ly], color=roles[key], ls=ROLE_LS[key], lw=max(0.8, lw_box), zorder=6)
            ax.text(lx + 6.0, ly, name, fontsize=fpt, ha="left", va="center", zorder=6); lx += iw_
    min_dpi = _min_dpi(root); emb = Wp / (W / mm)
    if emb < min_dpi * 0.985: notes.append(f"embedded raster {emb:.0f} dpi < target.min_dpi {min_dpi}: raise --dpi")
    if eff and min(eff) < min_dpi * 0.5: notes.append(f"source images give only {min(eff):.0f} dpi at print size (< half of min_dpi {min_dpi}): the grid is upsampled, not sharper; use larger source images or fewer columns")
    cn = fs.colour_name
    gt_drawn = any(r[1] == a.gt_col and r[5] for r in src)
    if bstat: boxes_cap = f" Boxes: {cn(roles['tp'])} solid = true positive (IoU >= 0.5 with a {a.gt_col} box), {cn(roles['fp'])} dashed = false positive, {cn(roles['fn'])} dotted = missed {a.gt_col} box."
    elif gt_drawn: boxes_cap = f" Boxes: {cn(roles['gt'])} = {a.gt_col}; other columns' boxes in their method colour."
    else: boxes_cap = ""
    cap = (f"Qualitative grid, {nrows} samples × {len(methods)} methods; photos embedded as one {Wp}×{Hp}px raster ({emb:.0f} dpi at {W:g} mm), frames/boxes/labels vector."
           + boxes_cap + (f" Overlay: {cmap_name} map blended at alpha {a.overlay_alpha:g}." if cb_on else "") + (f" Display gamma {a.display_gamma:g} (display only)." if abs(a.display_gamma - 1.0) > 1e-9 else ""))
    print(f"grid {Wp}×{Hp}px -> {emb:.0f} dpi embedded @ {W:g} mm; cell {cw:.1f}×{ch:.1f} mm; box line {lw_box:.2f} pt; cells {len(methods)}×{nrows}"
          + (f"; MISSING {len(missing)}: {missing[:6]}" if missing else "") + (f"; source images ≥ {min(eff):.0f} dpi" if eff else ""))
    for n in notes: print(f"[WARN] grid: {n}")
    if bstat: print("box status (IoU >= 0.5, class-aware; per method TP/FP/FN): " + "; ".join(f"{m_} {v_[0]}/{v_[1]}/{v_[2]}" for m_, v_ in counts.items()))
    # ---- what was drawn -> <out>.meta.json + <out>.caption.md (caption_draft.py): the caption states these facts, the author adds the takeaway
    used = (["gt"] if gt_drawn else []) + (["tp", "fp", "fn"] if bstat else []) + (["ours_frame"] if (hl and any(r[5] for r in src)) else [])
    sel_iou = (selection or {}).get("iou")
    meta = {"rows": nrows, "cols": list(methods), "styles": {m_: sty[m_] for m_ in methods if m_ in sty}, "gt_col": a.gt_col, "label_fmt": a.label_fmt if a.labels_dir else None, "box_status": bstat,
            "roles_used": used, "roles": {r_: roles[r_] for r_ in used}, "role_lines": dict(ROLE_LS), "iou": (0.5 if bstat else (sel_iou if cc_kind == "det" else None)),
            "min_score": a.min_score or None, "cell_counts": cc_kind, "overlay_alpha": a.overlay_alpha if cb_on else None, "display_gamma": a.display_gamma if abs(a.display_gamma - 1.0) > 1e-9 else None,
            "inset": inset, "selection": selection, "min_box_pt": round(lw_box, 2), "width_mm": W}
    if cb_on and any(c_["ov"] and c_["ov"].lower().endswith(".npy") for c_ in cells.values()): meta["cam"] = {"cmap": cmap_name, "norm": "per_image_minmax"}
    try:
        _mp, _cp = cd.write_files(os.path.splitext(os.path.join(root, a.out))[0], "grid", meta, ST)
        print(f"[INFO] caption draft (replace the <takeaway> sentence): {os.path.relpath(_cp, root)}; what was drawn: {os.path.relpath(_mp, root)}")
    except Exception as e: print(f"[WARN] grid: could not write the meta / caption draft ({type(e).__name__}: {e})")
    mf.finish(fig, a, src, ["sample", "method", "image", "overlay", "mask", "n_boxes", "box_color", "n_marks", "highlight", "label", "color", "line", "marker", "counts"], root, cap)
    return emb

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("sota", "multi", "ablation", "seeds"):
        p = sub.add_parser(n); p.add_argument("--csv", required=True); p.add_argument("--out", required=True); p.add_argument("--metrics", required=True)
        p.add_argument("--higher", default=""); p.add_argument("--lower", default=""); p.add_argument("--project", default="", help="read results.metric_direction / primary_direction from <project>/research-state.yaml"); p.add_argument("--caption", default="Caption."); p.add_argument("--label", default="tab:x"); p.add_argument("--decimals", type=int, default=3); p.add_argument("--md", action="store_true")
        p.add_argument("--numbers", action="store_true", help="also register every cell in <out-dir>/numbers.csv for the G6 numbers gate")
        p.add_argument("--ci-style", choices=["bracket", "pm", "none"], default="bracket", help="uncertainty from <metric>_lo/_hi (bracket, or pm = half-width) or <metric>_sd (pm); none = off")
        p.add_argument("--alpha", type=float, default=0.05, help="sig_<metric> columns holding p-values: significant when p < alpha"); p.add_argument("--sig-test", default="", help="text for the dagger footnote, e.g. 'paired bootstrap, 10k resamples' (the script never tests anything itself)")
        p.add_argument("--fit", choices=["auto", "linewidth", "columnwidth", "none"], default="auto", help="wrap the tabular in resizebox when the estimated width exceeds the target"); p.add_argument("--width-mm", type=float, default=0, help="target table width; default = venue template column (via --project) / 88 mm cs_conf / 170 mm"); p.add_argument("--font-pt", type=float, default=9.0, help="table font size in pt (small of a 10 pt class = 9)")
        p.add_argument("--allow-code-labels", action="store_true", help="a method / setting / component name that reads like code (chgate, F6R, out0) is a WARN instead of a FAIL; the default is to register a label in figures.style (figure_style.py init)")
        if n in ("sota", "multi"):
            p.add_argument("--delta", default="", help="'best' or a method name: final row = first --ours minus the strongest non-ours row (or that method)"); p.add_argument("--name-col", default="method"); p.add_argument("--group-col", default=""); p.add_argument("--ours", default=""); p.add_argument("--extra", default="", help="non-ranked columns e.g. Params,FLOPs"); p.add_argument("--cite-col", default="")
        if n == "multi": p.add_argument("--datasets", required=True); p.add_argument("--dataset-col", default="dataset"); p.add_argument("--dataset-labels", default="", help='display names for the dataset headers, e.g. "prostate_t1=Prostate ($K{=}6$),kidney_t1=Kidney"')
        if n == "ablation": p.add_argument("--components", required=True); p.add_argument("--ablation-plain", action="store_true", help="no red/blue, only bold full row")
        if n == "seeds": p.add_argument("--setting-col", default="setting"); p.add_argument("--seed-col", default="seed")
    g = sub.add_parser("grid"); g.add_argument("--root", required=True); g.add_argument("--methods", required=True); g.add_argument("--samples", required=True); g.add_argument("--out", required=True)
    g.add_argument("--inset", default=""); g.add_argument("--cols", type=int, default=0); g.add_argument("--width-mm", type=float, default=0.0, help="print width; default = the venue's full text width (CVPR 174.6 mm; state.target via --project), 183 mm without a venue"); g.add_argument("--cell-px", type=int, default=0, help="0 = auto from --dpi"); g.add_argument("--dpi", type=float, default=400)
    g.add_argument("--project", default=".", help="where figures.csv / research-state.yaml (target.min_dpi) live; --out is relative to it")
    g.add_argument("--labels-dir", default="", help="<dir>/<method>/<sample>.txt|json|xml"); g.add_argument("--label-fmt", choices=["yolo", "coco", "voc", "xyxy"], default="yolo"); g.add_argument("--gt-col", default="GT", help="column whose boxes use the gt role colour (yellow by default; and whose image is the base for CAM / mask columns without their own image)")
    g.add_argument("--box-status", action="store_true", help="colour predicted boxes by match status against the --gt-col boxes (IoU >= 0.5, class-aware): TP / FP / missed ground truth in the tp / fp / fn role colours of figures.style (green solid / orange dashed / light grey dotted by default) on the prediction's cell, legend strip, TP/FP/FN counts printed"); g.add_argument("--min-score", type=float, default=0.0, help="drop predicted boxes below this confidence (6th column of yolo / xyxy lines, 'score' in coco json)")
    g.add_argument("--class-names", default=""); g.add_argument("--box-lw", type=float, default=0, help="printed pt; 0 = scaled to the cell (0.8-1.0 pt); never below 0.8 pt")
    g.add_argument("--overlay-dir", default="", help="<dir>/<method>/<sample>.npy (2-D map, min-max normalised, colour-mapped) or .png (used as is)"); g.add_argument("--overlay-alpha", type=float, default=0.55); g.add_argument("--cmap", default="", help="default = figures.style.cmap (viridis); jet / rainbow maps are refused unless figures.style.roles.allow_jet is true")
    g.add_argument("--colorbar", default="Low,High", help="'bottom,top' end labels of the shared vertical colorbar; 'none' = no bar")
    g.add_argument("--row-labels", default="", help="comma list; default = sample names; 'none' = no row labels"); g.add_argument("--col-labels", default="", help="comma list; default = method names"); g.add_argument("--label-pos", choices=["bottom", "top"], default="bottom", help="column labels under each row group (default) or above it")
    g.add_argument("--highlight", default="", help="method(s) framed in the ours_frame role colour (Fig. 4 'Ours' column); default = figures.style.ours"); g.add_argument("--marks", default="", help="csv sample,method,cx,cy,w,h (0-1 cell coords): ellipses in the ours colour")
    g.add_argument("--mask-dir", default="", help="<dir>/<method>/<sample>.png with class ids (0 = background, unpainted)"); g.add_argument("--palette", type=int, default=0, help="number of classes incl. background (0 = whole 20-colour palette)"); g.add_argument("--mask-alpha", type=float, default=0.6)
    g.add_argument("--cell-counts", default="", help="samples.csv of select_samples.py: prints 'TP 5 · FP 1 · FN 0' (det) or 'in-box 62 %%' (cam) under every cell at figures.style.font_pt; <csv stem>.meta.json (the selection rule and win / loss counts) goes into the caption draft")
    g.add_argument("--display-gamma", type=float, default=1.0, help="display-only brightening of the photos, out = in ** gamma (0.5 lifts dark inputs; nothing but the shown pixels changes; the caption draft says so)")
    g.add_argument("--allow-code-labels", action="store_true", help="a column label that reads like code (chgate, IRraw, out0) is a WARN instead of a FAIL")
    g.add_argument("--gap-mm", type=float, default=0.4); g.add_argument("--aspect", default="auto", help="cell height / width; auto = first image")
    ap.add_argument("--labels", default="", help='display labels, e.g. "AP50=AP$_{50}$,AP50_95=AP$_{50:95}$"')
    a = ap.parse_args()
    for kv in filter(None, a.labels.split(",")):
        k, v = kv.split("=", 1); LABELS[k] = v
    for kv in filter(None, (getattr(a, "dataset_labels", "") or "").split(",")):
        k, v = kv.split("=", 1); DLABELS[k] = v
    global ALLOW_CODE
    ALLOW_CODE = bool(getattr(a, "allow_code_labels", False))
    if a.cmd == "grid": det_grid(a); sys.exit(FAILS)
    load_style(a.project or ".")
    if a.project:
        import yaml
        sp = os.path.join(a.project, "research-state.yaml")
        if os.path.exists(sp):
            _st = yaml.safe_load(io.open(sp, encoding="utf-8")) or {}; STATE.update(_st.get("results") or {}); TARGET.update(_st.get("target") or {})
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
    sys.exit(FAILS)

if __name__ == "__main__":
    main()
