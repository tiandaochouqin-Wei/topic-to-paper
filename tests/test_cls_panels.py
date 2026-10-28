# -*- coding: utf-8 -*-
"""classification / agreement panels of make_figure.py (roc, pr, confusion, calibration, bland-altman) and the synthetic-data watermark
that finish() applies to every figure. Hand-computed values on tiny inputs; every PDF must be vector."""
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


def _pdf_text(path):
    import fitz
    doc = fitz.open(str(path)); t = "".join(p.get_text() for p in doc); doc.close()
    return t


def _issues(root, out):
    return [r["issues"] for r in csv.DictReader(io.open(root / "figures.csv", encoding="utf-8-sig")) if r["file"] == out][0]


# toy: positives {0.9, 0.65, 0.35}, negatives {0.8, 0.4, 0.1} -> 6 of 9 (pos, neg) pairs ordered correctly
TOY = [(0, 0.1), (0, 0.4), (1, 0.35), (0, 0.8), (1, 0.65), (1, 0.9)]


def _preds(path, seed=0, n=60, groups=(("ours", 1.6), ("base", 0.9)), folder="results"):
    rng = np.random.default_rng(seed); rows = []
    for g, d in groups:
        for _ in range(n):
            y = int(rng.random() < 0.4); rows.append([g, y, round(float(rng.normal(d * y, 1.0)), 4)])
    _table(path, ["method", "label", "score"], rows)
    return rows


# ------------------------------------------------------------------ pure functions
def test_auc_and_average_precision_hand_values():
    y = np.array([t[0] for t in TOY]); s = np.array([t[1] for t in TOY])
    assert abs(mf.auc_score(y, s) - 6 / 9) < 1e-12
    assert abs(mf.average_precision(y, s) - (1 + 2 / 3 + 3 / 5) / 3) < 1e-12           # precision at each positive: 1/1, 2/3, 3/5
    assert abs(mf.auc_score(y, -s) - 3 / 9) < 1e-12                                       # reversed ranking
    assert mf.auc_score(np.array([0, 1]), np.array([0.5, 0.5])) == 0.5                    # a full tie is chance, not 0 or 1


def test_auc_ties_count_half_a_pair():
    y = np.array([1, 1, 0, 0]); s = np.array([0.9, 0.5, 0.5, 0.1])                       # pairs: (.9,.5)=1 (.9,.1)=1 (.5,.5)=.5 (.5,.1)=1
    assert abs(mf.auc_score(y, s) - 3.5 / 4) < 1e-12


def test_ece_with_known_bins_and_t_quantile():
    p = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9]); y = np.array([0, 0, 0, 0, 1, 1, 1, 1.0])
    assert abs(mf.ece_score(p, y, 2, "uniform") - 0.25) < 1e-12                            # |0 - .25| and |1 - .75| in two equal bins
    bs = mf.calib_bins(p, y, 2, "uniform"); assert [b[2] for b in bs] == [4, 4] and abs(bs[0][3] - 0.25) < 1e-12
    assert abs(mf.t_crit(10) - 2.228) < 0.01 and abs(mf.t_crit(1000) - 1.962) < 0.003


def test_bland_altman_statistics():
    A = np.array([10, 12, 14, 16, 18, 20.0]); B = np.array([9, 11, 15, 15, 17, 21.0]); st = mf.ba_stats(A, B)
    sd = np.sqrt(((np.array([1, 1, -1, 1, 1, -1.0]) - 1 / 3) ** 2).sum() / 5)
    assert abs(st["bias"] - 1 / 3) < 1e-12 and abs(st["sd"] - sd) < 1e-12 and abs(st["hi"] - (1 / 3 + 1.96 * sd)) < 1e-12 and abs(st["lo"] - (1 / 3 - 1.96 * sd)) < 1e-12
    assert not st["prop"]
    st2 = mf.ba_stats(1.2 * B, B)                                                           # difference = 0.2 B, mean = 1.1 B -> slope 0.2 / 1.1
    assert abs(st2["slope"] - 0.2 / 1.1) < 1e-9 and st2["prop"]


# ------------------------------------------------------------------ roc / pr
def test_roc_toy_csv_summary_row_and_vector_pdf(tmp_path):
    _table(tmp_path / "results" / "toy.csv", ["label", "score"], TOY)
    r = run("make_figure.py", "roc", "--csv", "results/toy.csv", "--y-true", "label", "--score", "score", "--out", "figures/fig_roc.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "[WARN] roc: group 'all' n_pos=3, n_neg=3 (< 10)" in r.out and "AUC unstable" in r.out
    src = _outputs(tmp_path, "figures/fig_roc.png"); summ = [s for s in src if s["kind"] == "summary"]
    assert len(summ) == 1 and abs(float(summ[0]["auc"]) - 6 / 9) < 1e-9 and summ[0]["n_pos"] == "3" and summ[0]["n_neg"] == "3" and summ[0]["ci_lo"] == ""
    curve = [(float(s["fpr"]), float(s["tpr"])) for s in src if s["kind"] == "curve"]
    assert curve[0] == (0.0, 0.0) and curve[-1] == (1.0, 1.0)
    assert "AUC 0.667" in _pdf_text(tmp_path / "figures" / "fig_roc.pdf")


def test_roc_groups_ci_and_ours(tmp_path):
    _preds(tmp_path / "results" / "p.csv")
    r = run("make_figure.py", "roc", "--csv", "results/p.csv", "--y-true", "label", "--score", "score", "--group", "method", "--ours", "ours", "--ci", "bootstrap:50",
            "--out", "figures/fig_roc.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    src = _outputs(tmp_path, "figures/fig_roc.png"); summ = {s["group"]: s for s in src if s["kind"] == "summary"}
    assert set(summ) == {"ours", "base"}
    for s in summ.values():
        assert float(s["ci_lo"]) < float(s["auc"]) < float(s["ci_hi"]) and int(s["n_pos"]) + int(s["n_neg"]) == 60
    assert float(summ["ours"]["auc"]) > float(summ["base"]["auc"])
    assert any(s["kind"] == "band" for s in src) and "bootstrap" in _issues(tmp_path, "figures/fig_roc.png")
    assert "[" in _pdf_text(tmp_path / "figures" / "fig_roc.pdf")                         # AUC [lo, hi] in the legend


def test_roc_bootstrap_is_deterministic_for_a_seed(tmp_path):
    _preds(tmp_path / "results" / "p.csv")
    def go(seed, out):
        r = run("make_figure.py", "roc", "--csv", "results/p.csv", "--y-true", "label", "--score", "score", "--group", "method", "--ci", "bootstrap:40", "--seed", seed, "--out", out, cwd=tmp_path)
        assert r.returncode == 0, r.out
        return read(tmp_path / out.replace(".png", ".source.csv"))
    a1, a2, b = go(3, "figures/a1.png"), go(3, "figures/a2.png"), go(4, "figures/b.png")
    assert a1 == a2 and a1 != b


def test_roc_refuses_a_one_class_group_and_bad_input(tmp_path):
    _table(tmp_path / "results" / "p.csv", ["method", "label", "score"], [["a", 1, 0.5], ["a", 1, 0.6], ["b", 0, 0.1], ["b", 1, 0.9]])
    r = run("make_figure.py", "roc", "--csv", "results/p.csv", "--y-true", "label", "--score", "score", "--group", "method", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "only one class" in r.out and "'a'" in r.out, r.out
    assert not os.path.exists(tmp_path / "figures" / "f.pdf")
    _table(tmp_path / "results" / "q.csv", ["label", "score"], [[2, 0.5], [0, 0.1]])
    r = run("make_figure.py", "roc", "--csv", "results/q.csv", "--y-true", "label", "--score", "score", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "not binary" in r.out, r.out
    r = run("make_figure.py", "roc", "--csv", "results/p.csv", "--y-true", "label", "--score", "score", "--group", "method", "--ci", "jackknife:10", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "--ci" in r.out, r.out
    r = run("make_figure.py", "roc", "--csv", "results/p.csv", "--y-true", "nope", "--score", "score", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "nope" in r.out, r.out


def test_pr_average_precision_prevalence_and_ci(tmp_path):
    _table(tmp_path / "results" / "toy.csv", ["label", "score"], TOY)
    r = run("make_figure.py", "pr", "--csv", "results/toy.csv", "--y-true", "label", "--score", "score", "--out", "figures/fig_pr.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    src = _outputs(tmp_path, "figures/fig_pr.png"); summ = [s for s in src if s["kind"] == "summary"][0]
    assert abs(float(summ["ap"]) - (1 + 2 / 3 + 3 / 5) / 3) < 1e-9
    txt = _pdf_text(tmp_path / "figures" / "fig_pr.pdf"); assert "AP 0.756" in txt and "prevalence 0.50" in txt
    _preds(tmp_path / "results" / "p.csv")
    r = run("make_figure.py", "pr", "--csv", "results/p.csv", "--y-true", "label", "--score", "score", "--group", "method", "--ci", "bootstrap:30", "--out", "figures/fig_pr2.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    summ = {s["group"]: s for s in _outputs(tmp_path, "figures/fig_pr2.png") if s["kind"] == "summary"}
    assert float(summ["ours"]["ci_lo"]) <= float(summ["ours"]["ap"]) <= float(summ["ours"]["ci_hi"]) + 1e-9


# ------------------------------------------------------------------ confusion
def test_confusion_long_rows_counts_percentages_and_per_class_rows(tmp_path):
    pairs = [("cat", "cat")] * 8 + [("cat", "dog")] * 2 + [("dog", "dog")] * 5 + [("dog", "cat")] * 5 + [("bird", "bird")] * 4
    _table(tmp_path / "results" / "c.csv", ["y", "p"], pairs)
    r = run("make_figure.py", "confusion", "--csv", "results/c.csv", "--true-col", "y", "--pred-col", "p", "--labels", "cat,dog,bird", "--out", "figures/fig_cm.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    src = _outputs(tmp_path, "figures/fig_cm.png"); cell = {(s["true"], s["pred"]): s for s in src if s["kind"] == "cell"}
    assert cell[("cat", "dog")]["count"] == "2" and abs(float(cell[("cat", "dog")]["row_pct"]) - 20.0) < 1e-9 and abs(float(cell[("dog", "cat")]["row_pct"]) - 50.0) < 1e-9
    cls = {s["true"]: s for s in src if s["kind"] == "class"}
    assert abs(float(cls["cat"]["recall"]) - 0.8) < 1e-9 and abs(float(cls["cat"]["precision"]) - 8 / 13) < 1e-9 and cls["dog"]["support"] == "10" and float(cls["bird"]["recall"]) == 1.0
    acc = [s for s in src if s["kind"] == "accuracy"][0]; assert abs(float(acc["recall"]) - 17 / 24) < 1e-9
    txt = _pdf_text(tmp_path / "figures" / "fig_cm.pdf"); assert "80.0%" in txt and "20.0%" in txt and "cat" in txt and "Predicted" in txt
    assert "[WARN] confusion: recall below 0.5" not in r.out


def test_confusion_matrix_table_labels_and_errors(tmp_path):
    write(tmp_path / "results" / "m.csv", ",a,b\na,9,1\nb,3,7\n")
    r = run("make_figure.py", "confusion", "--csv", "results/m.csv", "--matrix", "--normalize", "none", "--out", "figures/fig_m.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    src = _outputs(tmp_path, "figures/fig_m.png"); cls = {s["true"]: s for s in src if s["kind"] == "class"}
    assert abs(float(cls["a"]["recall"]) - 0.9) < 1e-9 and abs(float(cls["b"]["precision"]) - 7 / 8) < 1e-9
    write(tmp_path / "results" / "n.csv", "1,2,3\n4,5,6\n")                                  # not square
    r = run("make_figure.py", "confusion", "--csv", "results/n.csv", "--matrix", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "square" in r.out, r.out
    _table(tmp_path / "results" / "c.csv", ["y", "p"], [("a", "a"), ("a", "z"), ("b", "b")])
    r = run("make_figure.py", "confusion", "--csv", "results/c.csv", "--true-col", "y", "--pred-col", "p", "--labels", "a,b", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "'z'" in r.out, r.out
    r = run("make_figure.py", "confusion", "--csv", "results/c.csv", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "--true-col" in r.out, r.out


def test_confusion_warns_on_weak_recall_and_empty_true_row(tmp_path):
    _table(tmp_path / "results" / "c.csv", ["y", "p"], [("a", "b")] * 3 + [("a", "a")] + [("b", "b")] * 4)
    r = run("make_figure.py", "confusion", "--csv", "results/c.csv", "--true-col", "y", "--pred-col", "p", "--labels", "a,b,c", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed and "recall below 0.5 for ['a']" in r.out, r.out        # class c has no true samples: recall n/a, no crash
    cls = {s["true"]: s for s in _outputs(tmp_path, "figures/f.png") if s["kind"] == "class"}
    assert cls["c"]["recall"] == "" and cls["c"]["precision"] == "" and cls["c"]["support"] == "0"


# ------------------------------------------------------------------ calibration
def test_calibration_ece_brier_hollow_bins_and_two_axes(tmp_path):
    p = [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9]; y = [0, 0, 0, 0, 1, 1, 1, 1]
    _table(tmp_path / "results" / "k.csv", ["label", "prob"], list(zip(y, p)))
    r = run("make_figure.py", "calibration", "--csv", "results/k.csv", "--y-true", "label", "--prob", "prob", "--bins", "2", "--strategy", "uniform", "--out", "figures/fig_cal.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "ECE 0.2500" in r.out and "Brier 0.0750" in r.out and "only 8 samples" in r.out
    src = _outputs(tmp_path, "figures/fig_cal.png"); bins = [s for s in src if s["kind"] == "bin"]; summ = [s for s in src if s["kind"] == "summary"][0]
    assert len(bins) == 2 and [b["n"] for b in bins] == ["4", "4"] and abs(float(bins[0]["mean_conf"]) - 0.25) < 1e-9 and float(bins[1]["obs_freq"]) == 1.0
    assert abs(float(summ["ece"]) - 0.25) < 1e-9 and abs(float(summ["brier"]) - 0.075) < 1e-9
    txt = _pdf_text(tmp_path / "figures" / "fig_cal.pdf"); assert "ECE 0.250" in txt and "bin with n < 5" in txt and "Count" in txt   # n = 4 < 5: hollow markers + legend key


def test_calibration_groups_quantile_bins_and_errors(tmp_path):
    rng = np.random.default_rng(2); rows = []
    for g, k in (("ours", 1.0), ("base", 0.6)):
        for _ in range(300):
            pr = float(rng.random()); rows.append([g, int(rng.random() < pr ** k), round(pr, 5)])
    _table(tmp_path / "results" / "k.csv", ["method", "label", "prob"], rows)
    r = run("make_figure.py", "calibration", "--csv", "results/k.csv", "--y-true", "label", "--prob", "prob", "--group", "method", "--ours", "ours", "--out", "figures/fig_cal.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    src = _outputs(tmp_path, "figures/fig_cal.png"); ece = {s["group"]: float(s["ece"]) for s in src if s["kind"] == "summary"}
    assert ece["ours"] < ece["base"] and all(len([b for b in src if b["kind"] == "bin" and b["group"] == g]) == 10 for g in ece)   # quantile bins: ten equal-count bins
    assert all(b["n"] == "30" for b in src if b["kind"] == "bin")
    _table(tmp_path / "results" / "bad.csv", ["label", "prob"], [(0, 0.2), (1, 3.5)])
    r = run("make_figure.py", "calibration", "--csv", "results/bad.csv", "--y-true", "label", "--prob", "prob", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "outside [0, 1]" in r.out, r.out
    r = run("make_figure.py", "calibration", "--csv", "results/k.csv", "--y-true", "label", "--prob", "prob", "--bins", "1", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "--bins" in r.out, r.out


# ------------------------------------------------------------------ bland-altman
def test_bland_altman_numbers_in_source_and_on_the_figure(tmp_path):
    A = [10, 12, 14, 16, 18, 20]; B = [9, 11, 15, 15, 17, 21]
    _table(tmp_path / "results" / "ba.csv", ["measA", "measB"], list(zip(A, B)))
    r = run("make_figure.py", "bland-altman", "--csv", "results/ba.csv", "--a", "measA", "--b", "measB", "--unit", "HU", "--out", "figures/fig_ba.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "n=6" in r.out and "bias +0.3333 HU" in r.out and "n=6 < 30" in r.out
    src = _outputs(tmp_path, "figures/fig_ba.png"); summ = [s for s in src if s["kind"] == "summary"][0]; sd = float(np.std([1, 1, -1, 1, 1, -1], ddof=1))
    assert abs(float(summ["bias"]) - 1 / 3) < 1e-9 and abs(float(summ["loa_hi"]) - (1 / 3 + 1.96 * sd)) < 1e-9 and summ["proportional_bias"] == "False"
    assert len([s for s in src if s["kind"] == "point"]) == 6
    txt = _pdf_text(tmp_path / "figures" / "fig_ba.pdf"); assert "bias +0.33 HU" in txt.replace("−", "-") and "+1.96 SD" in txt


def test_bland_altman_proportional_bias_and_groups(tmp_path):
    rng = np.random.default_rng(5); rows = []
    for g, off in (("lung", 0.0), ("liver", 30.0)):
        for _ in range(40):
            b = float(rng.uniform(20, 120)) + off; rows.append([g, round(1.15 * b + rng.normal(0, 2), 3), round(b, 3)])
    _table(tmp_path / "results" / "ba.csv", ["dataset", "measA", "measB"], rows)
    r = run("make_figure.py", "bland-altman", "--csv", "results/ba.csv", "--a", "measA", "--b", "measB", "--group", "dataset", "--out", "figures/fig_ba.png", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed and "proportional bias" in r.out, r.out
    src = _outputs(tmp_path, "figures/fig_ba.png"); summ = {s["group"]: s for s in src if s["kind"] == "summary"}
    assert set(summ) == {"lung", "liver", "all"} and summ["all"]["proportional_bias"] == "True"
    assert float(summ["all"]["slope_lo"]) > 0.05 and float(summ["all"]["slope_lo"]) < float(summ["all"]["slope"]) < float(summ["all"]["slope_hi"])
    assert "slope" in _pdf_text(tmp_path / "figures" / "fig_ba.pdf")


def test_bland_altman_errors(tmp_path):
    _table(tmp_path / "results" / "ba.csv", ["a", "b"], [(1, 2), (2, 3)])
    r = run("make_figure.py", "bland-altman", "--csv", "results/ba.csv", "--a", "a", "--b", "b", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "at least 3" in r.out, r.out
    r = run("make_figure.py", "bland-altman", "--csv", "results/ba.csv", "--a", "a", "--b", "zz", "--out", "figures/f.png", cwd=tmp_path)
    assert r.returncode == 1 and not r.crashed and "zz" in r.out, r.out


# ------------------------------------------------------------------ synthetic watermark
MARK = "SYNTHETIC DEMO"


def _roc(tmp_path, csv_rel, *extra, project=".", out="figures/fig_w.png"):
    return run("make_figure.py", "roc", "--project", project, "--csv", csv_rel, "--y-true", "label", "--score", "score", "--out", out, *extra, cwd=tmp_path)


def test_data_under_results_is_not_watermarked(tmp_path):
    _preds(tmp_path / "results" / "p.csv", groups=(("a", 1.2),))
    r = _roc(tmp_path, "results/p.csv")
    assert r.returncode == 0 and "[WARN] figure" not in r.out, r.out
    _outputs(tmp_path, "figures/fig_w.png")
    assert MARK not in _pdf_text(tmp_path / "figures" / "fig_w.pdf") and "synthetic" not in _issues(tmp_path, "figures/fig_w.png")


def test_data_inside_project_but_outside_results_only_warns(tmp_path):
    _preds(tmp_path / "scratch" / "p.csv", groups=(("a", 1.2),))
    r = _roc(tmp_path, "scratch/p.csv")
    assert r.returncode == 0 and "[WARN] figure: 数据 scratch/p.csv 在项目内但不在 results/ 或 runs/ 下，来源未核" in r.out, r.out
    assert MARK not in _pdf_text(tmp_path / "figures" / "fig_w.pdf") and "synthetic" not in _issues(tmp_path, "figures/fig_w.png")


@pytest.mark.parametrize("rel", ["results/figdemo.csv", "results/fake_preds.csv", "demo/p.csv"])
def test_synthetic_file_name_gets_the_watermark(tmp_path, rel):
    _preds(tmp_path / rel, groups=(("a", 1.2),))
    r = _roc(tmp_path, rel)
    assert r.returncode == 0 and "[WARN] figure:" in r.out and "按合成数据加水印" in r.out, r.out
    assert MARK in _pdf_text(tmp_path / "figures" / "fig_w.pdf") and _issues(tmp_path, "figures/fig_w.png").endswith("| synthetic")
    _vector(tmp_path / "figures" / "fig_w.pdf")


def test_demographics_in_a_file_name_is_not_a_demo(tmp_path):
    _preds(tmp_path / "results" / "demographics_preds.csv", groups=(("a", 1.2),))
    r = _roc(tmp_path, "results/demographics_preds.csv")
    assert r.returncode == 0 and MARK not in _pdf_text(tmp_path / "figures" / "fig_w.pdf"), r.out


def test_synthetic_header_or_comment_gets_the_watermark(tmp_path):
    rows = [["a", 1, 0.9], ["a", 0, 0.1]] * 6
    _table(tmp_path / "results" / "h.csv", ["method", "label", "score_synthetic"], rows)
    r = run("make_figure.py", "roc", "--csv", "results/h.csv", "--y-true", "label", "--score", "score_synthetic", "--out", "figures/h.png", cwd=tmp_path)
    assert r.returncode == 0 and "表头 / 注释含" in r.out and MARK in _pdf_text(tmp_path / "figures" / "h.pdf"), r.out
    write(tmp_path / "results" / "c.csv", "# SYNTHETIC toy data, not a measurement\nlabel,score\n" + "\n".join(f"{y},{s}" for y, s in TOY * 2) + "\n")
    r = run("make_figure.py", "roc", "--csv", "results/c.csv", "--y-true", "label", "--score", "score", "--out", "figures/c.png", cwd=tmp_path)
    assert r.returncode == 0 and MARK in _pdf_text(tmp_path / "figures" / "c.pdf"), r.out


def test_synthetic_flag_and_data_outside_the_project(tmp_path):
    _preds(tmp_path / "results" / "p.csv", groups=(("a", 1.2),))
    r = _roc(tmp_path, "results/p.csv", "--synthetic")
    assert r.returncode == 0 and MARK in _pdf_text(tmp_path / "figures" / "fig_w.pdf"), r.out
    proj = tmp_path / "proj"; os.makedirs(proj)
    _preds(tmp_path / "elsewhere" / "p.csv", groups=(("a", 1.2),))
    r = run("make_figure.py", "roc", "--project", str(proj), "--csv", str(tmp_path / "elsewhere" / "p.csv"), "--y-true", "label", "--score", "score", "--out", "figures/o.png", cwd=tmp_path)
    assert r.returncode == 0 and "[WARN] figure: 数据不在 results/ 或 runs/ 下，按合成数据加水印" in r.out, r.out
    assert MARK in _pdf_text(proj / "figures" / "o.pdf") and _issues(proj, "figures/o.png").endswith("| synthetic")


def test_no_watermark_check_skips_the_rule_but_says_so(tmp_path):
    proj = tmp_path / "proj"; os.makedirs(proj)
    _preds(tmp_path / "elsewhere" / "p.csv", groups=(("a", 1.2),))
    r = run("make_figure.py", "roc", "--project", str(proj), "--csv", str(tmp_path / "elsewhere" / "p.csv"), "--y-true", "label", "--score", "score", "--no-watermark-check", "--out", "figures/o.png", cwd=tmp_path)
    assert r.returncode == 0 and "[WARN] figure: --no-watermark-check" in r.out, r.out
    assert MARK not in _pdf_text(proj / "figures" / "o.pdf") and _issues(proj, "figures/o.png").endswith("| provenance-unchecked")


def test_every_subcommand_inherits_the_watermark(tmp_path):
    _preds(tmp_path / "results" / "p.csv", groups=(("a", 1.2),)); _table(tmp_path / "results" / "c.csv", ["y", "p"], [("a", "a"), ("a", "b"), ("b", "b")])
    _table(tmp_path / "results" / "k.csv", ["label", "prob"], [(0, 0.2), (1, 0.8), (0, 0.4), (1, 0.6)]); _table(tmp_path / "results" / "ba.csv", ["a", "b"], [(1, 1.1), (2, 1.9), (3, 3.2), (4, 4.1)])
    _table(tmp_path / "results" / "cv.csv", ["epoch", "AP", "method"], [(1, 1, "m"), (2, 3, "m"), (3, 4, "m")])
    cmds = {"pr": ["--y-true", "label", "--score", "score", "--csv", "results/p.csv"], "confusion": ["--true-col", "y", "--pred-col", "p", "--csv", "results/c.csv"],
            "calibration": ["--y-true", "label", "--prob", "prob", "--csv", "results/k.csv"], "bland-altman": ["--a", "a", "--b", "b", "--csv", "results/ba.csv"],
            "curves": ["--x", "epoch", "--y", "AP", "--series", "method", "--csv", "results/cv.csv"]}
    for name, args in cmds.items():
        r = run("make_figure.py", name, *args, "--synthetic", "--out", f"figures/{name}.png", cwd=tmp_path)
        assert r.returncode == 0 and not r.crashed, (name, r.out)
        assert MARK in _pdf_text(tmp_path / "figures" / f"{name}.pdf"), name
    # the same figures without the flag carry no mark
    r = run("make_figure.py", "confusion", *cmds["confusion"], "--out", "figures/plain.png", cwd=tmp_path)
    assert r.returncode == 0 and MARK not in _pdf_text(tmp_path / "figures" / "plain.pdf")


def test_make_motivation_inherits_the_watermark(tmp_path):
    rows = [[s, x, round(10 + 3 * x + k, 3)] for s, k in (("A", 0), ("B", 1.5)) for x in (0.1, 0.4, 0.7, 1.0)]
    _table(tmp_path / "results" / "cond.csv", ["method", "level", "AP"], rows)
    base = ["make_motivation.py", "condition", "--csv", "results/cond.csv", "--x", "level", "--y", "AP", "--series", "method", "--out"]
    r = run(*base, "figures/m1.png", "--synthetic", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    assert MARK in _pdf_text(tmp_path / "figures" / "m1.pdf") and _issues(tmp_path, "figures/m1.png").endswith("| synthetic")
    r = run(*base, "figures/m2.png", cwd=tmp_path)
    assert r.returncode == 0 and MARK not in _pdf_text(tmp_path / "figures" / "m2.pdf"), r.out
    r = run(*base, "figures/m3.png", "--no-watermark-check", cwd=tmp_path)
    assert r.returncode == 0 and "--no-watermark-check" in r.out, r.out


def test_table_figures_from_state_results_are_checked_too(research):
    r = run("make_figure.py", "main", "--project", str(research), "--out", "figures/fig_main.png", cwd=research)
    assert r.returncode == 0 and not r.crashed, r.out
    assert "[WARN] figure" not in r.out and MARK not in _pdf_text(research / "figures" / "fig_main.pdf")      # results/main.csv is under results/
    r = run("make_figure.py", "main", "--project", str(research), "--synthetic", "--out", "figures/fig_main2.png", cwd=research)
    assert r.returncode == 0 and MARK in _pdf_text(research / "figures" / "fig_main2.pdf")


def test_no_literal_control_characters_in_the_new_code():
    for f in ("make_figure.py", "make_motivation.py"):
        s = open(SCRIPTS / f, encoding="utf-8").read()
        assert not [c for c in s if ord(c) < 32 and c not in "\n\r\t"], f
