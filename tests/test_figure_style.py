# -*- coding: utf-8 -*-
"""figure_style.py — the project-wide figure style registry (round-3 figure review: ours named four ways, colours that changed between figures, code names such as
chgate / recv / IRraw / out0 / value on the axes). One test per failure mode: looks_like_code on the REAL offending labels and on legitimate ones, load / key / label /
colour fallbacks, order, the CLI check (i)-(v) + WARN cases, and init (scan, draft block, colour-blind-safe palette)."""
import itertools
import sys

import pytest

from conftest import SCRIPTS, read, run, write

sys.path.insert(0, str(SCRIPTS))
import figure_style as fs

REAL_OFFENDERS = ["chgate", "recv", "xattn", "IRraw", "out0", "out1", "value", "F6R +aug +L_rel", "F6R + Lrel", "F1 Add", "F2 Concat", "params_M", "clean_AP", "AP_rgb_drop",
                  "rgb", "cnn", "E:/t2p_trial_fusion/figures/det", "figures/det/01735.png", "val", "y", "clsLoss", "layer3"]
LEGIT = ["RGB-only", "IR-only", "SMM", "Concat", "AP (%)", "DINOv2", "ResNet-50", "L$_\\mathrm{rel}$", "F1 score", "F1", "F1 (%)", "mAP@0.5", "w/o reliability loss", "GFLOPs",
         "Params (M)", "Epoch", "Validation AP (%)", "Detection loss", "ours", "Δ AP (pp)", "AP$_{50}$", "IoU", "± s.d.", "mean ± s.d.", "Day", "Night", "Clean", "Fog", "Dark",
         "SNR (dB)", "HU", "RelRoute (ours)", "RelRoute w/o reliability loss", "Train/val", "AP50/AP75", "UNet++", "YOLOv8n", "ViT-B/16", "BiFPN", "SwinUNETR", "nnU-Net",
         "mIoU", "Early fusion", "Backbone", "PAN neck", "Detect head", "RGB image", "IR image", "Detections", "Params (M) / FLOPs (G)", "Mean of A and B", "Learning curve",
         "add", "cat", "base"]
WORDS = ("epoch epochs loss score recall width height depth length strong weak fusion gate ours base early late mid high low dark fog blur noise clean night day rain snow stage "
         "layer block head neck input output params flops count mean median max min curve curves class image frame scene train test valid error rate ratio light bright right left "
         "mixed first second third fourth sixth month north bench lunch string spring script prompt prompts front point joint field shape gamma alpha sigma delta theta kernel window "
         "patch token query other total trend sweep small large medium tiny nano edge cloud sparse dense round state merge split skip scale shift drift crowd trade bias sync with "
         "without worst best solve valve rhythm object select tests costs trust three shrink scrap sprint punch earth tenth angle single angry transfer extra explain next text "
         "eighth plots bands bars boxes stems ranks hours years frames steps levels flows ground truth pairs hits misses drops gains gap size time hard soft easy sets domain "
         "unseen smooth noisy fine tuned eval demo main full half part ref fig tab top bottom lower upper inner outer").split()


@pytest.mark.parametrize("label", REAL_OFFENDERS)
def test_looks_like_code_catches_the_real_offending_labels(label):
    assert fs.looks_like_code(label), label


@pytest.mark.parametrize("label", LEGIT)
def test_looks_like_code_has_no_false_positive_on_legitimate_labels(label):
    assert not fs.looks_like_code(label), label


def test_looks_like_code_has_no_false_positive_on_plain_figure_words():
    assert [w for w in WORDS if fs.looks_like_code(w, placeholders=False)] == []


def test_looks_like_code_accepts_english_words_with_the_wth_cluster():
    """2026-11-06 (tpami_medimg): 'growth' in the QUBIQ task name 'brain growth' was flagged as code-like because 'wth' was not a legitimate run"""
    assert [w for w in ("growth", "growths", "length", "strength", "width", "depth") if fs.looks_like_code(w, placeholders=False)] == []


def test_placeholder_axis_labels_only_count_as_labels():
    assert fs.looks_like_code("Value") and fs.looks_like_code("val")
    assert not fs.looks_like_code("value", placeholders=False)        # a word of running text / PDF words
    assert not fs.looks_like_code("Value (HU)")


# ------------------------------------------------------------------ load / key / label
def _style(**kw):
    d = {"ours": ["rr"], "methods": {"rr": {"label": "RelRoute (ours)", "color": "#c94a5e", "line": "-", "marker": "o"},
                                      "smm": {"label": "SMM", "color": "#4a4a4a", "line": "--", "marker": "s"},
                                      "cat": {"label": "Concat", "color": "#3d6a94", "line": "-.", "marker": "^"},
                                      "rgb": {"label": "RGB-only", "color": "#7fa7c9", "line": "(0, (1, 1))", "marker": "v"}},
         "aliases": {"F6R +aug +L_rel": "rr", "ours": "rr", "F2 Concat": "cat"}, "datasets": {"m3fd": {"label": "M3FD", "marker": "o", "fill": "full"}}}
    d.update(kw); return fs.Style(d)


def test_load_never_raises_on_missing_file_section_or_broken_yaml(tmp_path):
    assert fs.load(tmp_path).empty()                                           # no research-state.yaml
    write(tmp_path / "research-state.yaml", "figures:\n  map: figures.csv\n")
    assert fs.load(tmp_path).empty()                                           # no style section
    write(tmp_path / "research-state.yaml", "figures: [unclosed\n  - x: {\n")
    st = fs.load(tmp_path); assert st.empty() and st.error                      # broken yaml: empty, reason kept
    assert fs.load({}).empty() and fs.load({"figures": {"style": None}}).empty()


def test_load_reads_the_registry_from_research_state(tmp_path):
    write(tmp_path / "research-state.yaml",
          'figures:\n  style:\n    ours: [rr]\n    methods:\n      rr: {label: "RelRoute (ours)", color: "#c94a5e", line: "-", marker: "o"}\n'
          '      rgb: {label: "RGB-only", color: "#7fa7c9", line: "(0, (1, 1))", marker: "v"}\n    font_pt: 6.5\n    cmap: magma\n')
    st = fs.load(tmp_path)
    assert st.label("rr") == "RelRoute (ours)" and st.is_ours("rr") and st.font_pt == 6.5 and st.cmap == "magma"
    assert st.line("rgb") == (0, (1, 1))                                       # a quoted dash tuple is parsed, a YAML list too
    assert fs.load({"figures": {"style": {"methods": {"a": {"line": [0, [1, 1]]}}}}}).line("a") == (0, (1, 1))


def test_key_resolves_exact_alias_and_case_space_underscore_insensitive():
    st = _style()
    assert st.key("rr") == "rr" and st.key("ours") == "rr" and st.key("F6R +aug +L_rel") == "rr"
    assert st.key("RR") == "rr" and st.key("f2 concat") == "cat" and st.key("rgb_only") == "rgb" and st.key("RGB-only") == "rgb" and st.key("relroute (ours)") == "rr"
    assert st.key("nothing") is None and st.key(None) is None


def test_label_uses_registry_humanises_unknown_and_strict_refuses():
    st = _style()
    assert st.label("F6R +aug +L_rel") == "RelRoute (ours)" and st.label("smm") == "SMM"
    assert st.label("val_loss") == "Val loss" and st.label("params_M") == "Params (M)"
    assert fs.humanise("ir_branch") == "IR branch" and fs.humanise("") == ""
    with pytest.raises(fs.StyleError, match="chgate"): st.label("chgate", strict=True)
    with pytest.raises(fs.StyleError): st.label("some_unregistered_name", strict=True)
    assert st.label("smm", strict=True) == "SMM"
    bad = fs.Style({"methods": {"x": {"label": "chgate"}}})
    with pytest.raises(fs.StyleError): bad.label("x", strict=True)             # a registered but code-like label is refused too


def test_color_line_marker_registry_and_deterministic_fallback_avoids_ours_and_roles():
    st = _style()
    assert st.color("rr") == "#c94a5e" and st.line("smm") == "--" and st.marker("cat") == "^" and st.color("F2 Concat") == "#3d6a94"
    assert st.ours_color == "#c94a5e" and st.linewidth("rr") > st.linewidth("smm")
    forbidden = {st.ours_color} | {st.role(r) for r in fs.DEFAULT_ROLES} | {"#4a4a4a", "#3d6a94", "#7fa7c9"}
    seen = {st.color(f"unknown_{i}", i) for i in range(30)}
    assert seen and not (seen & forbidden)
    assert st.color("mystery") == st.color("mystery") and st.color("mystery") == st.color("MYSTERY")        # deterministic, spelling-insensitive hash
    assert st.line("mystery") != "-" and st.marker("mystery") != "o"                                        # '-' and 'o' stay reserved for ours
    empty = fs.Style(None)
    assert empty.color("anything") not in {fs.ACCENT, *[empty.role(r) for r in fs.DEFAULT_ROLES]} and empty.ours_color == fs.ACCENT


def test_fallback_palette_is_colour_blind_safe_and_away_from_the_roles():
    empty = fs.Style(None)
    pool = empty._fallback_pool()
    for c in pool: assert min(fs.delta_e(c, a) for a in [fs.ACCENT] + list(fs.DEFAULT_ROLES.values())) >= 14, c
    sep, who = fs.min_separation([fs.ACCENT] + pool[:5])                       # the first five baselines under normal / deut / prot / trit vision
    assert sep >= 12, (sep, who)
    # the simulation behaves: grey is untouched, red vs green collapses under deuteranopia
    assert fs.simulate("#808080", "deut") == "#808080"
    assert fs.delta_e(fs.simulate("#d62728", "deut"), fs.simulate("#2ca02c", "deut")) < fs.delta_e("#d62728", "#2ca02c") / 2


def test_order_puts_ours_first_then_registry_order_then_the_rest():
    st = _style()
    assert st.order(["zzz", "rgb", "smm", "F6R +aug +L_rel", "cat", "aaa"]) == ["F6R +aug +L_rel", "smm", "cat", "rgb", "zzz", "aaa"]


def test_roles_stage_dataset():
    st = _style(roles={"fp": "#aa00aa"}, stages={"fuse": "RelRoute fusion"})
    assert st.role("fp") == "#aa00aa" and st.role("gt") == fs.DEFAULT_ROLES["gt"] and st.role("tp") == fs.DEFAULT_ROLES["tp"]
    with pytest.raises(fs.StyleError): st.role("nonsense")
    assert st.stage("fuse") == "RelRoute fusion" and st.stage("neck_block") == "Neck block"
    d = st.dataset("m3fd"); assert d == {"label": "M3FD", "marker": "o", "fill": "full"} and "color" not in d
    assert st.dataset("llvip")["label"] == "Llvip" and st.dataset("llvip")["marker"] in fs.MARKS
    assert fs.Style(None).cmap == "viridis" and fs.Style(None).font_pt == 7.0


def test_colour_and_line_words():
    assert fs.colour_name("#2e9b57") == "green" and fs.colour_name("#e08a00") == "orange" and fs.colour_name("#ffd23f") == "yellow" and fs.colour_name("#d9d9d9") == "light grey"
    assert fs.colour_name("#c94a5e") == "red" and fs.colour_name("#3d6a94") == "blue"
    assert [fs.line_word(x) for x in ("-", "--", "-.", ":", (0, (1, 1)))] == ["solid", "dashed", "dash-dotted", "dotted", "dotted"]


# ------------------------------------------------------------------ CLI check
def _project(tmp_path, style_yaml=None, sources=(), pdf_words=None):
    block = "figures:\n  map: figures.csv\n" + (style_yaml or "")
    write(tmp_path / "research-state.yaml", "branch: research\n" + block)
    for name, text in sources: write(tmp_path / "figures" / name, text)
    if pdf_words:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(2, 1)); fig.text(0.1, 0.5, pdf_words); (tmp_path / "figures").mkdir(exist_ok=True); fig.savefig(str(tmp_path / "figures" / "fig_t.pdf")); plt.close(fig)
    return tmp_path

GOOD = ('  style:\n    ours: [rr]\n    methods:\n      rr: {label: "RelRoute (ours)", color: "#c94a5e", line: "-", marker: "o"}\n'
        '      smm: {label: "SMM", color: "#4a4a4a", line: "--", marker: "s"}\n    datasets: {m3fd: {label: "M3FD", marker: "o", fill: "full"}}\n    cmap: viridis\n')
SRC_OK = "series,epoch,value_mean,label,color,line,marker\nrr,1,3.0,RelRoute (ours),#c94a5e,-,o\nsmm,1,4.0,SMM,#4a4a4a,--,s\n"

def _check(p, *extra): return run("figure_style.py", "check", "--project", p, *extra, cwd=p)


def test_check_passes_on_a_consistent_project(tmp_path):
    p = _project(tmp_path, GOOD, [("fig_a.source.csv", SRC_OK), ("fig_b.source.csv", SRC_OK)], pdf_words="RelRoute SMM Epoch")
    r = _check(p); assert r.returncode == 0 and r.fails == 0 and not r.crashed, r.out
    assert "[PASS]" in r.out and "0 FAIL" in r.out


def test_check_i_code_like_label_in_a_source_csv_fails(tmp_path):
    src = SRC_OK + "chgate,1,3.0,chgate,#112233,-,o\n"
    r = _check(_project(tmp_path, GOOD, [("fig_a.source.csv", src)])); assert r.returncode >= 1 and "chgate" in r.out and "code-like" in r.out, r.out


def test_check_i_code_like_word_in_the_pdf_text_layer_fails(tmp_path):
    p = _project(tmp_path, GOOD, [("fig_a.source.csv", SRC_OK)], pdf_words="recv gate")
    r = _check(p); assert r.fails >= 1 and "recv" in r.out and "text" in r.out, r.out


def test_check_ii_one_method_two_colours_or_two_labels_fails(tmp_path):
    other = SRC_OK.replace("#c94a5e", "#1b9e77")
    r = _check(_project(tmp_path, GOOD, [("fig_a.source.csv", SRC_OK), ("fig_b.source.csv", other)])); assert r.fails >= 1 and "different colors" in r.out.replace("colours", "colors"), r.out
    renamed = SRC_OK.replace("RelRoute (ours)", "Ours")
    r = _check(_project(tmp_path, GOOD, [("fig_a.source.csv", SRC_OK), ("fig_b.source.csv", renamed)])); assert r.fails >= 1 and "different labels" in r.out, r.out


def test_check_iii_baseline_with_the_ours_colour_and_role_colour_equal_to_ours_fail(tmp_path):
    clash = GOOD.replace('color: "#4a4a4a"', 'color: "#c94a5e"')
    r = _check(_project(tmp_path, clash)); assert r.fails >= 1 and "ours colour" in r.out, r.out
    r = _check(_project(tmp_path, GOOD + '    roles: {fp: "#c94a5e"}\n')); assert r.fails >= 1 and "roles.fp" in r.out, r.out


def test_check_iv_dataset_with_a_hue_fails(tmp_path):
    bad = GOOD.replace('fill: "full"}', 'fill: "full", color: "#3d6a94"}')
    r = _check(_project(tmp_path, bad)); assert r.fails >= 1 and "datasets.m3fd" in r.out and "never by colour" in r.out, r.out


def test_check_v_jet_fails_unless_allowed(tmp_path):
    r = _check(_project(tmp_path, GOOD.replace("viridis", "jet"))); assert r.fails >= 1 and "jet" in r.out, r.out
    r = _check(_project(tmp_path, GOOD.replace("viridis", "jet") + "    roles: {allow_jet: true}\n")); assert r.fails == 0, r.out


def test_check_warns_on_source_csv_without_style_columns_and_without_a_registry(tmp_path):
    old = "series,epoch,value_mean\nrr,1,3.0\n"
    r = _check(_project(tmp_path, GOOD, [("fig_old.source.csv", old)])); assert r.fails == 0 and "[WARN] figures/fig_old.source.csv: no style columns" in r.out, r.out
    r = _check(_project(tmp_path, None, [("fig_old.source.csv", old)])); assert r.fails == 0 and "no figure style registry" in r.out, r.out
    # an unregistered code name in a file that has no style columns is only a WARN (what was drawn is unknown)
    r = _check(_project(tmp_path, GOOD, [("fig_old.source.csv", "method,n\nchgate,3\n")])); assert r.fails == 0 and "chgate" in r.out and "[WARN]" in r.out, r.out


def test_check_warns_about_unconfirmed_todo_labels(tmp_path):
    r = _check(_project(tmp_path, GOOD.replace('marker: "o"}', 'marker: "o"}   # TODO: author name', 1)))
    assert r.fails == 0 and "TODO: author name" in r.out and "[WARN]" in r.out, r.out


def test_check_allow_lists_a_word(tmp_path):
    p = _project(tmp_path, GOOD, [("fig_a.source.csv", SRC_OK)], pdf_words="recv")
    assert _check(p).fails >= 1 and _check(p, "--allow", "recv").fails == 0


# ------------------------------------------------------------------ CLI init
def _trial(tmp_path):
    write(tmp_path / "research-state.yaml", "branch: research\nfigures:\n  map: figures.csv\n  inspected: []\n\nreview:\n  log: x\n")
    write(tmp_path / "results" / "main.csv", "run_id,method,dataset,seed,clean_AP\nr0,F1 Add,m3fd,0,35.8\nr1,F2 Concat,m3fd,0,36.6\nr2,ours,m3fd,0,38.0\nr3,RGB-only,llvip,0,31.1\n"
                                              "r4,IR-only,llvip,0,29.0\nr5,SMM,m3fd,0,34.0\nr6,chgate,m3fd,0,30.0\n")
    write(tmp_path / "figures" / "fig_cam.source.csv", "sample,method,n_boxes\n01735,GT,3\n01735,recv,2\n01735,ours,3\n")


def test_init_writes_a_draft_block_that_loads_and_is_colour_blind_safe(tmp_path):
    _trial(tmp_path)
    r = run("figure_style.py", "init", "--project", tmp_path, cwd=tmp_path); assert r.returncode == 0 and not r.crashed, r.out
    txt = read(tmp_path / "research-state.yaml")
    assert "  style:" in txt and txt.index("figures:") < txt.index("style:") < txt.index("review:") and "inspected: []" in txt       # inserted under figures:, rest untouched
    assert txt.count("TODO: author name") >= 7
    st = fs.load(tmp_path)
    assert st.ours == ["ours"] and st.color("ours") == fs.ACCENT
    assert st.key("F1 Add") and st.label("F1 Add") == "F1 Add"                                                           # humanised draft (the author confirms it)
    assert "gt" not in st.methods and st.key("GT") is None                                                              # the ground-truth column is no method
    assert {"m3fd", "llvip"} <= set(st.datasets) and all("color" not in v for v in st.datasets.values())
    cols = [st.color(k) for k in st.methods]; assert len(set(cols)) == len(cols)
    base = [st.color(k) for k in st.methods if k not in st.ours]
    sep, who = fs.min_separation([st.ours_color] + base); assert sep >= 8, (sep, who)
    fails = [m for s, m in st.validate() if s == "FAIL"]
    assert len(fails) == 2 and all("code name" in m for m in fails), fails                                                # only the humanised family codes "F1 Add" / "F2 Concat" still need a real name
    assert "[WARN] methods.f1_add.label" in r.out and "[FAIL]" not in r.out                                               # init warns, it does not fail on a draft
    c = _check(tmp_path); assert c.fails == 2 and "TODO: author name" in c.out, c.out                                    # check keeps failing until the author renames them


def test_init_on_an_existing_registry_lists_the_names_not_yet_registered(tmp_path):
    _trial(tmp_path)
    write(tmp_path / "research-state.yaml", "figures:\n  style:\n    ours: [ours]\n    methods:\n      ours: {label: \"RelRoute (ours)\", color: \"#c94a5e\"}\n      smm: {label: \"SMM\"}\n"
                                              "    aliases: {\"F2 Concat\": smm}\n")
    before = read(tmp_path / "research-state.yaml")
    r = run("figure_style.py", "init", "--project", tmp_path, cwd=tmp_path)
    assert r.returncode == 0 and "'chgate'" in r.out and "'F1 Add'" in r.out and "'F2 Concat'" not in r.out and "'SMM'" not in r.out and "'smm'" not in r.out, r.out
    assert read(tmp_path / "research-state.yaml") == before                                                              # never overwritten


def test_init_appends_figures_when_the_key_is_missing_and_show_prints_the_table(tmp_path):
    write(tmp_path / "research-state.yaml", "branch: research\n"); write(tmp_path / "results" / "main.csv", "method,dataset\nA model,x\nours,x\n")
    r = run("figure_style.py", "init", "--project", tmp_path, cwd=tmp_path); assert r.returncode == 0, r.out
    assert fs.load(tmp_path).ours == ["ours"]
    r = run("figure_style.py", "show", "--project", tmp_path, cwd=tmp_path); assert r.returncode == 0 and "A model" in r.out and "(ours)" in r.out, r.out
