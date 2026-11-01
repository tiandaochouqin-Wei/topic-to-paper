# -*- coding: utf-8 -*-
"""caption_draft.py — caption DRAFTS generated from what a generator recorded in <out>.meta.json, and `check` of the LaTeX caption against that meta.
Round-3 figure review: hand-written captions contradicted the figures (a "zoom" caption after the inset was dropped; "green = GT, red = predictions" after the
box-status colours changed). One test per failure mode."""
import json
import sys

import pytest

from conftest import SCRIPTS, read, run, write

sys.path.insert(0, str(SCRIPTS))
import caption_draft as cd
import figure_style as fs


def _style():
    return fs.Style({"ours": ["rr"], "methods": {"rr": {"label": "RelRoute (ours)", "color": "#c94a5e", "line": "-", "marker": "o"},
                                                  "smm": {"label": "SMM", "color": "#4a4a4a", "line": "--", "marker": "s"},
                                                  "rgb": {"label": "RGB-only", "color": "#7fa7c9", "line": "(0, (1, 1))", "marker": "v"}},
                     "datasets": {"m3fd": {"label": "M3FD", "marker": "o", "fill": "full"}}})

CURVES = {"y_label": "Validation AP", "y_unit": "%", "metric": "val_AP", "x_label": "Epoch", "x_name": "epoch", "series": ["smm", "rr", "rgb"], "band": "sd", "n_seeds": 3,
          "ema": {"alpha": 0.12, "init": "first", "raw_line": True}, "end_x": 99, "inset": {"x0": 70, "x1": 99, "x_name": "epoch"},
          "annotate": {"x": 99, "ours": "rr", "baseline": "smm", "delta": 0.8, "unit": "pp", "metric": "val_AP", "label": "AP"}}


# ------------------------------------------------------------------ drafts
@pytest.mark.parametrize("kind", cd.KINDS + ("bland-altman",))
def test_every_kind_drafts_a_caption_that_starts_with_the_takeaway_placeholder(kind):
    cap = cd.draft(kind, {}, _style())
    assert cap.startswith("<takeaway") and len(cap) > 80, cap
    assert cd.draft(kind, {}, None).startswith("<takeaway")                    # works without a registry too


def test_unknown_kind_is_refused():
    with pytest.raises(ValueError, match="unknown figure kind"): cd.draft("pie", {}, _style())


def test_curves_caption_states_units_direction_bands_smoothing_inset_and_delta():
    cap = cd.draft("curves", CURVES, _style())
    assert "Validation AP (%) versus Epoch" in cap and "RelRoute (ours), SMM and RGB-only".replace("RelRoute (ours), SMM", "RelRoute (ours), SMM") in cap
    assert "higher is better" in cap
    assert "Shaded band: mean ± s.d. over 3 seeds" in cap
    assert "EMA α = 0.12, initialised at the first value" in cap and "End labels are raw means at epoch 99" in cap
    assert "Inset: epochs 70–99" in cap
    assert "Δ = RelRoute (ours) − SMM at epoch 99 (Δ AP +0.80 pp, higher is better)" in cap
    assert "thick solid red" in cap and "SMM (dashed dark grey)" in cap and "RGB-only (dotted blue)" in cap          # the colour / line semantics come from the style


def test_curves_caption_says_nothing_about_what_was_not_drawn():
    meta = {k: v for k, v in CURVES.items() if k not in ("inset", "ema", "band", "annotate", "end_x")}
    cap = cd.draft("curves", meta, _style()).lower()
    for word in ("inset", "zoom", "ema", "shaded", "moving average", "end labels", "Δ ".lower()): assert word not in cap, (word, cap)


def test_direction_comes_from_metric_direction_and_is_overridable():
    cap = cd.draft("curves", {"y_label": "Training loss", "metric": "loss_total", "series": ["rr"]}, _style()); assert "lower is better" in cap
    cap = cd.draft("curves", {"y_label": "Skill", "metric": "mystery_col", "results": {"metric_direction": {"mystery_col": "lower"}}, "series": ["rr"]}, _style()); assert "lower is better" in cap
    cap = cd.draft("curves", {"y_label": "Thing", "metric": "loss", "direction": "higher", "series": ["rr"]}, _style()); assert "higher is better" in cap
    assert "better" not in cd.draft("curves", {"y_label": "Thing", "series": ["rr"]}, _style())                       # unknown direction: not invented


def test_no_ours_is_stated():
    assert "equal weight" in cd.draft("curves", {"y_label": "AP", "series": ["smm", "rgb"]}, fs.Style(None))


def test_bars_ablation_and_seed_captions():
    bars = cd.draft("bars", {"y_label": "AP", "y_unit": "%", "metric": "AP", "series": ["rr", "smm"], "error_bars": "sd", "n_seeds": 3, "dots": "seeds", "x_label": "corruption"}, _style())
    assert "Error bars: ± s.d. over 3 seeds, dots = individual seeds" in bars and "one bar per method (RelRoute (ours) and SMM)" in bars
    abl = cd.draft("ablation", {"metric": "AP", "reference": "rr", "n_seeds": 3, "resolvable_n": 2, "n_ablations": 5, "band_sigma": "±2σ"}, _style())
    assert "relative to RelRoute (ours)" in abl and "±2σ" in abl and "not resolvable" in abl and "2 of 5 ablations are resolvable" in abl
    assert "mean ± s.d. over 3 seeds, dots = individual seeds" in cd.draft("seeds", {"series": ["rr"], "y_label": "AP", "n_seeds": 3}, _style())


def test_grid_caption_states_roles_from_the_style_counts_gamma_normalisation_and_selection():
    sel = {"rule": "largest difference between ours and the best baseline", "n_images": 100, "wins": 60, "losses": 25, "ties": 15, "n_counter": 4, "counter_examples": ["a", "b"]}
    meta = {"rows": 4, "cols": ["smm", "rr"], "box_status": True, "roles_used": ["gt", "tp", "fp", "fn"], "iou": 0.5, "min_score": 0.25, "cell_counts": "det", "display_gamma": 0.5, "selection": sel,
            "cam": {"cmap": "viridis", "norm": "per_image_minmax"}, "inset": [0.1, 0.1, 0.3, 0.3], "min_box_pt": 0.8}
    cap = cd.draft("grid", meta, _style())
    assert "yellow solid = ground truth" in cap and "green solid = true positive" in cap and "orange dashed = false positive" in cap and "light grey dotted = missed ground truth" in cap
    assert "IoU ≥ 0.5" in cap and "confidence ≥ 0.25" in cap and "TP · FP · FN" in cap
    assert "gamma 0.5" in cap and "no model input was changed" in cap
    assert "min–max normalised per image, colour map viridis" in cap
    assert "Frames were chosen automatically: largest difference" in cap and "better than the best baseline on 60, worse on 25 and tied on 15" in cap and "4 counter-example(s)" in cap
    assert "Inset" in cap and "0.8 pt" in cap
    cam = cd.draft("grid", {"cols": ["rr"], "cell_counts": "cam"}, _style()); assert "share of the activation mass inside the ground-truth boxes" in cam


def test_grid_roles_come_from_the_roles_actually_drawn_when_the_generator_records_them():
    cap = cd.draft("grid", {"cols": ["rr"], "roles_used": ["tp", "fp"], "roles": {"tp": "#0000ff", "fp": "#ff0000"}}, _style())
    assert "blue solid = true positive" in cap and "red dashed = false positive" in cap and "green" not in cap


def test_tradeoff_architecture_and_remaining_kinds():
    t = cd.draft("tradeoff", {"x_label": "GFLOPs", "y_label": "AP", "y_metric": "AP", "x_metric": "GFLOPs", "datasets": ["m3fd"], "dataset_encoding": "marker", "front": True, "leader_lines": True, "series": ["rr", "smm"]}, _style())
    assert "AP versus GFLOPs" in t and "Datasets are encoded by marker shape (M3FD), colour identifies the method" in t and "Pareto" in t and "leader lines" in t and "AP: higher is better" in t
    a = cd.draft("architecture", {"model": "RelRoute", "stages": ["Backbone", "Fusion"], "ours_modules": ["Fusion"], "n_params": 2606098, "shapes": True, "input_shape": "1×3×640×640"}, _style())
    assert "filled in red" in a and "2,606,098 parameters" in a and "1×3×640×640" in a
    assert "bootstrap (200 resamples)" in cd.draft("roc", {"ci": "bootstrap:200", "series": ["rr"]}, _style())
    assert "prevalence" in cd.draft("pr", {}, _style())
    assert "limits of agreement (bias ± 1.96" in cd.draft("bland_altman", {"unit": "HU"}, _style()) and "in HU" in cd.draft("bland_altman", {"unit": "HU"}, _style())
    assert "percentiles" in cd.draft("box", {"whis": [5, 95], "group": "dataset"}, _style())
    assert "n = 3 per group" in cd.draft("seeds", {"n": {"rr": 3, "smm": 3}}, _style())
    assert "Synthetic demonstration data" in cd.draft("bars", {"synthetic": True}, _style())


def test_write_files_writes_meta_json_and_caption_md(tmp_path):
    mp, cp = cd.write_files(str(tmp_path / "figures" / "fig_c.png"), "curves", CURVES, _style())
    assert mp.endswith("fig_c.meta.json") and cp.endswith("fig_c.caption.md")
    meta = json.loads(read(mp)); assert meta["kind"] == "curves" and meta["inset"]["x0"] == 70
    assert read(cp).startswith("<takeaway") and "EMA α = 0.12" in read(cp)


def test_draft_cli_prints_the_caption(tmp_path):
    cd.write_files(str(tmp_path / "figures" / "fig_c"), "curves", CURVES, _style())
    r = run("caption_draft.py", "draft", "--meta", "figures/fig_c.meta.json", "--project", tmp_path, cwd=tmp_path)
    assert r.returncode == 0 and r.out.startswith("<takeaway") and "Inset: epochs 70–99" in r.out, r.out


# ------------------------------------------------------------------ check
def _project(tmp_path, meta, caption, yaml="", name="fig_a", extra_tex=""):
    write(tmp_path / "research-state.yaml", "branch: research\n" + yaml)
    write(tmp_path / "figures" / f"{name}.meta.json", json.dumps(meta))
    write(tmp_path / "paper" / "latex" / "main.tex",
          "\\documentclass{article}\\usepackage{graphicx}\\begin{document}\n\\begin{figure}\\includegraphics[width=\\linewidth]{../../figures/" + name + ".pdf}\n"
          "\\caption{" + caption + "}\\label{fig:a}\\end{figure}\n" + extra_tex + "\\end{document}\n")
    return tmp_path

def _chk(p, *extra): return run("caption_draft.py", "check", "--project", p, *extra, cwd=p)

OKCAP = "RelRoute (ours) lowers the loss. Shaded: mean ± s.d. over 3 seeds; lines are EMA smoothed; inset: epochs 70--99; $\\Delta$ AP in pp (higher is better)."


def test_check_passes_when_the_caption_agrees_with_the_meta(tmp_path):
    r = _chk(_project(tmp_path, CURVES, OKCAP)); assert r.returncode == 0 and r.fails == 0 and "[PASS] 1 figure caption" in r.out and "[WARN]" not in r.out, r.out


def test_check_inset_claimed_but_absent_is_a_fail(tmp_path):
    meta = {k: v for k, v in CURVES.items() if k != "inset"}
    r = _chk(_project(tmp_path, meta, "Zoomed view of the last epochs. Shaded: s.d.; EMA smoothed; higher is better.")); assert r.fails == 1 and "inset / zoom" in r.out and "drew none" in r.out, r.out
    assert _chk(tmp_path).returncode == 1                                                                              # exit code = number of FAIL lines


def test_check_inset_drawn_but_not_mentioned_is_a_warn(tmp_path):
    r = _chk(_project(tmp_path, CURVES, "Shaded: mean ± s.d.; EMA smoothed; higher is better.")); assert r.fails == 0 and "carries an inset" in r.out, r.out


def test_check_colour_word_contradicting_a_role_is_a_fail_and_a_consistent_one_passes(tmp_path):
    meta = {"kind": "grid", "box_status": True, "roles_used": ["gt", "tp", "fp", "fn"], "cell_counts": "det"}
    r = _chk(_project(tmp_path, meta, "Green = ground truth, red = predictions, TP, FP, FN under each image.")); assert r.fails == 1 and "'green' for ground truth" in r.out and "yellow" in r.out, r.out
    ok = "Boxes: yellow = ground truth, green = true positive, orange dashed = false positive, grey dotted = missed ground truth."
    r = _chk(_project(tmp_path, meta, ok)); assert r.fails == 0 and "contradict" not in r.out and "[WARN]" not in r.out, r.out
    r = _chk(_project(tmp_path, meta, "Red boxes mark false positives; green boxes mark true positives.")); assert r.fails == 1 and "'red' for false positive" in r.out, r.out      # fp is orange in this style


def test_check_roles_recorded_by_the_generator_beat_the_registry(tmp_path):
    meta = {"kind": "grid", "roles_used": ["tp", "fp"], "roles": {"tp": "#0000ff", "fp": "#ff0000"}}
    r = _chk(_project(tmp_path, meta, "Blue boxes are true positives, red boxes are false positives.")); assert r.fails == 0, r.out
    r = _chk(_project(tmp_path, meta, "Green boxes are true positives.")); assert r.fails == 1, r.out


def test_check_roles_the_figure_did_not_draw_are_ignored(tmp_path):
    meta = {"kind": "grid", "roles_used": ["tp"], "cell_counts": "det"}
    r = _chk(_project(tmp_path, meta, "Green = true positive; blue = ground truth.")); assert r.fails == 0, r.out


def test_check_bands_not_explained_is_a_warn(tmp_path):
    r = _chk(_project(tmp_path, {"kind": "curves", "band": "sd", "n_seeds": 3}, "RelRoute wins on every dataset.")); assert r.fails == 0 and "bands / error bars / whiskers" in r.out, r.out
    r = _chk(_project(tmp_path, {"kind": "curves", "band": "sd", "n_seeds": 3}, "RelRoute wins; shaded band is the s.d. over 3 seeds.")); assert "bands / error bars" not in r.out, r.out
    r = _chk(_project(tmp_path, {"kind": "curves", "band": "none"}, "RelRoute wins.")); assert "bands / error bars" not in r.out, r.out


def test_check_delta_annotation_without_direction_is_a_warn(tmp_path):
    meta = {"kind": "curves", "annotate": {"x": 99, "delta": 0.8}}
    r = _chk(_project(tmp_path, meta, "RelRoute gains $\\Delta$ = 0.8 pp at epoch 99.")); assert r.fails == 0 and "Δ annotation" in r.out and "direction" in r.out, r.out
    r = _chk(_project(tmp_path, meta, "RelRoute gains $\\Delta$ = 0.8 pp at epoch 99 (higher is better).")); assert "Δ annotation" not in r.out, r.out


def test_check_smoothing_gamma_normalisation_and_selection_are_warned_when_unmentioned(tmp_path):
    meta = {"kind": "grid", "ema": {"alpha": 0.1}, "cam": {"norm": "per_image_minmax"}, "display_gamma": 0.5, "selection": {"rule": "x"}}
    r = _chk(_project(tmp_path, meta, "Qualitative results.")); assert r.fails == 0
    for what in ("smoothed (EMA)", "normalised per image", "gamma-brightened", "selected by a rule"): assert what in r.out, (what, r.out)
    r = _chk(_project(tmp_path, meta, "Qualitative results; EMA smoothed; maps are min-max normalised per image; brightened for display (gamma 0.5); frames chosen by a stated criterion."))
    assert "[WARN]" not in r.out, r.out


def test_check_takeaway_placeholder_left_in_the_caption_is_a_warn(tmp_path):
    r = _chk(_project(tmp_path, {"kind": "curves"}, "<takeaway: fill me in> Loss versus epoch.")); assert r.fails == 0 and "takeaway" in r.out and "[WARN]" in r.out, r.out


def test_check_without_meta_without_tex_or_without_the_figure_in_the_tex_is_info_only(tmp_path):
    write(tmp_path / "research-state.yaml", "branch: research\n")
    r = _chk(tmp_path); assert r.returncode == 0 and "no figures/*.meta.json" in r.out, r.out
    write(tmp_path / "figures" / "fig_a.meta.json", json.dumps({"kind": "curves"}))
    r = _chk(tmp_path); assert r.returncode == 0 and "main.tex not found" in r.out, r.out
    r = _chk(_project(tmp_path, {"kind": "curves"}, "ok", name="fig_other")); assert r.returncode == 0, r.out
    write(tmp_path / "figures" / "fig_a.meta.json", json.dumps({"kind": "curves", "inset": [0, 0, 1, 1]}))
    r = _chk(tmp_path); assert r.returncode == 0 and "not \\includegraphics-ed" in r.out, r.out


def test_check_accepts_a_custom_tex_path(tmp_path):
    p = _project(tmp_path, {"kind": "curves"}, "Zoomed view.")
    (p / "paper" / "latex" / "main.tex").rename(p / "paper" / "alt.tex")
    assert _chk(p).returncode == 0                                                                                    # default path has no tex: nothing compared
    r = _chk(p, "--tex", "paper/alt.tex"); assert r.fails == 1, r.out
