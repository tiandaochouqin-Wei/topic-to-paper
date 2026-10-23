# -*- coding: utf-8 -*-
"""statistical panels modelled on the ACSR paper (Figs 5-8): make_motivation.py tradeoff (colour / broken axis / bubble legend /
label placement), make_figure.py curves (EMA, inset, annotation), stems, box, hbar. Synthetic data in tmp_path; every PDF must be vector."""
import csv
import io
import os
import re
import sys

import numpy as np
import pytest

from conftest import SCRIPTS, read, run, write

sys.path.insert(0, str(SCRIPTS))
import make_figure as mf  # noqa: E402


def _vector(path):
    """a data panel is vector: no image XObject (the ProcSet line of every matplotlib PDF names /ImageB, so look for the Subtype)"""
    b = open(path, "rb").read()
    assert len(b) > 1000 and b.startswith(b"%PDF"), path
    assert not re.search(rb"/Subtype\s*/Image\b", b), f"{path} embeds a raster image"


def _outputs(root, out):
    stem = out[:-4]
    for suffix in (".png", ".pdf", "_gray.png", ".source.csv"):
        assert os.path.exists(root / (stem + suffix)), stem + suffix
    assert out in read(root / "figures.csv")
    _vector(root / (stem + ".pdf"))
    return list(csv.DictReader(io.open(root / (stem + ".source.csv"), encoding="utf-8")))


def _table(path, header, rows):
    write(path, "\n".join([",".join(header)] + [",".join(str(c) for c in r) for r in rows]) + "\n")


# ------------------------------------------------------------------ pure functions
def test_ema_formula():
    assert np.allclose(mf.ema([1, 2, 3, 4], 0.5), [1, 1.5, 2.25, 3.125])
    assert np.allclose(mf.ema([5.0, 1.0, 9.0], 1.0), [5, 1, 9])                       # alpha = 1 is the raw series
    s = mf.ema([0, 10, 10, 10], 0.12)
    assert s[0] == 0 and abs(s[1] - 1.2) < 1e-12 and abs(s[2] - (0.12 * 10 + 0.88 * 1.2)) < 1e-12
    with pytest.raises(ValueError):
        mf.ema([1, 2], 0)


def test_place_labels_never_overlap_and_drop_the_rest():
    import matplotlib.pyplot as plt
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    xs, ys = rng.uniform(0, 1, 45), rng.uniform(0, 1, 45)
    ax.scatter(xs, ys, s=8); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    items = [(x, y, f"method-{i}", "#333333", i < 3) for i, (x, y) in enumerate(zip(xs, ys))]
    res = mf.place_labels(fig, ax, items, fontsize=5.8)
    box = ax.get_window_extent(fig.canvas.get_renderer())
    got = [b for b in res if b is not None]
    assert len(res) == len(items) and 5 < len(got) < len(items)                      # a crowd cannot all be named: some are dropped, not overlapped
    assert all(res[i] is not None for i in range(3)) or any(r is None for r in res)   # priority order: earlier items are served first
    for i, a in enumerate(got):
        assert box.x0 <= a.x0 and a.x1 <= box.x1 and box.y0 <= a.y0 and a.y1 <= box.y1
        for b in got[i + 1:]:
            assert not (a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1), "two placed labels overlap"
    plt.close(fig)


# ------------------------------------------------------------------ curves (Fig 6)
def _curves(path, epochs_ours=40, epochs_base=30):
    rng = np.random.default_rng(1); rows = []
    for ds, hi in (("M3FD", 85.0), ("LLVIP", 95.0)):
        for m, ne, gain in (("ACSR", epochs_ours, 2.0), ("Base", epochs_base, 0.0)):
            for sd in (0, 1):
                for e in range(1, ne + 1):
                    rows.append([ds, m, sd, e, round(hi + gain - 40 * np.exp(-e / 8) + rng.normal(0, 0.8), 4)])
    _table(path, ["dataset", "method", "seed", "epoch", "AP50"], rows)
    return rows


def test_curves_ema_inset_annotation_numbers_match_the_input(tmp_path):
    rows = _curves(tmp_path / "curves.csv")
    out = "figures/fig_c6.png"
    r = run("make_figure.py", "curves", "--csv", "curves.csv", "--x", "epoch", "--y", "AP50", "--series", "method", "--panel", "dataset",
            "--ours", "ACSR", "--ema", "0.2", "--inset", "last:10", "--annotate", "last", "--delta-unit", "pp", "--letters", "--ncols", "2",
            "--free-y", "--width-mm", "120", "--height-in", "2.4", "--out", out, cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "layout audit clean" in r.out and "[WARN] curves" not in r.out, r.out      # inset axes are not "another panel"
    src = _outputs(tmp_path, out)
    summ = [s for s in src if s["kind"] == "summary"]
    assert [s["panel"] for s in summ] == ["LLVIP", "M3FD"] and all(s["epoch"] == "30.0" for s in summ)   # last epoch both series share = 30, not 40
    for s in summ:
        def smooth(method):
            by = {}
            for p, m, sd, e, v in rows:
                if p == s["panel"] and m == method: by.setdefault(e, []).append(v)
            es = sorted(by); return dict(zip(es, mf.ema([np.mean(by[e]) for e in es], 0.2)))
        o, b = smooth("ACSR")[30], smooth("Base")[30]
        assert abs(float(s["ours"]) - o) < 1e-9 and abs(float(s["baseline"]) - b) < 1e-9 and abs(float(s["delta"]) - (o - b)) < 1e-9
    pts = [s for s in src if s["kind"] == "point"]
    assert {"AP50_smooth", "AP50_mean", "AP50_sd"} <= set(src[0]) and all(float(p["n"]) == 2 for p in pts)
    assert "α = 0.2" in read(tmp_path / "figures.csv")                                 # the smoothing weight is in the caption text
    assert "annotated LLVIP: ΔAP50 @ epoch 30" in r.out


def test_curves_without_new_options_keep_the_old_source_columns(tmp_path):
    _curves(tmp_path / "curves.csv")
    r = run("make_figure.py", "curves", "--csv", "curves.csv", "--x", "epoch", "--y", "AP50", "--series", "method", "--out", "figures/fig_old.png", cwd=tmp_path)
    assert r.returncode == 0, r.out
    assert list(csv.reader(io.open(tmp_path / "figures" / "fig_old.source.csv", encoding="utf-8")))[0] == ["panel", "series", "epoch", "AP50_mean", "AP50_sd", "n"]


def test_curves_annotate_needs_ours_and_a_baseline_series(tmp_path):
    _curves(tmp_path / "curves.csv")
    r = run("make_figure.py", "curves", "--csv", "curves.csv", "--x", "epoch", "--y", "AP50", "--series", "method", "--annotate", "last", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "--ours" in r.out, r.out
    r = run("make_figure.py", "curves", "--csv", "curves.csv", "--x", "epoch", "--y", "AP50", "--series", "method", "--ours", "ACSR", "--baseline", "nope", "--annotate", "last", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "nope" in r.out, r.out
    r = run("make_figure.py", "curves", "--csv", "curves.csv", "--x", "epoch", "--y", "AP50", "--series", "method", "--ema", "1.5", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "--ema" in r.out, r.out


def test_curves_explicit_inset_range_and_single_panel(tmp_path):
    _curves(tmp_path / "curves.csv")
    r = run("make_figure.py", "curves", "--csv", "curves.csv", "--x", "epoch", "--y", "AP50", "--series", "method", "--ours", "ACSR", "--inset", "20:30", "--out", "figures/fig_i.png", cwd=tmp_path)
    assert r.returncode == 0 and "layout audit clean" in r.out, r.out
    _outputs(tmp_path, "figures/fig_i.png")


# ------------------------------------------------------------------ stems (Fig 7)
def test_stems_gains_count_and_labels(tmp_path):
    rows = [["R18", "CNN", 56.0, 59.2], ["R50", "CNN", 57.0, 58.9], ["Star", "CNN", 57.4, 59.2], ["Mamba", "SSM", 58.1, 59.9], ["DMamba", "SSM", 58.4, 59.6], ["Bad", "Hybrid", 59.5, 59.1]]
    _table(tmp_path / "bb.csv", ["backbone", "family", "baseline_AP", "ours_AP"], rows)
    out = "figures/fig_stems.png"
    r = run("make_figure.py", "stems", "--csv", "bb.csv", "--item", "backbone", "--x", "baseline_AP", "--y", "ours_AP", "--group", "family", "--out", out, cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "5/6 backbones above y = x" in r.out and "layout audit clean" in r.out, r.out
    src = _outputs(tmp_path, out)
    assert [s["backbone"] for s in src] == [x[0] for x in rows]
    for s, x in zip(src, rows):
        assert abs(float(s["gain"]) - (x[3] - x[2])) < 1e-9 and s["above_diagonal"] == str(x[3] > x[2]) and s["family"] == x[1]
        assert s["label_placed"] == "True"


def test_stems_without_group_colours_every_item(tmp_path):
    _table(tmp_path / "bb.csv", ["backbone", "baseline_AP", "ours_AP"], [["a", 1.0, 1.5], ["b", 1.2, 1.9], ["c", 2.0, 2.2]])
    r = run("make_figure.py", "stems", "--csv", "bb.csv", "--item", "backbone", "--x", "baseline_AP", "--y", "ours_AP", "--out", "figures/fig_s2.png", cwd=tmp_path)
    assert r.returncode == 0 and "3/3 backbones above y = x" in r.out, r.out
    _outputs(tmp_path, "figures/fig_s2.png")


def test_stems_missing_column_fails_cleanly(tmp_path):
    _table(tmp_path / "bb.csv", ["backbone", "baseline_AP", "ours_AP"], [["a", 1.0, 1.5]])
    r = run("make_figure.py", "stems", "--csv", "bb.csv", "--item", "backbone", "--x", "baseline_AP", "--y", "nope", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "column nope" in r.out, r.out


# ------------------------------------------------------------------ box (Fig 8b)
def test_box_five_numbers_match_numpy(tmp_path):
    rng = np.random.default_rng(2); vals = {"M3FD": rng.normal(0.9, 0.05, 60), "SUN": rng.normal(0.72, 0.1, 80), "NYU": rng.normal(0.7, 0.1, 50)}
    _table(tmp_path / "auroc.csv", ["dataset", "auroc"], [[d, round(float(v), 6)] for d, vs in vals.items() for v in vs])
    out = "figures/fig_box.png"
    r = run("make_figure.py", "box", "--csv", "auroc.csv", "--value", "auroc", "--group", "dataset", "--whis", "10,90", "--vline", "0.5", "--out", out, cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed and "layout audit clean" in r.out, r.out
    src = _outputs(tmp_path, out)
    assert [s["dataset"] for s in src] == list(vals) and {"whisker_lo_p10", "whisker_hi_p90"} <= set(src[0])
    for s, (d, v) in zip(src, vals.items()):
        v = np.round(v, 6); lo, q1, md, q3, hi = np.percentile(v, [10, 25, 50, 75, 90])
        assert int(s["n"]) == len(v) and abs(float(s["whisker_lo_p10"]) - lo) < 1e-9 and abs(float(s["q1"]) - q1) < 1e-9
        assert abs(float(s["median"]) - md) < 1e-9 and abs(float(s["q3"]) - q3) < 1e-9 and abs(float(s["whisker_hi_p90"]) - hi) < 1e-9


def test_box_warns_on_tiny_groups(tmp_path):
    _table(tmp_path / "a.csv", ["g", "v"], [["x", 1], ["x", 2], ["y", 1], ["y", 2], ["y", 3], ["y", 4], ["y", 5]])
    r = run("make_figure.py", "box", "--csv", "a.csv", "--value", "v", "--group", "g", "--out", "figures/b.png", cwd=tmp_path)
    assert r.returncode == 0 and "[WARN] box:" in r.out and "'x'" in r.out and "'y'" not in r.out, r.out


# ------------------------------------------------------------------ hbar (Fig 8c)
def test_hbar_values_signs_and_best_flag(tmp_path):
    _table(tmp_path / "d.csv", ["dataset", "dAP"], [["M3FD", -2.0], ["M3FD", -1.96], ["LLVIP", -4.1], ["UODAC", 0.5], ["NYU", -0.43]])
    out = "figures/fig_hbar.png"
    r = run("make_figure.py", "hbar", "--csv", "d.csv", "--value", "dAP", "--group", "dataset", "--out", out, cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed and "layout audit clean" in r.out, r.out
    src = _outputs(tmp_path, out)
    assert [s["dataset"] for s in src] == ["M3FD", "LLVIP", "UODAC", "NYU"]
    assert [round(float(s["dAP"]), 3) for s in src] == [-1.98, -4.1, 0.5, -0.43] and [s["n"] for s in src] == ["2", "1", "1", "1"]
    assert [s["best"] for s in src] == ["False", "False", "True", "False"]                # higher is best by default
    r = run("make_figure.py", "hbar", "--csv", "d.csv", "--value", "dAP", "--group", "dataset", "--lower", "--out", "figures/fig_hbar2.png", cwd=tmp_path)
    assert [s["best"] for s in _outputs(tmp_path, "figures/fig_hbar2.png")] == ["False", "True", "False", "False"]


def test_hbar_missing_column_fails_cleanly(tmp_path):
    _table(tmp_path / "d.csv", ["dataset", "dAP"], [["a", 1]])
    r = run("make_figure.py", "hbar", "--csv", "d.csv", "--value", "nope", "--group", "dataset", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "column nope" in r.out, r.out


# ------------------------------------------------------------------ tradeoff (Fig 5)
def _frontier(path, n_prior=8):
    rng = np.random.default_rng(4); rows = []
    for bi, ds in enumerate(("M3FD", "LLVIP", "SUN")):
        for i in range(n_prior):
            rows.append([f"prior{i}", ds, round(float(rng.uniform(3, 50) if i < n_prior - 1 else 150 + 20 * bi), 2), round(float(rng.uniform(20, 60)), 2), round(float(rng.uniform(8, 786)), 1)])
        rows.append(["ACSR", ds, 5 + 3 * bi, 65 - 4 * bi, 19.2])
        rows.append(["ACSR-S", ds, 4 + 3 * bi, 55 - 4 * bi, 9.0])
    _table(path, ["method", "dataset", "params", "AP", "GFLOPs"], rows)
    return rows


def _args(*a): return ["--csv", "fr.csv", "--x", "params", "--y", "AP", *a]


def test_tradeoff_colour_marker_label_and_source_columns(tmp_path):
    _frontier(tmp_path / "fr.csv"); out = "figures/fig_fr.png"
    r = run("make_motivation.py", "tradeoff", *_args("--size", "GFLOPs", "--color", "dataset", "--ours", "ACSR,ACSR-S", "--marker-ours", "star", "--bubble-legend", "8,100,786",
                                                     "--title", "Frontier", "--no-front", "--width-mm", "150", "--height-in", "3", "--out", out), cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    src = _outputs(tmp_path, out)
    assert {"label", "params", "AP", "GFLOPs", "n", "on_front", "dataset", "placed_label"} <= set(src[0])
    assert {s["dataset"] for s in src} == {"M3FD", "LLVIP", "SUN"} and len(src) == 3 * 10
    assert {s["placed_label"] for s in src} <= {"yes", "no", "skipped"}
    ours = [s for s in src if s["label"] in ("ACSR", "ACSR-S")]
    assert len(ours) == 6 and all(s["placed_label"] in ("yes", "no") for s in ours)    # ours is named at every point
    prior = [s for s in src if s["label"].startswith("prior")]
    assert sum(1 for s in prior if s["placed_label"] != "skipped") <= len({s["label"] for s in prior})   # each prior method is named at most once
    assert "Pareto front" not in read(tmp_path / "figures.csv")
    assert "ours (ACSR [M3FD]) is on the Pareto front" in r.out                       # the front is per benchmark


def test_tradeoff_front_is_per_colour_group(tmp_path):
    _table(tmp_path / "fr.csv", ["method", "dataset", "params", "AP"], [["a", "D1", 1, 50], ["b", "D1", 2, 40], ["a", "D2", 1, 20], ["b", "D2", 2, 45]])
    r = run("make_motivation.py", "tradeoff", *_args("--color", "dataset", "--ours", "b", "--out", "figures/fig_g.png"), cwd=tmp_path)
    assert r.returncode == 0, r.out
    src = {(s["label"], s["dataset"]): s["on_front"] for s in _outputs(tmp_path, "figures/fig_g.png")}
    assert src == {("a", "D1"): "True", ("b", "D1"): "False", ("a", "D2"): "True", ("b", "D2"): "True"}   # (a, D1) would dominate (b, D2) in a pooled front
    assert "[WARN] tradeoff: ours (b [D1]) is dominated by ['a [D1]']" in r.out


def _capture(monkeypatch, tmp_path, argv):
    import make_motivation as mm
    got = []
    monkeypatch.setattr(mm, "finish", lambda fig, a, src, hdr, root, caption: got.append((fig, src, caption)))
    monkeypatch.setattr(sys, "argv", ["make_motivation.py", "tradeoff", *argv]); monkeypatch.chdir(tmp_path)
    mm.main()
    return got[0]


def test_tradeoff_broken_axis_makes_two_axes_with_the_gap_between(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt
    _frontier(tmp_path / "fr.csv")
    fig, src, cap = _capture(monkeypatch, tmp_path, _args("--color", "dataset", "--ours", "ACSR", "--broken-x", "60,140", "--size", "GFLOPs", "--bubble-legend", "8,100,786", "--out", "figures/b.png"))
    axs = fig.axes
    assert len(axs) == 2 and axs[0].get_xlim()[1] == 60 and axs[1].get_xlim()[0] == 140
    assert axs[0].get_shared_y_axes().joined(axs[0], axs[1]) and "broken between 60 and 140" in cap
    assert len(axs[0].collections) + len(axs[1].collections) >= len(src)                 # every point is drawn on the axis it belongs to
    assert sum(1 for ax in axs if ax.get_legend() is not None) == 1                       # legend once
    plt.close(fig)
    fig, _, _ = _capture(monkeypatch, tmp_path, _args("--out", "figures/s.png"))
    assert len(fig.axes) == 1
    plt.close(fig)


def test_tradeoff_broken_axis_rejects_points_in_the_gap_and_logx(tmp_path):
    _frontier(tmp_path / "fr.csv")
    r = run("make_motivation.py", "tradeoff", *_args("--broken-x", "10,40", "--out", "figures/b.png"), cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "hidden interval" in r.out, r.out
    r = run("make_motivation.py", "tradeoff", *_args("--broken-x", "60,140", "--logx", "--out", "figures/b.png"), cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "--logx" in r.out, r.out


def test_tradeoff_crowded_labels_are_dropped_and_listed(tmp_path):
    rows = [[f"method{i}", 10 + 0.02 * i, 50 + 0.01 * i] for i in range(14)] + [["far", 80, 20]]
    _table(tmp_path / "fr.csv", ["method", "params", "AP"], rows)
    r = run("make_motivation.py", "tradeoff", *_args("--out", "figures/fig_d.png"), cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    src = {s["label"]: s["placed_label"] for s in _outputs(tmp_path, "figures/fig_d.png")}
    dropped = [k for k, v in src.items() if v == "no"]
    assert dropped and "label(s) dropped" in r.out and all(k in r.out for k in dropped), r.out
    assert src["far"] == "yes" and src["method0"] == "yes"


def test_tradeoff_single_ours_messages_unchanged(tmp_path):
    _table(tmp_path / "fr.csv", ["method", "params", "AP"], [["tiny", 2.6, 30], ["big", 120, 36], ["ours", 6.2, 35.6]])
    r = run("make_motivation.py", "tradeoff", *_args("--ours", "ours", "--logx", "--out", "figures/fig_u.png"), cwd=tmp_path)
    assert r.returncode == 0 and "ours (ours) is on the Pareto front" in r.out, r.out
    r = run("make_motivation.py", "tradeoff", *_args("--ours", "nope", "--out", "figures/fig_u2.png"), cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "nope" in r.out, r.out


# ------------------------------------------------------------------ occupancy-aware inset / annotation, marker-aware labels
def _run_curves_in_process(monkeypatch, tmp_path, argv):
    got = []
    monkeypatch.setattr(mf, "finish", lambda fig, a, src, hdr, root, caption: got.append((fig, src)))
    monkeypatch.setattr(sys, "argv", ["make_figure.py", "curves", *argv]); monkeypatch.chdir(tmp_path)
    mf.main()
    return got[0]


def test_curves_inset_and_annotation_avoid_a_falling_curve_ending_lower_right(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt
    rows = []
    for m, off in (("ours", 0.0), ("base", 4.0)):
        for e in range(1, 61): rows.append([m, e, round(100 * np.exp(-e / 20) + off, 4)])      # falls from the upper left to the lower right
    _table(tmp_path / "fall.csv", ["method", "epoch", "loss"], rows)
    fig, src = _run_curves_in_process(monkeypatch, tmp_path, ["--csv", "fall.csv", "--x", "epoch", "--y", "loss", "--series", "method", "--ours", "ours", "--ema", "0.3",
                                                              "--inset", "last:10", "--annotate", "last", "--width-mm", "88", "--height-in", "2.6", "--out", "figures/fall.png"])
    ax = fig.axes[0]; rend = fig.canvas.get_renderer(); axbb = ax.get_window_extent(rend)
    ins = ax.child_axes[0].get_window_extent(rend); txt = [t for t in ax.texts if t.get_gid() == "stat-annotation"][0].get_window_extent(rend)
    for name, bb in (("inset", ins), ("annotation", txt)):
        cx = ((bb.x0 + bb.x1) / 2 - axbb.x0) / axbb.width; cy = ((bb.y0 + bb.y1) / 2 - axbb.y0) / axbb.height
        assert not (cx > 0.5 and cy < 0.5), f"{name} sits in the lower right, on the curve end"
    assert not [m for sv, m in mf.audit_layout(fig) if "covers" in m], mf.audit_layout(fig)
    plt.close(fig)


def test_audit_flags_an_inset_or_annotation_sitting_on_a_line():
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(3, 2)); ax.plot([0, 1], [0, 1], lw=1)
    ax.inset_axes([0.3, 0.3, 0.4, 0.4]).plot([0, 1], [0, 1])                      # right on the diagonal
    issues = mf.audit_layout(fig); plt.close(fig)
    assert any(sv == "WARN" and "inset" in m and "covers plotted lines" in m for sv, m in issues), issues
    fig, ax = plt.subplots(figsize=(3, 2)); ax.plot([0, 1], [0, 1], lw=1)
    ax.inset_axes([0.6, 0.05, 0.35, 0.3]).plot([0, 1], [0, 1])                     # lower right is empty
    ax.text(0.03, 0.97, "annotation", transform=ax.transAxes, va="top", gid="stat-annotation")
    assert not [m for sv, m in mf.audit_layout(fig) if "covers" in m]
    ax.texts[0].set_position((0.5, 0.5)); ax.texts[0].set_ha("center"); ax.texts[0].set_va("center")
    assert any("annotation" in m and "covers" in m for sv, m in mf.audit_layout(fig))
    plt.close(fig)


def test_place_labels_keeps_off_neighbour_markers():
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(3.4, 2.4)); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    pts = [(0.50, 0.5, 300.0), (0.53, 0.5, 300.0)]                                  # close, big markers: B's marker lies right of A
    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=[p[2] for p in pts])
    item = [(0.50, 0.5, "A-label", "k", False)]
    bare = mf.place_labels(fig, ax, item)[0]
    assert bare is not None and bare.x0 > ax.transData.transform((0.5, 0.5))[0]    # without markers the first offset (to the right) wins
    withm = mf.place_labels(fig, ax, item, markers=pts)[0]
    assert withm is not None and withm.x1 <= ax.transData.transform((0.5, 0.5))[0] + 1    # now it moves to the free side
    for k, (x, y, s_) in enumerate(pts):
        mb = mf.marker_bbox(fig, ax, x, y, s_)
        if k == 0: continue                                                         # own marker is exempt
        assert not (withm.x0 < mb.x1 and mb.x0 < withm.x1 and withm.y0 < mb.y1 and mb.y0 < withm.y1), "label sits on the neighbour's marker"
    # a label with no free offset at all is dropped rather than placed on a marker
    crowd = [(0.5 + 0.004 * i, 0.5, 4000.0) for i in range(6)]
    res = mf.place_labels(fig, ax, [(0.5, 0.5, "boxed-in", "k", False, None, 0)], markers=crowd)
    assert res == [None]
    plt.close(fig)
