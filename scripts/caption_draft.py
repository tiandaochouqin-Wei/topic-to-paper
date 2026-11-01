# -*- coding: utf-8 -*-
"""P5 — figure captions generated from what was DRAWN, and a check that the LaTeX caption still agrees with the figure.

Round-3 figure review: hand-written captions contradicted the figures (a "zoom" caption after the inset was dropped; "green = GT, red = predictions" after the
box-status colours changed). Every generator therefore records what it drew in <out>.meta.json and a DRAFT caption in <out>.caption.md; the author replaces the first
sentence (a takeaway placeholder) and keeps the factual rest in sync.

  python caption_draft.py draft --meta figures/fig_curves.meta.json [--kind curves] [--project .]    print the draft caption
  python caption_draft.py check [--project .] [--tex paper/latex/main.tex]
        for every figures/*.meta.json whose figure is \\includegraphics-ed in the LaTeX source, compare the caption with the meta:
        FAIL  the caption claims an inset / zoom but none was drawn; a colour word contradicts a role colour ("green = ground truth" while gt is yellow)
        WARN  an inset was drawn and the caption does not say so; bands / error bars / whiskers drawn but not explained; smoothing, normalisation, display gamma,
              frame selection not mentioned; a delta annotation without the metric direction; the caption still contains "<takeaway"
        Exit code = number of FAIL lines.

Python API (generators import it):
  import caption_draft as cd
  cap = cd.draft(kind, meta, style)                       # str; kind in KINDS (aliases: bars/main, bland-altman)
  meta_path, cap_path = cd.write_files(out_base, kind, meta, style)   # <out_base>.meta.json (+ "kind") and <out_base>.caption.md

meta (every key optional; a generator fills what it drew, the caption states only that):
  common   y_label, y_unit, x_label, x_unit, metric (a results column: the direction comes from metric_direction.py), direction ("higher"|"lower"), results (state.results
           for metric_direction), series [names in draw order], ours, baseline, n (int or {series: n}), n_seeds, panels [names], panel_label, title_hint,
           logx, logy, synthetic, watermark
  bands    band ("sd"|"minmax"|"ci95"|"sem"|"none"), band_n; error_bars ("sd"|"ci95"|...); dots ("seeds")
  curves   ema {alpha, init: "first", raw_line: bool} | alpha number, end_x (epoch of the end labels), end_labels "raw"|"smoothed", inset {x0, x1, x_name} | "x0:x1",
           annotate {x, ours, baseline, delta, unit, metric, direction}
  ablation reference, band_sigma ("±2σ"), resolvable_n, n_ablations
  stems    item, group, k_above, n_items | box: whis [lo, hi], vline | hbar: fmt, group | roc/pr: ci "bootstrap:200", auc {series: value}, prevalence, chance
  calib    bins, strategy, ece, brier | confusion: normalize, classes | bland_altman: unit, loa (1.96), slope_shown | tradeoff: x_label, y_label, x_direction, y_direction,
           front (bool), datasets [names], dataset_encoding "marker"|"fill"|"panel", leader_lines, y_norm
  grid     rows (samples), cols (methods), gt_col, label_fmt, box_status (bool), roles_used [gt,tp,fp,fn], roles {role: hex} (actual), role_lines {role: linestyle},
           iou, min_score, cell_counts ("det"|"cam"|None), cam {cmap, norm: "per_image_minmax"}, overlay_alpha, display_gamma, inset (crop box or {…}),
           selection (the samples.meta.json dict of select_samples.py), min_box_pt
  architecture  model, stages [names], ours_modules [names], n_params, shapes (bool), input_shape, engine
"""
import argparse, glob, io, json, os, re, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import figure_style as fs
import metric_direction as md

KINDS = ("curves", "bars", "main", "ablation", "seeds", "stems", "box", "hbar", "roc", "pr", "calibration", "confusion", "bland_altman", "tradeoff", "grid", "architecture")
ALIASES = {"bland-altman": "bland_altman", "blandaltman": "bland_altman", "main": "bars", "calib": "calibration", "det": "grid", "cam": "grid", "qualitative": "grid", "arch": "architecture"}
TAKEAWAY = "<takeaway: one sentence that states what this figure shows, with the number that carries it (e.g. which method wins, by how much, on what)>"
ROLE_LINE = {"gt": "-", "tp": "-", "fp": "--", "fn": ":"}


# ------------------------------------------------------------------ small helpers
def _g(meta, *keys, default=None):
    for k in keys:
        if meta.get(k) not in (None, "", [], {}): return meta[k]
    return default

def _num(v, spec="g"):
    try: return format(float(v), spec)
    except (TypeError, ValueError): return str(v)

def _join(items, last="and"):
    items = [str(x) for x in items if str(x)]
    return "" if not items else (items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {last} " + items[-1])

def _direction(meta, metric=None):
    d = meta.get("direction")
    if d in ("higher", "lower"): return d
    for m in (metric, meta.get("metric"), meta.get("y_label")):
        if m:
            try:
                d = md.direction(str(m), meta.get("results"))
            except ValueError: d = None
            if d: return d
    return None

def _dir_text(d): return {"higher": "higher is better", "lower": "lower is better"}.get(d, "")

def _axis(label, unit):
    label = str(label or "").strip(); unit = str(unit or "").strip()
    if not label: return ""
    return label if (not unit or unit in label) else f"{label} ({unit})"

def _sty(style, meta, name, i=None):
    """what was drawn for a series: meta.styles[name] ({label, color, line, marker}, written by the generator) over the registry"""
    d = dict(style.columns(name, i)); d.update({k: v for k, v in ((meta.get("styles") or {}).get(name) or {}).items() if v not in (None, "")})
    return d

def _labels(style, names, meta=None): return [_sty(style, meta or {}, n)["label"] for n in names]

def _look(style, meta, name, i=None):
    """'thick solid red' / 'dashed dark grey' from what was drawn"""
    d = _sty(style, meta, name, i); ls = d["line"]
    if isinstance(ls, str) and ls.startswith("("):
        try: ls = fs._parse_line(ls)
        except fs.StyleError: pass
    return (("thick " if style.is_ours(name) else "") + f"{fs.line_word(ls)} {fs.colour_name(d['color'])}").strip()

def _series_sentence(style, meta):
    names = style.order(_g(meta, "series", default=[]) or [])
    if not names: return ""
    ours = [n for n in names if style.is_ours(n)] or ([meta["ours"]] if meta.get("ours") in names else [])
    base = [n for n in names if n not in ours]
    parts = []
    if ours: parts.append(f"{_join([_sty(style, meta, n)['label'] for n in ours])} is the {_look(style, meta, ours[0])} line")
    else: parts.append("No method is singled out: all series are drawn with equal weight")
    if base:
        parts.append("baselines: " + ", ".join(f"{_sty(style, meta, n, i + 1)['label']} ({_look(style, meta, n, i + 1)})" for i, n in enumerate(base[:8]))
                     + (f"; {len(base) - 8} more in distinct colours and markers" if len(base) > 8 else ""))
    t = "; ".join(parts)
    return t[:1].upper() + t[1:] + "."

def _band_text(meta):
    b = meta.get("band"); n = meta.get("band_n") or meta.get("n_seeds")
    if b in (None, "", "none", False): return ""
    what = {"sd": "mean ± s.d.", "minmax": "min–max range", "ci95": "95 % confidence interval of the mean", "sem": "mean ± s.e.m."}.get(str(b), str(b))
    return f"Shaded band: {what}" + (f" over {n} seeds" if n else "") + "."

def _bars_text(meta):
    e = meta.get("error_bars")
    if e in (None, "", "none", False): return ""
    what = {"sd": "± s.d.", "ci95": "95 % confidence intervals", "sem": "± s.e.m.", "minmax": "min–max"}.get(str(e), str(e))
    n = meta.get("n_seeds") or (meta.get("n") if not isinstance(meta.get("n"), dict) else None)
    return f"Error bars: {what}" + (f" over {n} seeds" if n else "") + (", dots = individual seeds" if meta.get("dots") else "") + "."

def _n_per_group(meta):
    n = meta.get("n")
    if isinstance(n, dict) and n:
        vals = sorted(set(n.values()))
        return ("n = %s per group." % vals[0]) if len(vals) == 1 else "n per group: " + ", ".join(f"{k} {v}" for k, v in n.items()) + "."
    if isinstance(n, (int, float)): return f"n = {int(n)}."
    return ""

def _ema_text(meta):
    e = meta.get("ema")
    if isinstance(e, (int, float)) and not isinstance(e, bool): e = {"alpha": e}
    if not e: return ""
    a = e.get("alpha"); init = "the first value" if e.get("init", "first") == "first" else str(e.get("init"))
    t = f"Lines are exponential moving averages (EMA α = {_num(a)}, initialised at {init})" if a is not None else "Lines are exponentially smoothed"
    t += "; the grey line behind is the raw seed mean." if e.get("raw_line", True) else "."
    x = meta.get("end_x")
    if x is not None:
        t += f" End labels are {'raw' if meta.get('end_labels', 'raw') == 'raw' else 'smoothed'} means at {meta.get('x_name') or 'x'} {_num(x)}."
    return t

def _inset_text(meta):
    ins = meta.get("inset")
    if not ins: return ""
    if isinstance(ins, str): x0, _, x1 = ins.partition(":"); ins = {"x0": x0, "x1": x1}
    if isinstance(ins, dict) and ins.get("x0") not in (None, ""):
        nm = ins.get("x_name") or meta.get("x_name") or "x"
        return f"Inset: {nm}s {ins['x0']}–{ins['x1']} (the grey rectangle marks the zoomed region)."
    if isinstance(ins, (list, tuple)) and len(ins) == 4: return f"Inset: enlarged crop (x {ins[0]:g}, y {ins[1]:g}, w {ins[2]:g}, h {ins[3]:g} of the image)."
    return "Inset: zoomed region."

def _annotate_text(meta, style):
    an = meta.get("annotate")
    if not an: return ""
    d = _direction(meta, an.get("metric")) or _direction(meta) or an.get("direction")
    ours = style.label(an.get("ours") or meta.get("ours") or "ours"); base = style.label(an.get("baseline") or meta.get("baseline") or "the baseline")
    metric = an.get("label") or meta.get("y_label") or fs.humanise(an.get("metric") or "metric")
    t = f"Δ = {ours} − {base}"
    if an.get("x") is not None: t += f" at {meta.get('x_name') or 'x'} {_num(an['x'])}"
    if an.get("delta") is not None: t += f" (Δ {metric} {float(an['delta']):+.2f}{(' ' + an['unit']) if an.get('unit') else ''}"
    else: t += f" (Δ {metric}"
    return t + (f", {_dir_text(d)}" if d else "") + ")."

def _roles_text(style, meta):
    used = _g(meta, "roles_used", default=None)
    if used is None and meta.get("box_status"): used = ["gt", "tp", "fp", "fn"]
    if not used: return ""
    cols = meta.get("roles") or {}; lines = {**ROLE_LINE, **(meta.get("role_lines") or {})}; items = []
    for r in ("gt", "tp", "fp", "fn"):
        if r not in used: continue
        c = cols.get(r) or style.role(r); w = fs.colour_name(c)
        items.append(f"{w} {fs.line_word(lines[r])} = {fs.ROLE_WORDS[r]}" if r != "gt" or "tp" in used else f"{w} = {fs.ROLE_WORDS[r]}")
    if "ours_frame" in used: items.append(f"a {fs.colour_name(cols.get('ours_frame') or style.role('ours_frame'))} frame marks our method")
    return ("Boxes: " + ", ".join(items) + ".") if items else ""

def _selection_text(sel, meta):
    if not sel: return ""
    t = "Frames were chosen automatically" + (f": {sel['rule']}" if sel.get("rule") else "") + "."
    n, w, l = sel.get("n_images"), sel.get("wins"), sel.get("losses")
    if n:
        t += f" Over all {n} frames our method is better than the best baseline on {w}, worse on {l}" + (f" and tied on {sel['ties']}" if sel.get("ties") is not None else "") + "."
    nc = sel.get("n_counter")
    if nc: t += f" {nc} counter-example(s) where it is clearly worse are listed in the supplementary material" + (f" ({_join(sel.get('counter_examples', [])[:4])})" if sel.get("counter_examples") else "") + "."
    if sel.get("typical"): t += f" {len(sel['typical'])} frame(s) with a median score are shown for context."
    return t

def _tail(meta, style):
    """sentences common to every figure: n per group, synthetic watermark"""
    out = [_n_per_group(meta)]
    if meta.get("synthetic") or meta.get("watermark"): out.append("Synthetic demonstration data (watermarked); not a result.")
    return [x for x in out if x]

def _panels(meta, style):
    ps = meta.get("panels")
    if not ps: return ""
    pl = meta.get("panel_label") or "panel"
    return f"One panel per {pl}: " + _join([style.dataset(p)["label"] if meta.get("panel_label") in (None, "dataset") else str(p) for p in ps]) + "."


# ------------------------------------------------------------------ one builder per kind
def _curves(meta, style):
    y = _axis(meta.get("y_label"), meta.get("y_unit")) or "the metric"; x = _axis(meta.get("x_label"), meta.get("x_unit")) or "x"
    d = _direction(meta)
    s = [f"{y} versus {x} for {_join(_labels(style, style.order(meta.get('series') or []), meta))}." if meta.get("series") else f"{y} versus {x}."]
    if d: s.append(f"{y.split(' (')[0]}: {_dir_text(d)}.")
    s += [_panels(meta, style), _series_sentence(style, meta), _band_text(meta), _ema_text(meta), _inset_text(meta), _annotate_text(meta, style)]
    if meta.get("logx") or meta.get("logy"): s.append(f"Logarithmic {_join([a for a, f in (('x', meta.get('logx')), ('y', meta.get('logy'))) if f])} axis.")
    return s + _tail(meta, style)

def _bars(meta, style):
    y = _axis(meta.get("y_label"), meta.get("y_unit")) or "the metric"; d = _direction(meta)
    names = _labels(style, style.order(meta.get("series") or []), meta)
    s = [f"Grouped bars: {y} per {meta.get('x_label') or 'condition'}" + (f", one bar per method ({_join(names)})" if names else "") + "."]
    if d: s.append(f"{y.split(' (')[0]}: {_dir_text(d)}.")
    s += [_bars_text(meta), _series_sentence(style, meta) if meta.get("series") else ""]
    if meta.get("logy"): s.append("Logarithmic y axis.")
    return s + _tail(meta, style)

def _ablation(meta, style):
    ref = style.label(meta.get("reference")) if meta.get("reference") else "the reference"; d = _direction(meta)
    y = _axis(meta.get("y_label") or "Δ " + str(meta.get("metric") or "metric"), meta.get("y_unit"))
    s = [f"Change in {meta.get('metric') or 'the metric'} of each ablation relative to {ref} ({y})."]
    if d: s.append(f"A negative bar is {'an improvement' if d == 'lower' else 'a drop'} ({_dir_text(d)}).")
    sig = meta.get("band_sigma") or "±2σ"
    s.append(f"The grey band is the seed noise ({sig} of the reference over {meta.get('n_seeds') or 'its'} seeds); bars inside the band are greyed because the change is not resolvable from seed noise.")
    if meta.get("resolvable_n") is not None: s.append(f"{meta['resolvable_n']} of {meta.get('n_ablations', '?')} ablations are resolvable.")
    return s + _tail(meta, style)

def _seeds(meta, style):
    y = _axis(meta.get("y_label"), meta.get("y_unit")) or "the metric"; d = _direction(meta)
    s = [f"Seed stability of {_join(_labels(style, meta.get('series') or [], meta))}: {y}, mean ± s.d. over {meta.get('n_seeds') or 'the'} seeds, dots = individual seeds."]
    if d: s.append(f"{_dir_text(d).capitalize()}.")
    return s + _tail(meta, style)

def _stems(meta, style):
    item = meta.get("item") or "item"; xl = _axis(meta.get("x_label"), meta.get("x_unit")) or "baseline"; yl = _axis(meta.get("y_label"), meta.get("y_unit")) or "ours"; d = _direction(meta)
    s = [f"Paired comparison per {item}: baseline ({xl}) versus our method ({yl}); the dashed line is y = x and each stem runs from it to one {item}; the label above a point is the gain."]
    if meta.get("k_above") is not None: s.append(f"{meta['k_above']} of {meta.get('n_items', '?')} {item}s lie above y = x.")
    if meta.get("group"): s.append(f"Colour encodes the {meta['group']}.")
    if d: s.append(f"{_dir_text(d).capitalize()}.")
    return s + _tail(meta, style)

def _box(meta, style):
    v = _axis(meta.get("y_label") or meta.get("value"), meta.get("y_unit")) or "value"; w = meta.get("whis") or [5, 95]
    s = [f"{v} per {meta.get('group') or 'group'}. Boxes span the quartiles, the line is the median, whiskers are the {_num(w[0])}th and {_num(w[1])}th percentiles."]
    if meta.get("vline") is not None: s.append(f"Vertical line: {_num(meta['vline'])}.")
    if _direction(meta): s.append(f"{_dir_text(_direction(meta)).capitalize()}.")
    return s + _tail(meta, style)

def _hbar(meta, style):
    v = _axis(meta.get("y_label") or meta.get("value"), meta.get("y_unit")) or "value"
    s = [f"{v} per {meta.get('group') or 'group'}; the value is printed at the bar end and bars left of the zero line are negative." + (" Rows of one group are averaged." if (meta.get("n") or 1) not in (1, None) else "")]
    if _direction(meta): s.append(f"{_dir_text(_direction(meta)).capitalize()}.")
    return s + _tail(meta, style)

def _binary(meta, style, kind):
    xn, yn = ("false-positive rate", "true-positive rate") if kind == "roc" else ("recall", "precision")
    s = [f"{'ROC' if kind == 'roc' else 'Precision–recall'} curves ({yn} versus {xn}) for {_join(_labels(style, style.order(meta.get('series') or []), meta))}." if meta.get("series") else f"{'ROC' if kind == 'roc' else 'Precision–recall'} curves."]
    s.append("Dotted diagonal: chance." if kind == "roc" else "Dotted horizontal line: prevalence (a classifier at chance).")
    s.append(f"The legend gives {'AUC' if kind == 'roc' else 'average precision'}" + (f" with the 95 % interval of a stratified bootstrap ({str(meta['ci']).split(':')[-1]} resamples); the shaded band is the same interval." if meta.get("ci") else "."))
    s.append("Higher is better.")
    return s + _tail(meta, style)

def _calibration(meta, style):
    s = ["Reliability diagram: observed frequency versus mean predicted confidence per " + ("equal-count (quantile)" if meta.get("strategy") == "quantile" else "equal-width") + f" bin ({meta.get('bins', 10)} bins); marker area is proportional to the bin count, hollow markers have fewer than 5 samples; the dashed diagonal is perfect calibration. The strip below shows the histogram of predictions."]
    s.append("ECE and Brier score are in the legend; lower is better." if (meta.get("ece") is not None or meta.get("brier") is not None) else "Lower ECE and Brier score are better.")
    return s + _tail(meta, style)

def _confusion(meta, style):
    s = ["Confusion matrix: rows are true classes, columns predictions; each cell shows the count" + (" and the row-normalised percentage" if meta.get("normalize", "true") == "true" else "") + "."]
    s.append("Per-class recall, precision and support are listed in the source data.")
    return s + _tail(meta, style)

def _bland(meta, style):
    u = f" in {meta['unit']}" if meta.get("unit") else ""
    s = [f"Bland–Altman plot: difference between the two measurements{u} versus their mean; the solid line is the bias and the dashed lines are the limits of agreement (bias ± {_num(meta.get('loa', 1.96))} s.d. of the differences)."]
    if meta.get("slope_shown"): s.append("The dash-dotted line is the regression of the difference on the mean (slope ± 95 % CI in the source data): proportional bias.")
    return s + _tail(meta, style)

def _tradeoff(meta, style):
    xl = _axis(meta.get("x_label"), meta.get("x_unit")) or "cost"; yl = _axis(meta.get("y_label"), meta.get("y_unit")) or "quality"
    dx, dy = meta.get("x_direction") or _direction({"metric": meta.get("x_metric") or meta.get("x_label")}), meta.get("y_direction") or _direction({"metric": meta.get("y_metric") or meta.get("y_label")})
    s = [f"{yl} versus {xl} for {_join(_labels(style, style.order(meta.get('series') or []), meta))}." if meta.get("series") else f"{yl} versus {xl}."]
    dirs = [f"{a.split(' (')[0]}: {_dir_text(d)}" for a, d in ((xl, dx), (yl, dy)) if d]
    if dirs: s.append("; ".join(dirs)[:1].upper() + "; ".join(dirs)[1:] + ".")
    if meta.get("front"): s.append("The line connects the Pareto-optimal methods.")
    ds = meta.get("datasets")
    if ds:
        enc = {"marker": "marker shape", "fill": "filled versus open markers", "panel": "separate panels"}.get(meta.get("dataset_encoding", "marker"), "marker shape")
        s.append("Datasets are encoded by " + enc + " (" + _join([f"{style.dataset(d)['label']}" for d in ds]) + "), colour identifies the method.")
    if meta.get("leader_lines"): s.append("Thin leader lines connect displaced labels to their points.")
    if meta.get("y_norm") not in (None, "", "none"): s.append(f"The y axis is normalised ({meta['y_norm']}).")
    ours = [n for n in (meta.get("series") or []) if style.is_ours(n)]
    if ours: s.append(f"{_sty(style, meta, ours[0])['label']} is drawn in {fs.colour_name(_sty(style, meta, ours[0])['color'])}; baselines in other colours.")
    return s + _tail(meta, style)

def _grid(meta, style):
    rows, cols = meta.get("rows"), meta.get("cols")
    s = ["Qualitative comparison: " + (f"rows are {len(rows) if isinstance(rows, list) else rows} samples" if rows else "rows are samples") + (f", columns are {_join(_labels(style, cols, meta))}" if isinstance(cols, list) and cols else ", columns are methods") + "."]
    ins = _inset_text(meta)
    if ins: s.append(ins.replace("Inset: ", "Inset (top-right of each image): ", 1))
    cam = meta.get("cam")
    if cam:
        s.append(f"Activation maps are {'min–max normalised per image' if cam.get('norm', 'per_image_minmax') == 'per_image_minmax' else cam.get('norm')}, colour map {cam.get('cmap') or style.cmap}" + (f", blended at α = {_num(meta['overlay_alpha'])}" if meta.get("overlay_alpha") is not None else "") + ".")
    rt = _roles_text(style, meta)
    if rt: s.append(rt + (f" Matching at IoU ≥ {_num(meta['iou'])}" + (f", predictions with confidence ≥ {_num(meta['min_score'])} only" if meta.get("min_score") else "") + "." if meta.get("iou") else ""))
    if meta.get("cell_counts") == "det": s.append("Under each image: TP · FP · FN counts.")
    elif meta.get("cell_counts") == "cam": s.append("Under each image: share of the activation mass inside the ground-truth boxes (in-box share).")
    if meta.get("display_gamma") not in (None, "", 1, 1.0): s.append(f"Images are brightened for display only (gamma {_num(meta['display_gamma'])}); no model input was changed.")
    s.append(_selection_text(meta.get("selection"), meta))
    if meta.get("min_box_pt"): s.append(f"Box lines are {_num(meta['min_box_pt'])} pt or thicker.")
    return s + _tail(meta, style)

def _architecture(meta, style):
    s = [f"Architecture of {meta.get('model') or 'the model'}" + (f" ({_join(meta['stages'])})" if meta.get("stages") else "") + "."]
    if meta.get("ours_modules"): s.append(f"Modules of our method ({_join(meta['ours_modules'])}) are filled in {fs.colour_name(style.ours_color)}; all other modules are light grey.")
    if meta.get("shapes"): s.append("Edge labels give tensor shapes" + (f" for a {meta['input_shape']} input" if meta.get("input_shape") else "") + " where the shape changes.")
    if meta.get("n_params") is not None: s.append(f"{_num(meta['n_params'], ',.0f')} parameters in total.")
    return s + _tail(meta, style)

_BUILD = {"curves": _curves, "bars": _bars, "ablation": _ablation, "seeds": _seeds, "stems": _stems, "box": _box, "hbar": _hbar,
          "roc": lambda m, s: _binary(m, s, "roc"), "pr": lambda m, s: _binary(m, s, "pr"), "calibration": _calibration, "confusion": _confusion,
          "bland_altman": _bland, "tradeoff": _tradeoff, "grid": _grid, "architecture": _architecture}

def norm_kind(kind):
    k = str(kind or "").strip().lower().replace(" ", "_")
    k = ALIASES.get(k, k)
    if k not in _BUILD: raise ValueError(f"unknown figure kind {kind!r}; use one of {sorted(set(KINDS) - {'main'})}")
    return k

def draft(kind, meta, style=None):
    """caption DRAFT: the first sentence is the takeaway placeholder `<takeaway: …>` the author must replace; the rest states, from meta only, what was drawn"""
    style = style or fs.Style(None); meta = meta or {}
    parts = [TAKEAWAY] + [x for x in _BUILD[norm_kind(kind)](meta, style) if x]
    return re.sub(r"\s+", " ", " ".join(p.strip() for p in parts)).strip()

def write_files(out_base, kind, meta, style=None):
    """<out_base>.meta.json (meta + kind) and <out_base>.caption.md; out_base without extension. -> (meta_path, caption_path)"""
    base = os.path.splitext(out_base)[0] if os.path.splitext(out_base)[1].lower() in (".png", ".pdf", ".svg", ".jpg") else out_base
    os.makedirs(os.path.dirname(os.path.abspath(base)) or ".", exist_ok=True)
    k = norm_kind(kind); m = dict(meta or {}); m["kind"] = k
    mp, cp = base + ".meta.json", base + ".caption.md"
    with io.open(mp, "w", encoding="utf-8", newline="\n") as f: json.dump(m, f, ensure_ascii=False, indent=1, default=str)
    with io.open(cp, "w", encoding="utf-8", newline="\n") as f: f.write(draft(k, m, style) + "\n")
    return mp, cp


# ------------------------------------------------------------------ check
COLOURS = r"light gr[ae]y|dark gr[ae]y|gr[ae]y|silver|black|white|red|crimson|orange|yellow|gold|amber|green|teal|cyan|blue|navy|purple|violet|magenta|pink|brown"
FAMILY = {"light grey": "grey", "dark grey": "grey", "gray": "grey", "light gray": "grey", "dark gray": "grey", "silver": "grey", "light grey ": "grey", "crimson": "red", "dark red": "red",
          "gold": "yellow", "amber": "yellow", "olive": "yellow", "cyan": "teal", "navy": "blue", "violet": "purple", "magenta": "pink", "white": "white", "black": "black"}
ROLE_RE = [("fn", r"missed(?: ground[- ]truth| objects?| detections?| targets?)?|false[- ]negatives?|\bFN\b|undetected"),
           ("fp", r"false[- ]positives?|\bFPs?\b|false alarms?|spurious"),
           ("tp", r"true[- ]positives?|\bTPs?\b|correct(?:ly)? (?:detected|matched)|matched"),
           ("gt", r"ground[- ]truth|\bGT\b")]
INSET_RE = re.compile(r"\binsets?\b|\bzoom(?:ed|s)?\b|\bmagnif\w+|\benlarge\w*|\bclose-?ups?\b", re.I)
BAND_RE = re.compile(r"shad(?:ed|ing)|\bbands?\b|s\.d\.|\bsd\b|std|standard deviation|confidence|\bCI\b|interval|error bars?|whiskers?|min.max|range|s\.e\.m|\bsem\b|±", re.I)
DIR_RE = re.compile(r"better|lower|higher|↑|↓|improvement", re.I)
SMOOTH_RE = re.compile(r"smooth|\bEMA\b|moving average|exponential", re.I)
NORM_RE = re.compile(r"normali[sz]|min.max|scaled", re.I)
GAMMA_RE = re.compile(r"gamma|brighten|display", re.I)
SELECT_RE = re.compile(r"chosen|selected|selection|picked|representative|cherry|criterion|automatic", re.I)

def _fam(w):
    w = w.lower().strip(); return FAMILY.get(w, w)

def colour_role_pairs(text):
    """[(colour word, role)] found in single clauses of a plain caption: one colour and one role in the same clause (split at , ; . :  and 'and')"""
    out = []
    for clause in re.split(r"[;.,]|\s+and\s+|\s+while\s+|\s+whereas\s+", text):
        cols = re.findall(r"\b(" + COLOURS + r")\b", clause, re.I)
        if len(set(_fam(c) for c in cols)) != 1: continue
        roles = []; rest = clause
        for r, pat in ROLE_RE:
            for m in re.finditer(pat, rest, re.I):
                roles.append((r, m.start())); rest = rest[:m.start()] + " " * (m.end() - m.start()) + rest[m.end():]
        if len({r for r, _ in roles}) != 1: continue
        out.append((cols[0].lower(), roles[0][0]))
    return out

def _read_json(p):
    try:
        with io.open(p, encoding="utf-8-sig") as f: d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception: return None

def tex_captions(tex_path):
    """[{stems, caption (plain text), raw}] per figure environment of a LaTeX source (\\input expanded, comments stripped)"""
    import tex_to_md as t2m
    text = t2m.expand_inputs(tex_path); envs = []
    for m in re.finditer(r"\\begin\{((?:sideways)?figure\*?)\}(.*?)\\end\{\1\}", text, re.S):
        body = m.group(2)
        stems = {os.path.splitext(os.path.basename(x.strip().replace("\\", "/")))[0] for x in re.findall(r"\\includegraphics\*?(?:\[[^\]]*\])?\s*\{([^}]+)\}", body)}
        top = re.sub(r"\\begin\{subfigure\}.*?\\end\{subfigure\}", "", body, flags=re.S)
        cm = re.search(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", top)
        if not cm: continue
        raw = t2m.balanced(top, cm.end() - 1)[0]
        try:
            import figure_review as fr
            plain = fr.tex_plain(raw)
        except Exception:
            plain = re.sub(r"\s+", " ", re.sub(r"[{}$~\\]", " ", t2m.unbrace(raw))).strip()
        envs.append({"stems": stems, "caption": plain, "raw": raw})
    return envs

FAILS = 0; WARNS = 0

def say(sev, msg):
    global FAILS, WARNS
    if sev == "FAIL": FAILS += 1
    elif sev == "WARN": WARNS += 1
    print(f"[{sev}] {msg}")

def check_one(name, meta, caption, style):
    """compare one caption (plain text) with its meta -> prints the findings"""
    cap = caption; low = cap.lower()
    # ---- inset / zoom
    has_inset = bool(meta.get("inset"))
    if INSET_RE.search(cap) and not has_inset:
        say("FAIL", f"{name}: the caption mentions an inset / zoom ('{INSET_RE.search(cap).group(0)}') but the figure drew none (meta.inset is empty): remove the sentence or redraw with --inset")
    elif has_inset and not INSET_RE.search(cap):
        say("WARN", f"{name}: the figure carries an inset ({_inset_text(meta) or 'inset'}) and the caption does not say what it shows")
    # ---- colour words against the role colours
    roles = {**{r: style.role(r) for r in ("gt", "tp", "fp", "fn")}, **{k: v for k, v in (meta.get("roles") or {}).items() if v}}
    used = meta.get("roles_used")
    for word, role in colour_role_pairs(cap):
        if used is not None and role not in used: continue
        want = fs.colour_name(roles[role])
        if _fam(word) != _fam(want):
            say("FAIL", f"{name}: the caption says '{word}' for {fs.ROLE_WORDS[role]} but that role is drawn {want} ({roles[role]}): fix the colour word or the roles in figures.style")
    # ---- bands / error bars / whiskers explained?
    drew_band = meta.get("band") not in (None, "", "none", False) or meta.get("error_bars") not in (None, "", "none", False) or meta.get("whis")
    if drew_band and not BAND_RE.search(cap): say("WARN", f"{name}: bands / error bars / whiskers were drawn but the caption does not say what they are (e.g. 'shaded: mean ± s.d. over 3 seeds')")
    # ---- smoothing, normalisation, gamma, selection
    if meta.get("ema") and not SMOOTH_RE.search(cap): say("WARN", f"{name}: the curves are smoothed (EMA) but the caption does not say so; the raw-mean end labels need that sentence")
    if meta.get("cam") and not NORM_RE.search(cap): say("WARN", f"{name}: activation maps are normalised per image and the caption does not say so")
    if meta.get("display_gamma") not in (None, "", 1, 1.0) and not GAMMA_RE.search(cap): say("WARN", f"{name}: images are gamma-brightened for display and the caption does not say so")
    if meta.get("selection") and not SELECT_RE.search(cap): say("WARN", f"{name}: frames were selected by a rule (samples.meta.json) and the caption does not state it, nor the win / loss counts")
    # ---- delta annotation needs the metric direction
    if meta.get("annotate") and not DIR_RE.search(cap): say("WARN", f"{name}: the figure prints a Δ annotation and the caption omits the metric direction ('higher is better' / 'lower is better')")
    if "<takeaway" in cap.lower(): say("WARN", f"{name}: the caption still contains the '<takeaway…>' placeholder: replace it with the one-sentence claim")

def run_check(root, tex=None, verbose=True):
    """-> (n_fail, n_warn) and prints the findings"""
    global FAILS, WARNS
    FAILS = WARNS = 0
    root = os.path.abspath(root); style = fs.load(root)
    metas = sorted(glob.glob(os.path.join(root, "figures", "**", "*.meta.json"), recursive=True))
    if not metas:
        say("INFO", "no figures/*.meta.json: nothing to compare (generators write <out>.meta.json; regenerate the figures with the current scripts)")
        if verbose: print(f"captions: {FAILS} FAIL, {WARNS} WARN")
        return FAILS, WARNS
    tex_path = tex or os.path.join(root, "paper", "latex", "main.tex")
    if not os.path.isabs(tex_path) and not os.path.isfile(tex_path): tex_path = os.path.join(root, tex_path)
    envs = []
    if os.path.isfile(tex_path):
        try: envs = tex_captions(tex_path)
        except Exception as e: say("WARN", f"{tex_path}: could not read the figure environments ({e})")
    else: say("INFO", f"{os.path.relpath(tex_path, root)} not found: captions are not compared yet; {len(metas)} meta file(s) will be checked once the LaTeX source exists")
    n_ok = 0; n_checked = 0
    for mp in metas:
        meta = _read_json(mp); stem = os.path.basename(mp)[:-len(".meta.json")]; rel = os.path.relpath(mp, root).replace("\\", "/")
        if meta is None: say("WARN", f"{rel}: not readable JSON"); continue
        if not envs: continue
        env = next((e for e in envs if stem in e["stems"] or re.sub(r"_[a-h]$", "", stem) in e["stems"]), None)
        if env is None: say("INFO", f"{stem}: not \\includegraphics-ed in the LaTeX source (supplementary or unused?); caption not compared"); continue
        n_checked += 1; f0, w0 = FAILS, WARNS
        check_one(stem, meta, env["caption"], style)
        if (FAILS, WARNS) == (f0, w0): n_ok += 1
    if n_checked and n_ok == n_checked: say("PASS", f"{n_checked} figure caption(s) agree with what was drawn")
    if verbose: print(f"captions: {FAILS} FAIL, {WARNS} WARN")
    return FAILS, WARNS

def cmd_draft(a):
    root = os.path.abspath(a.project); meta = _read_json(a.meta) or _read_json(os.path.join(root, a.meta))
    if meta is None: print(f"[FAIL] cannot read {a.meta}"); return 1
    kind = a.kind or meta.get("kind")
    if not kind: print("[FAIL] no kind: pass --kind or let the generator record meta.kind"); return 1
    print(draft(kind, meta, fs.load(root))); return 0

def main():
    ap = argparse.ArgumentParser(description="caption drafts from figure meta, and a check of the LaTeX captions against what was drawn")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft", help="print the caption draft for a <out>.meta.json"); d.add_argument("--meta", required=True); d.add_argument("--kind", default=""); d.add_argument("--project", default=".")
    c = sub.add_parser("check", help="compare LaTeX captions with figures/*.meta.json"); c.add_argument("--project", default="."); c.add_argument("--tex", default="", help="LaTeX main file (default paper/latex/main.tex)")
    a = ap.parse_args()
    if a.cmd == "draft": sys.exit(cmd_draft(a))
    f, _w = run_check(a.project, a.tex or None); sys.exit(min(f, 255))

if __name__ == "__main__":
    main()
