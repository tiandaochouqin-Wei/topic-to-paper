# -*- coding: utf-8 -*-
"""make_figure.py / make_motivation.py read the project-wide style registry (research-state.yaml figures.style, scripts/figure_style.py): names, colours, lines,
markers, ours, datasets, font; every source.csv carries label / color / line / marker; every figure writes <out>.meta.json and <out>.caption.md; the small
round-3 fixes (opaque legends placed by occupancy, leader lines, marker-aware limits, Δ naming metric and direction, end labels in the margin, no raw y label).
Synthetic data in tmp_path."""
import csv
import io
import json
import os
import sys

import numpy as np
import pytest

from conftest import SCRIPTS, read, run, write

sys.path.insert(0, str(SCRIPTS))
import make_figure as mf  # noqa: E402
import figure_style as fstyle  # noqa: E402

REGISTRY = """figures:
  style:
    ours: [relroute_l]
    methods:
      relroute_l: {label: "RelRoute (ours)", color: "#c94a5e", line: "-", marker: "o"}
      smm: {label: "SMM", color: "#4a4a4a", line: "--", marker: "s"}
      cat: {label: "Concat", color: "#3d6a94", line: "-.", marker: "^"}
      rgb: {label: "RGB-only", color: "#7fa7c9", line: "(0, (1, 1))", marker: "v"}
    aliases: {"F6R +aug": relroute_l}
    datasets: {m3fd: {label: "M3FD", marker: "o", fill: "full"}, llvip: {label: "LLVIP", marker: "s", fill: "none"}}
    roles: {gt: "#ffd23f", tp: "#2e9b57", fp: "#e08a00", fn: "#d9d9d9", ours_frame: "#1f1f1f", baseline_line: "#8a8a8a"}
    cmap: viridis
    font_pt: 7
"""
METHODS = [("relroute_l", 0.9), ("smm", 1.0), ("cat", 1.15), ("rgb", 1.3)]


def _table(path, header, rows):
    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    with io.open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def _dicts(path):
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig")))


def _project(tmp_path, registry=True):
    if registry: write(tmp_path / "research-state.yaml", REGISTRY)
    rng = np.random.default_rng(3); rows = []
    for ds in ("m3fd", "llvip"):
        for m, b in METHODS:
            for sd in range(2):
                for e in range(40):
                    rows.append([m, ds, sd, e, round(b * (1 + 3 * np.exp(-e / 10)) + rng.normal(0, 0.03), 4)])
    _table(tmp_path / "results" / "c.csv", ["method", "dataset", "seed", "epoch", "loss"], rows)


def _curves(tmp_path, *extra, out="figures/c.png"):
    return run("make_figure.py", "curves", "--project", ".", "--csv", "results/c.csv", "--out", out, "--x", "epoch", "--y", "loss", "--series", "method", "--ylabel", "Loss", *extra, cwd=tmp_path)


def _in_process(monkeypatch, tmp_path, script, argv):
    import importlib
    mod = importlib.import_module(script)
    got = []
    monkeypatch.setattr(mod if script == "make_figure" else mf, "finish", lambda fig, a, src, hdr, root, caption: got.append((fig, src, hdr, caption)))
    if script == "make_motivation": monkeypatch.setattr(mod, "finish", lambda fig, a, src, hdr, root, caption: got.append((fig, src, hdr, caption)))
    monkeypatch.setattr(sys, "argv", [script + ".py", *argv]); monkeypatch.chdir(tmp_path)
    mod.main()
    return got[0]


# ------------------------------------------------------------------ the registry drives names, colours, lines, order
def test_registry_drives_labels_colours_lines_and_order(tmp_path, monkeypatch):
    _project(tmp_path)
    fig, src, hdr, cap = _in_process(monkeypatch, tmp_path, "make_figure", ["curves", "--project", ".", "--csv", "results/c.csv", "--x", "epoch", "--y", "loss", "--ylabel", "Loss", "--series", "method",
                                                                           "--panel", "dataset", "--out", "figures/c.png"])
    leg = fig.legends[0] if fig.legends else next(ax.get_legend() for ax in fig.axes if ax.get_legend() is not None)
    labels = [t.get_text() for t in leg.get_texts()]
    assert labels[0] == "RelRoute (ours)" and set(labels) == {"RelRoute (ours)", "SMM", "Concat", "RGB-only"}   # registry labels, ours first, no code names
    cols = {t.get_text(): h.get_color() for t, h in zip(leg.get_texts(), leg.legend_handles)}
    assert cols["RelRoute (ours)"] == "#c94a5e" and cols["SMM"] == "#4a4a4a" and cols["Concat"] == "#3d6a94"
    assert hs_ls(leg)["SMM"] == "--" and hs_ls(leg)["Concat"] == "-.", hs_ls(leg)
    # no --ours given: the registry's ours is heavy (line width 1.8) and nothing warns about a missing ours
    assert max(h.get_linewidth() for h in leg.legend_handles) >= 1.7
    assert hdr[-4:] == ["label", "color", "line", "marker"]


def hs_ls(leg):
    return {t.get_text(): h.get_linestyle() for t, h in zip(leg.get_texts(), leg.legend_handles)}


def test_font_pt_from_the_registry_is_the_only_text_size(tmp_path):
    _project(tmp_path)
    r = _curves(tmp_path, "--panel", "dataset", "--width-mm", "120")
    assert r.returncode == 0, r.out
    import fitz
    pg = fitz.open(str(tmp_path / "figures" / "c.pdf"))[0]
    sizes = {round(sp["size"], 1) for b in pg.get_text("dict")["blocks"] for l in b.get("lines", []) for sp in l["spans"] if sp["text"].strip()}
    assert sizes == {7.0}, sizes                                                    # figures.style.font_pt: 7 for every role


def test_unregistered_series_get_a_warning_and_a_fallback_colour_never_ours_or_a_role(tmp_path):
    _project(tmp_path)
    rows = [[m, 0, e, 1.0 + 0.1 * i + 0.01 * e] for i, m in enumerate(["relroute_l", "smm", "newcomer", "other_one"]) for e in range(12)]
    _table(tmp_path / "results" / "u.csv", ["method", "seed", "epoch", "loss"], rows)
    r = run("make_figure.py", "curves", "--project", ".", "--csv", "results/u.csv", "--out", "figures/u.png", "--x", "epoch", "--y", "loss", "--ylabel", "Loss", "--series", "method", cwd=tmp_path)
    assert r.returncode == 0 and "[WARN] style: series 'newcomer' is not in figures.style" in r.out, r.out
    src = {s["series"]: s for s in _dicts(tmp_path / "figures" / "u.source.csv")}
    assert src["newcomer"]["label"] == "Newcomer" and src["other_one"]["label"] == "Other one"          # humanised drafts
    st = fstyle.load(str(tmp_path))
    avoid = [st.ours_color] + [st.role(k) for k in ("gt", "tp", "fp", "fn")]
    for n in ("newcomer", "other_one"):
        assert all(fstyle.delta_e(src[n]["color"], c) >= 10 for c in avoid), (n, src[n]["color"])
    assert src["newcomer"]["color"] != src["other_one"]["color"]


def test_no_ours_anywhere_warns_that_every_series_has_equal_weight(tmp_path):
    _project(tmp_path, registry=False)
    _table(tmp_path / "results" / "c.csv", ["method", "seed", "epoch", "loss"], [[m, 0, e, 1.0 + 0.1 * i + 0.01 * e] for i, m in enumerate(["ours", "base", "ref"]) for e in range(10)])
    r = _curves(tmp_path)
    assert r.returncode == 0 and "[WARN] style: no ours: every series drawn with equal weight" in r.out, r.out
    assert "[WARN] style: no figure style registry" in r.out
    r = _curves(tmp_path, "--ours", "ours", out="figures/c2.png")
    assert "no ours" not in r.out, r.out


def test_cli_ours_overrides_the_registry(tmp_path):
    _project(tmp_path)
    r = _curves(tmp_path, "--ours", "smm", out="figures/c3.png")
    assert r.returncode == 0, r.out
    meta = json.loads(read(tmp_path / "figures" / "c3.meta.json"))
    assert meta["ours"] == "smm"


# ------------------------------------------------------------------ code-like labels
def test_code_like_series_name_fails_and_the_flag_overrides(tmp_path):
    _project(tmp_path)
    rows = [[m, 0, e, 1.0 + 0.1 * i + 0.01 * e] for i, m in enumerate(["relroute_l", "chgate", "recv"]) for e in range(10)]
    _table(tmp_path / "results" / "k.csv", ["method", "seed", "epoch", "loss"], rows)
    args = ["make_figure.py", "curves", "--project", ".", "--csv", "results/k.csv", "--out", "figures/k.png", "--x", "epoch", "--y", "loss", "--ylabel", "Loss", "--series", "method"]
    r = run(*args, cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "[FAIL] style" in r.out and "chgate" in r.out and "recv" in r.out and "figure_style.py init" in r.out, r.out
    assert not (tmp_path / "figures" / "k.png").exists()                            # refused before anything was drawn
    r = run(*args, "--allow-code-labels", cwd=tmp_path)
    assert r.returncode == 0 and "[WARN] style: code-like series" in r.out, r.out


def test_registering_the_name_fixes_the_fail(tmp_path):
    _project(tmp_path)
    write(tmp_path / "research-state.yaml", read(tmp_path / "research-state.yaml").replace("    aliases:", '      chgate: {label: "Channel gate", color: "#a0522d", line: "-.", marker: "D"}\n    aliases:'))
    rows = [[m, 0, e, 1.0 + 0.1 * i + 0.01 * e] for i, m in enumerate(["relroute_l", "chgate"]) for e in range(10)]
    _table(tmp_path / "results" / "k.csv", ["method", "seed", "epoch", "loss"], rows)
    r = run("make_figure.py", "curves", "--project", ".", "--csv", "results/k.csv", "--out", "figures/k.png", "--x", "epoch", "--y", "loss", "--ylabel", "Loss", "--series", "method", cwd=tmp_path)
    assert r.returncode == 0, r.out
    assert {s["label"] for s in _dicts(tmp_path / "figures" / "k.source.csv")} == {"RelRoute (ours)", "Channel gate"}


def test_the_y_axis_is_never_the_raw_column_name_value(tmp_path):
    _project(tmp_path, registry=False)
    _table(tmp_path / "results" / "v.csv", ["method", "seed", "epoch", "value"], [[m, 0, e, 1.0 + 0.01 * e] for m in ("ours", "base") for e in range(10)])
    args = ["make_figure.py", "curves", "--project", ".", "--csv", "results/v.csv", "--out", "figures/v.png", "--x", "epoch", "--y", "value", "--series", "method"]
    r = run(*args, cwd=tmp_path)
    assert r.returncode == 1 and "[FAIL] style" in r.out and "'value'" in r.out, r.out
    assert run(*args, "--ylabel", "Loss", cwd=tmp_path).returncode == 0
    # a log_adapters.py table names its metric: that is the axis text, with its unit
    _table(tmp_path / "results" / "w.csv", ["epoch", "value", "method", "dataset", "seed", "metric", "units_out"], [[e, 50 + e, m, "D", 0, "metrics/mAP50(B)", "percent"] for m in ("ours", "base") for e in range(10)])
    r = run("make_figure.py", "curves", "--project", ".", "--csv", "results/w.csv", "--out", "figures/w.png", "--x", "epoch", "--y", "value", "--series", "method", cwd=tmp_path)
    assert r.returncode == 0, r.out
    assert "mAP50(B) (%)" in " ".join(read(tmp_path / "figures" / "w.caption.md").split()) + json.loads(read(tmp_path / "figures" / "w.meta.json"))["y_label"]


# ------------------------------------------------------------------ datasets are never hues
def _eff(path):
    rows = []
    for ds, hi in (("m3fd", 40), ("llvip", 60)):
        for m, (g, a, p) in {"relroute_l": (30, hi + 2, 5.1), "smm": (25, hi, 4.0), "cat": (40, hi - 1.5, 6.2), "rgb": (12, hi - 6, 2.0)}.items():
            rows.append([m, ds, g, a, p])
    _table(path, ["method", "dataset", "GFLOPs", "AP", "params_M"], rows)


def test_tradeoff_dataset_is_a_marker_and_the_method_keeps_one_colour(tmp_path):
    _project(tmp_path); _eff(tmp_path / "results" / "eff.csv")
    r = run("make_motivation.py", "tradeoff", "--project", ".", "--csv", "results/eff.csv", "--x", "GFLOPs", "--y", "AP", "--label", "method", "--color", "dataset", "--out", "figures/t.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    src = _dicts(tmp_path / "figures" / "t.source.csv")
    by = {}
    for s in src: by.setdefault(s["method"], set()).add(s["color"])
    assert all(len(v) == 1 for v in by.values()), by                                # the same method has the same colour on both datasets
    assert by["relroute_l"] == {"#c94a5e"} and len({next(iter(v)) for v in by.values()}) == 4
    meta = json.loads(read(tmp_path / "figures" / "t.meta.json"))
    assert meta["dataset_encoding"] == "marker" and meta["datasets"] == ["m3fd", "llvip"]
    assert "marker shape" in read(tmp_path / "figures" / "t.caption.md") and "colour identifies the method" in read(tmp_path / "figures" / "t.caption.md")


def test_tradeoff_panel_encoding_makes_one_axes_per_dataset(tmp_path, monkeypatch):
    _project(tmp_path); _eff(tmp_path / "results" / "eff.csv")
    fig, src, hdr, cap = _in_process(monkeypatch, tmp_path, "make_motivation", ["tradeoff", "--project", ".", "--csv", "results/eff.csv", "--x", "GFLOPs", "--y", "AP", "--label", "method",
                                                                               "--color", "dataset", "--dataset-encoding", "panel", "--out", "figures/p.png"])
    assert len(fig.axes) == 2 and [ax.get_title() for ax in fig.axes] == ["M3FD", "LLVIP"]
    r = run("make_motivation.py", "tradeoff", "--project", ".", "--csv", "results/eff.csv", "--x", "GFLOPs", "--y", "AP", "--label", "method", "--color", "dataset", "--dataset-encoding", "panel",
            "--broken-x", "15,20", "--out", "figures/p2.png", cwd=tmp_path)
    assert r.returncode == 1 and "--broken-x" in r.out


def test_bland_altman_groups_are_markers_not_hues(tmp_path):
    rng = np.random.default_rng(0); rows = []
    for g in ("m3fd", "llvip"):
        for _ in range(30):
            a = rng.normal(50, 10); rows.append([g, a, a + rng.normal(1, 2)])
    _table(tmp_path / "results" / "ba.csv", ["dataset", "m1", "m2"], rows); write(tmp_path / "research-state.yaml", REGISTRY)
    r = run("make_figure.py", "bland-altman", "--project", ".", "--csv", "results/ba.csv", "--a", "m1", "--b", "m2", "--group", "dataset", "--unit", "HU", "--out", "figures/ba.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    src = [s for s in _dicts(tmp_path / "figures" / "ba.source.csv") if s["kind"] == "point"]
    assert {s["marker"] for s in src} == {"o", "s"} and {s["color"] for s in src} == {""}
    assert {s["label"] for s in src} == {"M3FD", "LLVIP"}


# ------------------------------------------------------------------ source.csv style columns, meta and caption files
def test_every_subcommand_writes_style_columns_meta_and_caption(tmp_path):
    _project(tmp_path)
    rng = np.random.default_rng(1)
    _table(tmp_path / "results" / "main.csv", ["run_id", "method", "seed", "rmse_E1", "rmse_E2"],
           [[f"{m}_{s}", m, s, round(b * 0.2 + 0.01 * s, 4), round(b * 0.3 + 0.01 * s, 4)] for m, b in METHODS for s in range(3)])
    write(tmp_path / "research-state.yaml", read(tmp_path / "research-state.yaml") + "results:\n  main_table: results/main.csv\n  group_key: method\n  reference_method: relroute_l\n  primary_metric: rmse_E1\n")
    _table(tmp_path / "results" / "pred.csv", ["label", "score", "method"], [[int(rng.random() < 0.5), round(float(rng.random()), 4), m] for m in ("relroute_l", "smm") for _ in range(60)])
    _table(tmp_path / "results" / "box.csv", ["dataset", "auroc"], [[d, float(v)] for d in ("m3fd", "llvip") for v in rng.normal(0.8, 0.05, 20)])
    cases = [
        (["main", "--out", "figures/f_main.png", "--metrics", "rmse_E1,rmse_E2"], "bars", "method"),
        (["seeds", "--out", "figures/f_seeds.png", "--metrics", "rmse_E1", "--methods", "relroute_l,smm"], "seeds", "method"),
        (["roc", "--csv", "results/pred.csv", "--y-true", "label", "--score", "score", "--group", "method", "--out", "figures/f_roc.png"], "roc", "group"),
        (["box", "--csv", "results/box.csv", "--value", "auroc", "--group", "dataset", "--out", "figures/f_box.png"], "box", "dataset"),
        (["hbar", "--csv", "results/box.csv", "--value", "auroc", "--group", "dataset", "--out", "figures/f_hbar.png"], "hbar", "dataset"),
    ]
    for argv, kind, namecol in cases:
        r = run("make_figure.py", *argv, "--project", ".", cwd=tmp_path)
        assert r.returncode == 0 and not r.crashed, (argv, r.out)
        stem = tmp_path / "figures" / os.path.basename(argv[argv.index("--out") + 1])[:-4]
        src = _dicts(str(stem) + ".source.csv")
        assert {"label", "color", "line", "marker"} <= set(src[0]), argv
        meta = json.loads(read(str(stem) + ".meta.json"))
        assert meta["kind"] == kind and "styles" in meta, argv
        assert read(str(stem) + ".caption.md").startswith("<takeaway"), argv
    src = _dicts(tmp_path / "figures" / "f_main.source.csv")
    assert {s["label"] for s in src} == {"RelRoute (ours)", "SMM", "Concat", "RGB-only"}
    assert {s["color"] for s in src if s["method"] == "relroute_l"} == {"#c94a5e"}
    # the registry check agrees with everything that was drawn
    c = run("figure_style.py", "check", "--project", ".", cwd=tmp_path)
    assert c.fails == 0, c.out


def test_curves_meta_records_what_was_drawn_and_the_caption_says_it(tmp_path):
    _project(tmp_path)
    r = _curves(tmp_path, "--ema", "0.12", "--inset", "last:12", "--annotate", "last", "--baseline", "smm", "--delta-unit", "pp", "--width-mm", "174")
    assert r.returncode == 0 and not r.crashed, r.out
    meta = json.loads(read(tmp_path / "figures" / "c.meta.json"))
    assert meta["kind"] == "curves" and meta["ema"]["alpha"] == 0.12 and meta["inset"]["x0"] and meta["annotate"]["baseline"] == "smm" and meta["annotate"]["direction"] == "lower"
    assert meta["styles"]["relroute_l"]["color"] == "#c94a5e" and meta["styles"]["rgb"]["line"] == "(0, (1, 1))"
    cap = read(tmp_path / "figures" / "c.caption.md")
    assert "EMA" in cap and "Inset" in cap and "lower is better" in cap and "RelRoute (ours)" in cap and "Shaded band" in cap
    assert "red" in cap                                                              # the ours colour as drawn (#c94a5e)
    # an inset that was refused is not in the meta (the caption must not claim it)
    r = _curves(tmp_path, "--ema", "0.12", "--inset", "last:39", out="figures/c4.png")
    assert r.returncode == 0
    assert "inset" not in json.loads(read(tmp_path / "figures" / "c4.meta.json"))


# ------------------------------------------------------------------ the small round-3 fixes
def test_delta_annotation_names_the_metric_and_the_direction_and_labels_stay_in_the_margin(tmp_path, monkeypatch):
    _project(tmp_path)
    fig, src, hdr, cap = _in_process(monkeypatch, tmp_path, "make_figure", ["curves", "--project", ".", "--csv", "results/c.csv", "--x", "epoch", "--y", "loss", "--ylabel", "Loss", "--series", "method",
                                                                           "--panel", "dataset", "--ncols", "2", "--ema", "0.12", "--annotate", "last", "--baseline", "smm", "--width-mm", "170", "--out", "figures/d.png"])
    ax = fig.axes[0]; texts = [t.get_text() for t in ax.texts if t.get_gid() == "end-label"]
    delta = [t for t in texts if t.startswith("Δ")]
    assert delta and "Loss" in delta[0] and "SMM" in delta[0] and "lower is better" in delta[0], texts
    allx = [x for ln in ax.lines for x in ln.get_xdata()]
    lo, hi = ax.get_xlim(); assert hi <= max(allx) + 0.03 * (max(allx) - min(allx)) + 1e-9      # no stretch beyond 3 % of the data range
    rend = fig.canvas.get_renderer(); axbb = ax.get_window_extent(rend)
    for t in ax.texts:
        if t.get_gid() == "end-label": assert mf._text_bb(t, rend).x0 >= axbb.x1 - 1, "an end label sits inside the axes"
    assert not [m for sv, m in mf.audit_layout(fig) if "another panel" in m]


def test_legend_is_opaque_and_touches_no_line(tmp_path, monkeypatch):
    _project(tmp_path)
    fig, src, hdr, cap = _in_process(monkeypatch, tmp_path, "make_figure", ["curves", "--project", ".", "--csv", "results/c.csv", "--x", "epoch", "--y", "loss", "--ylabel", "Loss", "--series", "method", "--out", "figures/l.png"])
    ax = fig.axes[0]; leg = ax.get_legend()
    assert leg is not None and leg.get_frame().get_alpha() in (None, 1.0) and leg.get_frame().get_facecolor()[:3] == (1.0, 1.0, 1.0)
    fig.canvas.draw(); rend = fig.canvas.get_renderer(); bb = leg.get_window_extent(rend); P = mf._line_samples(ax)
    assert not ((P[:, 0] >= bb.x0) & (P[:, 0] <= bb.x1) & (P[:, 1] >= bb.y0) & (P[:, 1] <= bb.y1)).any(), "the legend sits on a line"


def test_place_legend_goes_outside_when_no_corner_is_free():
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(2.4, 1.6))
    rng = np.random.default_rng(0)
    for k in range(30): ax.plot(np.linspace(0, 1, 50), rng.random(50), lw=1)             # lines everywhere
    hs = [ax.plot([], [], label=f"s{i}")[0] for i in range(3)]
    lg = mf.place_legend(fig, ax, hs, [f"series {i}" for i in range(3)])
    fig.canvas.draw(); rend = fig.canvas.get_renderer(); bb = lg.get_window_extent(rend); axbb = ax.get_window_extent(rend)
    assert bb.y0 >= axbb.y1 - 1 or bb.x0 >= axbb.x1 - 1                                    # above or right of the data, not over it
    plt.close(fig)


def test_displaced_labels_get_leader_lines_and_near_ones_do_not():
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(3.4, 2.4)); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    pts = [(0.5, 0.5, 300.0), (0.55, 0.57, 3000.0), (0.1, 0.1, 30.0)]                       # a big neighbour blocks the near offset of the first label
    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=[p[2] for p in pts])
    lead = []
    far = [((4, 3), "left", "bottom"), ((-40, -30), "right", "top")]
    res = mf.place_labels(fig, ax, [(0.5, 0.5, "centre", "k", False, far), (0.1, 0.1, "alone", "k", False)], markers=pts, leader_mm=2.0, leaders=lead)
    assert res[0] is not None and res[1] is not None
    assert lead == [0]                                                                       # the boxed-in point's label moved away: leader; the isolated one sits next to its marker: none
    plt.close(fig)


def test_markers_at_the_edge_are_not_clipped(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt
    _table(tmp_path / "fr.csv", ["method", "params", "AP", "GF"], [["a", 1, 10, 100], ["b", 5, 20, 100], ["ours", 9, 30, 400]])
    fig, src, hdr, cap = _in_process(monkeypatch, tmp_path, "make_motivation", ["tradeoff", "--csv", "fr.csv", "--x", "params", "--y", "AP", "--size", "GF", "--ours", "ours", "--out", "figures/e.png"])
    ax = fig.axes[0]; fig.canvas.draw(); rend = fig.canvas.get_renderer(); axbb = ax.get_window_extent(rend)
    for coll in ax.collections:
        for off, s in zip(coll.get_offsets(), np.resize(coll.get_sizes(), len(coll.get_offsets()))):
            x, y = ax.transData.transform(off); r = np.sqrt(s) / 2 * fig.dpi / 72
            assert axbb.x0 <= x - r + 1 and x + r - 1 <= axbb.x1 and axbb.y0 <= y - r + 1 and y + r - 1 <= axbb.y1, "a marker is cut by the axes"
    plt.close(fig)
