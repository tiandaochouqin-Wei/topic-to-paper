# -*- coding: utf-8 -*-
"""Regression tests for the bugs a real end-to-end figure trial (cvpr2027_fusion, frozen skill 46add61) found; one test per bug, each built from the
bug's repro command on a small synthetic input in tmp_path. Bug numbers are those of the trial's BUGS.md; extra items from the visual review of the curves
are named test_curves_*. Everything here is synthetic (no trial data)."""
import colorsys
import csv
import io
import json
import os
import re
import sys

import numpy as np
import pytest

from conftest import SCRIPTS, edit, read, run, write

sys.path.insert(0, str(SCRIPTS))
import make_figure as mf  # noqa: E402

fitz = pytest.importorskip("fitz")


# ------------------------------------------------------------------ helpers
def _table(path, header, rows):
    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    with io.open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def _dicts(path):
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig")))


def _sparse_curves(path, n_pts=10):
    """val AP logged every 10 epochs, 3 seeds, ours ends at 37.7 and the baseline at 36.9 (raw gap +0.8), both start low: the EMA (alpha 0.12) of 10 points
    ends about 6 AP below the truth, and the baseline's lag differs, so the smoothed 'gap' has another sign"""
    rows = []
    for m, end, k in (("ours", 37.7, 25.0), ("base", 36.9, 21.0)):
        for sd, off in ((0, -0.1), (1, 0.0), (2, 0.1)):
            for i in range(n_pts):
                e = 9 + 10 * i
                v = end - k * np.exp(-i / 2.2) if i < n_pts - 1 else end
                rows.append([m, sd, e, round(float(v) + off * (i == n_pts - 1) + 0.05 * sd * (i < n_pts - 1), 4)])
    _table(path, ["method", "seed", "epoch", "value"], rows)
    return rows


def _dense_loss(path, n_pts=100, with_outlier=True):
    rows = []
    for m, off in (("ours", 0.15), ("base", 0.0)):
        for sd in (0, 1, 2):
            for e in range(n_pts):
                v = 2.0 + off + 3.0 * np.exp(-e / 15) + 0.02 * sd
                if with_outlier and e == 0: v += 2.5                         # the epoch-0 spike that used to seed the EMA
                rows.append([m, sd, e, round(float(v), 5)])
    _table(path, ["method", "seed", "epoch", "value"], rows)
    return rows


def _curves(tmp_path, csvname, *extra, out="figures/c.png", cwd=None):
    return run("make_figure.py", "curves", "--project", ".", "--csv", csvname, "--out", out, "--x", "epoch", "--y", "value", "--ylabel", "Loss", "--series", "method", *extra, cwd=cwd or tmp_path)


def _curves_in_process(monkeypatch, tmp_path, argv):
    got = []
    monkeypatch.setattr(mf, "finish", lambda fig, a, src, hdr, root, caption: got.append((fig, src, caption)))
    monkeypatch.setattr(sys, "argv", ["make_figure.py", "curves", *argv]); monkeypatch.chdir(tmp_path)
    mf.main()
    return got[0]


def _pdf_spans(path):
    doc = fitz.open(str(path)); pg = doc[0]
    return [sp for b in pg.get_text("dict")["blocks"] for l in b.get("lines", []) for sp in l["spans"] if sp["text"].strip()], pg.rect.width / 72 * 25.4


def _family(font):
    f = font.lower().split("+")[-1].split("-")[0]
    return re.sub(r"(psmt|ps|mt)$", "", f)


# ------------------------------------------------------------------ 1 (H): curves --ema annotation numbers
def test_bug01_ema_annotation_numbers_are_raw_seed_means_and_sparse_ema_warns(tmp_path):
    rows = _sparse_curves(tmp_path / "results" / "c.csv")
    means = {m: [np.mean([r[3] for r in rows if r[0] == m and r[2] == e]) for e in sorted({r[2] for r in rows})] for m in ("ours", "base")}
    assert abs(mf.ema(means["ours"], 0.12)[-1] - 37.7) > 3                           # the bug: the EMA of 10 points ends far from the data
    r = _curves(tmp_path, "results/c.csv", "--ema", "0.12", "--inset", "last:30", "--annotate", "last", "--ours", "ours", "--baseline", "base", "--out", "figures/c.png")
    assert r.returncode == 0 and not r.crashed, r.out
    assert re.search(r"\[WARN\] curves: --ema 0\.12 with only 10 points per series.*not meaningful", r.out), r.out
    summ = [s for s in _dicts(tmp_path / "figures" / "c.source.csv") if s["kind"] == "summary"]
    assert len(summ) == 1 and summ[0]["epoch"] == "99.0" and summ[0]["basis"] == "raw seed mean"
    assert float(summ[0]["ours"]) == pytest.approx(37.7, abs=1e-6) and float(summ[0]["baseline"]) == pytest.approx(36.9, abs=1e-6)
    assert float(summ[0]["delta"]) == pytest.approx(0.8, abs=1e-6)                   # sign and size of the real gap
    cap = read(tmp_path / "figures.csv")
    assert "RAW seed means" in cap and "not applied" in cap                         # the caption says which numbers these are


def test_bug01_dense_series_annotates_raw_values_and_the_ema_starts_at_the_first_raw_value(tmp_path):
    rows = _dense_loss(tmp_path / "results" / "l.csv")
    r = _curves(tmp_path, "results/l.csv", "--ema", "0.12", "--inset", "last:30", "--annotate", "last", "--ours", "ours", "--baseline", "base", "--band", "none", "--out", "figures/l.png")
    assert r.returncode == 0 and "[WARN] curves: --ema" not in r.out, r.out
    src = _dicts(tmp_path / "figures" / "l.source.csv")
    summ = [s for s in src if s["kind"] == "summary"][0]
    last = {m: np.mean([x[3] for x in rows if x[0] == m and x[2] == 99]) for m in ("ours", "base")}
    assert float(summ["ours"]) == pytest.approx(last["ours"], abs=1e-6) and float(summ["baseline"]) == pytest.approx(last["base"], abs=1e-6)
    for m in ("ours", "base"):
        first = [s for s in src if s["series"] == m and s["kind"] == "point"][0]
        assert float(first["value_smooth"]) == pytest.approx(float(first["value_mean"]), abs=1e-9)     # s_0 = x_0, not 0 and not a mean
    assert "EMA is for drawing only" in read(tmp_path / "figures.csv")


def test_curves_ema_of_a_constant_series_is_that_constant():
    assert np.allclose(mf.ema([4.2] * 60, 0.12), 4.2)
    assert mf.ema([7.0, 1.0, 1.0], 0.12)[0] == 7.0


# ------------------------------------------------------------------ 2 (H): G5 on .png rows
def _tiny_text_pdf(path, width_mm=180.0, font_pt=7.0):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, 40 / 25.4)); ax.plot([0, 1], [0, 1]); ax.set_xlabel("x axis label", fontsize=font_pt); ax.set_ylabel("y", fontsize=font_pt)
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)


def _register(project, file, width):
    rows = list(csv.DictReader(io.open(project / "figures.csv", encoding="utf-8-sig")))
    rows.append({"file": file, "print_width_mm": str(width), "source_data": "results/summary.csv", "inspected": "yes", "issues": ""})
    with io.open(project / "figures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "print_width_mm", "source_data", "inspected", "issues"]); w.writeheader(); w.writerows(rows)


def test_bug02_g5_measures_the_sibling_pdf_of_a_png_row_and_warns_when_only_a_raster_exists(research):
    from PIL import Image
    _tiny_text_pdf(research / "figures" / "fig_row.pdf")                                          # 7 pt at 180 mm native, registered at 45 mm -> 1.75 pt
    Image.new("RGB", (900, 400), "white").save(research / "figures" / "fig_row.png"); _register(research, "figures/fig_row.png", 45)
    Image.new("RGB", (900, 400), "white").save(research / "figures" / "fig_only.png"); _register(research, "figures/fig_only.png", 45)
    r = run("gate_check.py", "dpi", cwd=research)
    assert re.search(r"\[FAIL\] dpi: figures/fig_row\.pdf 印刷最小字号", r.out), r.out         # the PDF next to the registered .png was measured
    assert re.search(r"\[WARN\] dpi: figures/fig_only\.png 未量字号（只有栅格）", r.out), r.out


def test_bug02_curves_inset_and_all_text_stay_at_the_house_size(tmp_path):
    _dense_loss(tmp_path / "results" / "l.csv")
    r = _curves(tmp_path, "results/l.csv", "--ema", "0.12", "--inset", "last:30", "--annotate", "last", "--ours", "ours", "--baseline", "base", "--width-mm", "174.6", "--out", "figures/l.png")
    assert r.returncode == 0, r.out
    spans, native = _pdf_spans(tmp_path / "figures" / "l.pdf")
    sizes = {round(sp["size"], 1) for sp in spans}
    assert min(sizes) >= 6.0, sizes                                                              # inset tick labels were 4.9 pt printed
    assert sizes == {7.5}, sizes                                                                 # one font size for axes, ticks, legend, end labels, inset
    assert len({_family(sp["font"]) for sp in spans}) == 1, {sp["font"] for sp in spans}        # and one serif family


# ------------------------------------------------------------------ 3 / 4 / 13: log_adapters json, units none, epoch_base
def test_bug03_json_adapter_list_of_dicts_and_dict_of_lists(tmp_path):
    log = [{"epoch": e, "box": 1.0 - 0.01 * e, "hardware": "gpu"} | ({"val_AP": 20 + e} if e % 10 == 9 else {}) for e in range(30)]
    write(tmp_path / "log.json", json.dumps(log))
    r = run("log_adapters.py", "--adapter", "json", "--input", "log.json", "--metric-col", "val_AP", "--method", "m", "--dataset", "D", "--units", "percent", "--out", "o.csv", cwd=tmp_path)
    assert r.fails == 0 and not r.crashed, r.out
    rows = _dicts(tmp_path / "o.csv")
    assert [x["epoch"] for x in rows] == ["9", "19", "29"] and [float(x["value"]) for x in rows] == [29.0, 39.0, 49.0]
    assert rows[0]["epoch_base"] == "0"                                                           # bug 13: numbering base, not the first epoch that carries val_AP
    write(tmp_path / "log2.json", json.dumps({"epoch": [1, 2, 3], "loss": [3.0, 2.0, 1.0]}))
    r = run("log_adapters.py", "--adapter", "json", "--input", "log2.json", "--metric-col", "loss", "--method", "m", "--units", "none", "--out", "o2.csv", cwd=tmp_path)
    assert r.fails == 0, r.out
    assert [float(x["value"]) for x in _dicts(tmp_path / "o2.csv")] == [3.0, 2.0, 1.0]
    r = run("log_adapters.py", "--adapter", "csv", "--input", "log.json", "--metric-col", "val_AP", "--method", "m", "--units", "percent", "--out", "o3.csv", cwd=tmp_path)
    assert r.fails == 1 and "--adapter json" in r.out, r.out                                      # not "metric column '[' missing"


def test_bug04_units_none_keeps_values_and_records_none(tmp_path):
    write(tmp_path / "log.json", json.dumps([{"epoch": e, "loss": 4.0 - 0.5 * e} for e in range(6)]))
    r = run("log_adapters.py", "--adapter", "json", "--input", "log.json", "--metric-col", "loss", "--method", "m", "--units", "none", "--out", "o.csv", cwd=tmp_path)
    assert r.fails == 0 and "[WARN]" not in r.out, r.out                                          # no percent plausibility warning on a loss
    rows = _dicts(tmp_path / "o.csv")
    assert [float(x["value"]) for x in rows] == [4.0, 3.5, 3.0, 2.5, 2.0, 1.5] and {(x["units_in"], x["units_out"]) for x in rows} == {("none", "none")}


# ------------------------------------------------------------------ 5 / 6: inset and palette / legend (in process, on the figure)
def test_bug05_inset_is_refused_when_it_would_be_the_whole_curve(tmp_path, monkeypatch):
    _sparse_curves(tmp_path / "results" / "c.csv")
    fig, src, cap = _curves_in_process(monkeypatch, tmp_path, ["--csv", "results/c.csv", "--x", "epoch", "--y", "value", "--ylabel", "Loss", "--series", "method", "--ours", "ours", "--baseline", "base",
                                                               "--ema", "0.12", "--inset", "last:30", "--annotate", "last", "--out", "figures/c.png"])
    assert all(not ax.child_axes for ax in fig.axes)
    assert "inset and grey rectangle" not in cap


def test_bug05_inset_has_three_ticks_readable_labels_and_connectors_and_keeps_off_the_data(tmp_path, monkeypatch):
    _dense_loss(tmp_path / "results" / "l.csv")
    fig, src, cap = _curves_in_process(monkeypatch, tmp_path, ["--csv", "results/l.csv", "--x", "epoch", "--y", "value", "--ylabel", "Loss", "--series", "method", "--ours", "ours", "--baseline", "base",
                                                               "--ema", "0.12", "--inset", "last:30", "--annotate", "last", "--width-mm", "174.6", "--out", "figures/l.png"])
    ax = fig.axes[0]; ins = ax.child_axes[0]
    assert len(ins.get_xticks()) >= 3 and len(ins.get_yticks()) >= 3
    assert ins.xaxis.get_ticklabels()[0].get_fontsize() >= 6 and ins.yaxis.get_ticklabels()[0].get_fontsize() >= 6
    assert {c.__class__.__name__ for c in ax.get_children()} & {"InsetIndicator", "ConnectionPatch"}                  # zoom rectangle + connector lines to the inset
    assert not [m for sv, m in mf.audit_layout(fig) if "covers" in m], mf.audit_layout(fig)


def test_bug06_palette_hierarchy_one_row_legend_and_no_collision_with_the_end_labels(tmp_path, monkeypatch):
    rows = []
    names = ["RGB-only", "IR-only", "F2 Concat", "F6 SMM", "ours", "F6R +aug"]
    for i, m in enumerate(names):
        for sd in (0, 1):
            for e in range(40):
                rows.append([m, sd, e, round(2.0 + 0.2 * i + 3 * np.exp(-e / 10) + 0.01 * sd, 4)])
    _table(tmp_path / "results" / "l.csv", ["method", "seed", "epoch", "value"], rows)
    fig, src, cap = _curves_in_process(monkeypatch, tmp_path, ["--csv", "results/l.csv", "--x", "epoch", "--y", "value", "--ylabel", "Loss", "--series", "method", "--ours", "ours", "--baseline", "F6 SMM",
                                                               "--allow-code-labels",                      # "F2 Concat" / "F6R +aug" are family codes: the registry would name them, this test draws them as they are
                                                               "--ema", "0.12", "--annotate", "last", "--width-mm", "174.6", "--out", "figures/l.png"])
    ax = fig.axes[0]; leg = fig.legends[0] if fig.legends else ax.get_legend()
    hs = leg.legend_handles; labels = [t.get_text() for t in leg.get_texts()]
    assert not any("n=" in t for t in labels), labels                                          # n goes to the caption
    cols = {t: h.get_color() for t, h in zip(labels, hs)}
    assert cols["Ours"] == mf.ACCENT and hs[labels.index("Ours")].get_linewidth() >= 1.7        # an unregistered name is humanised ("ours" -> "Ours")
    assert labels[0] == "Ours"                                                                  # ours is first in the legend
    base = hs[labels.index("F6 SMM")]; assert base.get_linestyle() == "--" and base.get_linewidth() <= 1.0
    others = [cols[n] for n in names if n not in ("ours", "F6 SMM")]
    from figure_style import delta_e
    assert len(set(others)) == 4 and all(delta_e(a, b) >= 15 for i, a in enumerate(others) for b in others[i + 1:]) and all(delta_e(c, mf.ACCENT) >= 25 for c in others), others   # four clearly different colours, none near the accent
    if fig.legends: assert leg._ncols == len(labels)                                            # above the panels: one row (<= 6 series)
    fig.canvas.draw(); rend = fig.canvas.get_renderer(); lb = leg.get_window_extent(rend)
    for t in [t for t in ax.texts if t.get_gid() == "end-label"]:
        b = mf._text_bb(t, rend); assert not (lb.x0 < b.x1 and b.x0 < lb.x1 and lb.y0 < b.y1 and b.y0 < lb.y1), "legend covers an end label"
    assert "n = 2 seeds per series" in cap


def matplotlib_rgb(c):
    import matplotlib.colors as mc
    return mc.to_rgb(c)


def test_curves_raw_records_are_one_neutral_grey_and_x_starts_at_the_first_epoch(tmp_path, monkeypatch):
    _dense_loss(tmp_path / "results" / "l.csv")
    fig, src, cap = _curves_in_process(monkeypatch, tmp_path, ["--csv", "results/l.csv", "--x", "epoch", "--y", "value", "--ylabel", "Loss", "--series", "method", "--ours", "ours", "--baseline", "base",
                                                               "--ema", "0.12", "--annotate", "last", "--out", "figures/l.png"])
    ax = fig.axes[0]
    raw = [ln for ln in ax.lines if ln.get_alpha() is not None and ln.get_alpha() < 0.3]
    assert len(raw) == 2 and len({ln.get_color() for ln in raw}) == 1 and all(abs(ln.get_alpha() - 0.15) < 1e-9 for ln in raw)
    assert ax.get_xlim()[0] == 0                                                                  # first epoch, no negative padding


# ------------------------------------------------------------------ 14: caption with --band none
def test_bug14_band_none_with_seeds_does_not_say_single_run(tmp_path):
    _dense_loss(tmp_path / "results" / "l.csv")
    r = _curves(tmp_path, "results/l.csv", "--band", "none", "--out", "figures/l.png")
    assert r.returncode == 0, r.out
    cap = read(tmp_path / "figures.csv")
    assert "single run per series" not in cap and "n = 3 seeds per series" in cap


# ------------------------------------------------------------------ 7 / 8: tradeoff
def _eff(path):
    rows = [["A", "M3FD", 31.0, 2.6, 6.4], ["B", "M3FD", 36.0, 4.0, 9.5], ["C", "M3FD", 36.5, 4.4, 11.0], ["ours", "M3FD", 37.7, 5.2, 13.6],
            ["A", "LLVIP", 51.5, 2.6, 6.4], ["B", "LLVIP", 62.0, 4.0, 9.5], ["C", "LLVIP", 61.5, 4.4, 11.0], ["ours", "LLVIP", 62.1, 5.2, 13.6]]
    _table(path, ["method", "dataset", "AP", "params_M", "GFLOPs"], rows)


def test_bug07_tradeoff_size_legend_has_no_missing_glyph_and_no_raw_column_name(tmp_path):
    _eff(tmp_path / "results" / "eff.csv")
    r = run("make_motivation.py", "tradeoff", "--project", ".", "--csv", "results/eff.csv", "--x", "GFLOPs", "--y", "AP", "--label", "method", "--size", "params_M", "--ours", "ours", "--out", "figures/t.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "Glyph" not in r.out and "missing from" not in r.out, r.out
    spans, _ = _pdf_spans(tmp_path / "figures" / "t.pdf"); text = " ".join(sp["text"] for sp in spans)
    assert "∝" not in text and "params_M" not in text and "Params (M)" in text, text


def test_bug08_tradeoff_y_norm_per_color_puts_datasets_with_different_ranges_on_one_axis(tmp_path):
    _eff(tmp_path / "results" / "eff.csv")
    base = ["make_motivation.py", "tradeoff", "--project", ".", "--csv", "results/eff.csv", "--x", "GFLOPs", "--y", "AP", "--label", "method", "--color", "dataset", "--ours", "ours"]
    r = run(*base, "--out", "figures/t0.png", cwd=tmp_path)
    assert "disjoint AP ranges" in r.out and "--y-norm per-color" in r.out, r.out                 # the degenerate layout is called out
    r = run(*base, "--y-norm", "per-color", "--y-ref", "A", "--out", "figures/t1.png", cwd=tmp_path)
    assert r.returncode == 0 and "disjoint" not in r.out, r.out
    src = _dicts(tmp_path / "figures" / "t1.source.csv")
    ref = [s for s in src if s["method"] == "A"]
    assert {float(s["y_norm"]) for s in ref} == {0.0}                                             # the reference method is 0 in every group
    ours = {s["dataset"]: (float(s["AP"]), float(s["y_norm"])) for s in src if s["method"] == "ours"}
    assert ours["M3FD"] == (37.7, pytest.approx(6.7)) and ours["LLVIP"][1] == pytest.approx(10.6)   # raw AP kept next to the normalised one
    assert "gain over" in read(tmp_path / "figures.csv")
    assert "is on the front by construction" in r.out                                              # ours is the costliest model: say so


# ------------------------------------------------------------------ 9 / 15: grid box status, case collision
def _grid_world(tmp_path, extra_pred=""):
    from PIL import Image
    for m in ("GT", "base"):
        os.makedirs(tmp_path / "imgs" / m, exist_ok=True); Image.new("RGB", (64, 48), (90, 120, 150)).save(tmp_path / "imgs" / m / "s1.png")
        os.makedirs(tmp_path / "lab" / m, exist_ok=True)
    write(tmp_path / "lab" / "GT" / "s1.txt", "0 0.30 0.40 0.20 0.30\n0 0.75 0.60 0.20 0.30\n")                      # two ground-truth boxes
    write(tmp_path / "lab" / "base" / "s1.txt", "0 0.30 0.40 0.20 0.30 0.9\n0 0.60 0.20 0.10 0.10 0.8\n" + extra_pred)  # one TP, one FP; the second GT box is missed


def test_bug09_grid_box_status_counts_tp_fp_fn_and_draws_a_legend(tmp_path):
    _grid_world(tmp_path)
    r = run("make_comparison.py", "grid", "--root", "imgs", "--methods", "GT,base", "--samples", "s1", "--labels-dir", "lab", "--box-status", "--out", "figures/g.png", "--width-mm", "100", "--project", ".", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "box status (IoU >= 0.5, class-aware; per method TP/FP/FN): base 1/1/1" in r.out, r.out
    cap = read(tmp_path / "figures.csv")
    assert "green solid = true positive" in cap and "dashed = false positive" in cap and "dotted = missed" in cap     # the colour of the false-positive boxes is the style registry's (orange), not "red" any more
    spans, _ = _pdf_spans(tmp_path / "figures" / "g.pdf"); text = " ".join(sp["text"] for sp in spans)
    assert "TP (IoU >= 0.5)" in text and "FN (missed ground truth)" in text                        # legend strip in the vector layer


def test_bug09_grid_min_score_drops_low_confidence_boxes(tmp_path):
    _grid_world(tmp_path, extra_pred="0 0.10 0.10 0.10 0.10 0.2\n")
    r = run("make_comparison.py", "grid", "--root", "imgs", "--methods", "GT,base", "--samples", "s1", "--labels-dir", "lab", "--box-status", "--min-score", "0.5", "--out", "figures/g.png", "--width-mm", "100", "--project", ".", cwd=tmp_path)
    assert "base 1/1/1" in r.out, r.out                                                              # the 0.2 box is gone: still 1 TP / 1 FP / 1 FN


def test_bug15_grid_refuses_method_directories_that_differ_only_by_case(tmp_path):
    _grid_world(tmp_path)
    r = run("make_comparison.py", "grid", "--root", "imgs", "--methods", "base,BASE", "--samples", "s1", "--out", "figures/g.png", "--width-mm", "100", "--project", ".", cwd=tmp_path)
    assert r.returncode != 0 and "differ only by case" in r.out, r.out


# ------------------------------------------------------------------ 10: default width from the venue, registered width = PDF width
def test_bug10_default_width_comes_from_the_venue_and_the_registered_width_is_the_pdfs(tmp_path):
    write(tmp_path / "research-state.yaml", 'target:\n  venue: "CVPR 2027"\n  family: "cs_conf"\n')
    _dense_loss(tmp_path / "results" / "l.csv")
    r = _curves(tmp_path, "results/l.csv", "--ours", "ours", "--out", "figures/l.png")
    assert r.returncode == 0, r.out
    assert "--width-mm not given, 174.6 mm from state.target.venue CVPR 2027" in r.out, r.out
    _, pdf_mm = _pdf_spans(tmp_path / "figures" / "l.pdf")
    reg = float(_dicts(tmp_path / "figures.csv")[-1]["print_width_mm"])
    assert abs(reg - pdf_mm) < 0.06, (reg, pdf_mm)                                                 # bbox-tight pdf was 178.2 mm for a registered 174.6
    _table(tmp_path / "results" / "d.csv", ["dataset", "dAP"], [["A", 1.0], ["B", -0.5], ["C", 0.3]])
    r = run("make_figure.py", "hbar", "--project", ".", "--csv", "results/d.csv", "--value", "dAP", "--group", "dataset", "--out", "figures/h.png", cwd=tmp_path)
    assert "82.5 mm from state.target.venue" in r.out, r.out                                         # one-column figures get the column width
    write(tmp_path / "research-state.yaml", "target:\n  venue: \"\"\n")
    r = run("make_figure.py", "hbar", "--project", ".", "--csv", "results/d.csv", "--value", "dAP", "--group", "dataset", "--out", "figures/h2.png", cwd=tmp_path)
    assert "--width-mm not given" not in r.out                                                      # unknown venue: the historical default, no claim about a venue


# ------------------------------------------------------------------ 11: make_architecture
torch = pytest.importorskip("torch")

ARCH_MODEL = '''import torch, torch.nn as nn


class M(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(nn.Conv2d(3, 4, 3, padding=1), nn.ReLU())
        self.fuse_block = nn.Conv2d(4, 4, 1)

    def forward(self, x):
        return self.fuse_block(self.layers(x))
'''


def test_bug11_default_stage_names_are_humanised_and_a_failed_import_is_not_a_figure_fail(tmp_path):
    write(tmp_path / "code" / "m.py", ARCH_MODEL)
    r = run("make_architecture.py", "trace", "--project", ".", "--model", "code/m.py:M", "--input", "x:1x3x8x8", "--depth", "1", "--out", "figures/arch/m.yaml", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    import yaml
    sp = yaml.safe_load(io.open(tmp_path / "figures" / "arch" / "m.yaml", encoding="utf-8"))
    stages = {n["stage"] for n in sp["nodes"] if n["kind"] == "module"}
    assert stages == {"Layers", "Fuse block"} and "layers" not in stages and "fuse_block" not in stages, stages
    assert "default stage name(s) ['Layers']" in r.out and "--stages" in r.out                       # 'layers' is a code name: say so
    write(tmp_path / "code" / "m.py", "import a_package_that_is_not_installed_zz\n" + ARCH_MODEL)   # the checking interpreter lacks the model's dependency
    r = run("make_architecture.py", "check", "--project", ".", "--spec", "figures/arch/m.yaml", cwd=tmp_path)
    assert r.fails == 0 and r.returncode == 0, r.out
    assert "interpreter cannot import the model's dependencies" in r.out and "图是不是从已不存在的代码画的" not in r.out, r.out


# ------------------------------------------------------------------ 12: figure_plan add / drop
PLAN_HDR = "item,kind,role,claim_ids,form_reason,generator,files,width,panels,page_hint,exemplar,exemplar_caption,thumb,status,note\n"


def _plan_project(tmp_path):
    write(tmp_path / "paper" / "figure_plan.csv", PLAN_HDR + "Fig 1,figure,method,,overview,gen,figures/fig_arch,double,1,p3,,,,planned,\nFig 2,figure,ablation,C1,delta plot,gen,figures/fig_abl,double,1,p7,,,,planned,\n")
    write(tmp_path / "paper" / "claims.csv", "claim_id,statement,evidence_key,expected,table_or_figure\nC1,Removing the gate lowers AP by 1.0,k,1.0,Fig 2\nC2,Ours beats the baseline on qualitative cases,k,,\n")
    write(tmp_path / "figures.csv", "file,print_width_mm,source_data,inspected,issues\nfigures/fig_arch.png,174.6,figures/fig_arch.source.csv,yes,\nfigures/fig_cam.png,174.6,figures/fig_cam.source.csv,yes,\n")


def test_bug12_figure_plan_add_and_drop_edit_the_plan_without_hand_editing(tmp_path):
    _plan_project(tmp_path)
    r = run("figure_plan.py", "drop", "--project", ".", "--item", "Fig 2", "--reason", "no seeds, the ablation is a table only", cwd=tmp_path)
    assert r.fails == 0 and "dropped" in r.out, r.out
    rows = _dicts(tmp_path / "paper" / "figure_plan.csv"); f2 = [x for x in rows if x["item"] == "Fig 2"][0]
    assert f2["status"] == "dropped" and f2["note"] == "no seeds, the ablation is a table only"
    r = run("figure_plan.py", "drop", "--project", ".", "--item", "Fig 9", "--reason", "x", cwd=tmp_path)
    assert r.fails == 1 and "没有 'Fig 9'" in r.out, r.out
    r = run("figure_plan.py", "add", "--project", ".", "--role", "qualitative", "--claim", "C2", "--files", "figures/fig_cam", "--generator", "make_comparison.py grid ...", cwd=tmp_path)
    assert r.fails == 0 and "Fig 3 (qualitative, figure)" in r.out, r.out
    rows = _dicts(tmp_path / "paper" / "figure_plan.csv"); f3 = rows[-1]
    assert (f3["item"], f3["role"], f3["claim_ids"], f3["status"]) == ("Fig 3", "qualitative", "C2", "done")      # fig_cam.png is already in figures.csv
    assert "Fig 3" in read(tmp_path / "paper" / "figure_plan.md")
    r = run("figure_plan.py", "add", "--project", ".", "--role", "qualitative", "--claim", "C99", cwd=tmp_path)
    assert r.fails == 1 and "C99" in r.out, r.out
    r = run("figure_plan.py", "add", "--project", ".", "--item", "Fig 3", "--role", "analysis", cwd=tmp_path)
    assert r.fails == 1 and "已在计划里" in r.out, r.out
    r = run("figure_plan.py", "check", "--project", ".", cwd=tmp_path)
    assert "未计划的图" not in r.out and "还没画" not in r.out, r.out                                   # the planner no longer complains about the added / dropped rows
