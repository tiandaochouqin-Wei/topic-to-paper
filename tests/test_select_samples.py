# -*- coding: utf-8 -*-
"""select_samples.py — choose the frames that show the difference (round-3 figure review: every method looked the same on the chosen frames). Synthetic YOLO
ground truth / predictions where one image clearly favours ours, one favours a baseline (counter-example), a tie, a group quota and a typical image; CAM in-box share on
synthetic .npy maps; the meta file holds the rule and the global win / loss counts (no silent cherry-picking)."""
import csv
import io
import json
import sys

import numpy as np
import pytest

from conftest import SCRIPTS, read, run, write

sys.path.insert(0, str(SCRIPTS))

METHODS = "base1,base2,ours"


def box(k, score=None):
    """k-th object: non-overlapping 0.1 x 0.1 box; with a score it is a prediction line"""
    cx = 0.1 + 0.2 * k
    return f"0 {cx:.2f} 0.50 0.10 0.10" + ("" if score is None else f" {score}")


def _scene(tmp_path, spec):
    """spec: {image: {"gt": n_objects, "pred": {method: (k_hits, n_false_positives)}}}"""
    for img, d in spec.items():
        write(tmp_path / "gt" / f"{img}.txt", "\n".join(box(k) for k in range(d["gt"])) + "\n")
        for m, (hits, fps) in d["pred"].items():
            lines = [box(k, 0.9) for k in range(hits)] + [f"0 {0.05 + 0.1 * j:.2f} 0.90 0.06 0.06 0.8" for j in range(fps)]
            write(tmp_path / "pred" / m / f"{img}.txt", "\n".join(lines) + ("\n" if lines else ""))


SPEC = {   # image: gt objects, per method (true positives, false positives)
    "img01": {"gt": 2, "pred": {"base1": (0, 0), "base2": (1, 0), "ours": (2, 0)}},          # ours clearly better: score 2 (vs the stronger base2)
    "img02": {"gt": 1, "pred": {"base1": (1, 0), "base2": (1, 0), "ours": (1, 0)}},          # tie: 0
    "img03": {"gt": 3, "pred": {"base1": (3, 0), "base2": (0, 0), "ours": (1, 0)}},          # a baseline is clearly better: counter-example (-4)
    "img04": {"gt": 2, "pred": {"base1": (2, 3), "base2": (1, 0), "ours": (2, 0)}},          # ours has no false positives where base1 has 3: 1.5
    "img05": {"gt": 1, "pred": {"base1": (0, 0), "base2": (0, 0), "ours": (1, 0)}},          # score 2, one object
}


def _sel(tmp_path, *extra, spec=SPEC, out="samples.csv", mode="det"):
    _scene(tmp_path, spec)
    return run("select_samples.py", mode, "--gt-dir", tmp_path / "gt", "--pred-dir", tmp_path / "pred", "--methods", METHODS, "--ours", "ours", "--out", tmp_path / out, *extra, cwd=tmp_path)


def _rows(path): return list(csv.DictReader(io.open(path, encoding="utf-8", newline="")))
def _meta(tmp_path, stem="samples"): return json.loads(read(tmp_path / f"{stem}.meta.json"))
def _ids(path): return [r["image"] for r in _rows(path)]


def test_det_picks_the_frames_with_the_largest_advantage_and_breaks_ties_by_gt_count_then_id(tmp_path):
    r = _sel(tmp_path, "--k", "2"); assert r.returncode == 0 and not r.crashed, r.out
    rows = _rows(tmp_path / "samples.csv")
    assert [x["image"] for x in rows] == ["img01", "img05"]                       # both score 2; img01 has more ground-truth objects
    assert [float(x["score"]) for x in rows] == [2.0, 2.0] and {x["kind"] for x in rows} == {"win"}
    r = _sel(tmp_path, "--k", "3"); assert _ids(tmp_path / "samples.csv") == ["img01", "img05", "img04"]


def test_equal_score_and_gt_count_fall_back_to_the_image_id(tmp_path):
    spec = {"zz": SPEC["img05"], "aa": SPEC["img05"], "mm": SPEC["img02"]}
    _sel(tmp_path, "--k", "2", spec=spec); assert _ids(tmp_path / "samples.csv") == ["aa", "zz"]


def test_cell_counts_columns_are_tp_fp_fn_per_method(tmp_path):
    _sel(tmp_path, "--k", "4")
    r = {x["image"]: x for x in _rows(tmp_path / "samples.csv")}
    assert list(r["img01"])[:3] == ["image", "group", "score"] and "kind" == list(r["img01"])[-1]
    assert (r["img01"]["tp_ours"], r["img01"]["fp_ours"], r["img01"]["fn_ours"]) == ("2", "0", "0")
    assert (r["img01"]["tp_base1"], r["img01"]["fp_base1"], r["img01"]["fn_base1"]) == ("0", "0", "2")
    assert (r["img04"]["tp_base1"], r["img04"]["fp_base1"], r["img04"]["fn_base1"]) == ("2", "3", "0")


def test_counter_examples_are_reported_printed_and_written(tmp_path):
    r = _sel(tmp_path, "--k", "2")
    assert "counter-examples" in r.out and "counter  img03" in r.out, r.out
    c = _rows(tmp_path / "samples_counter.csv"); assert [x["image"] for x in c] == ["img03"] and float(c[0]["score"]) == -4.0 and c[0]["kind"] == "counter"
    assert "img03" not in _ids(tmp_path / "samples.csv")


def test_meta_holds_the_rule_and_the_global_win_loss_counts_over_all_images(tmp_path):
    _sel(tmp_path, "--k", "2")
    m = _meta(tmp_path)
    assert (m["n_images"], m["wins"], m["losses"], m["ties"]) == (5, 3, 1, 1)
    assert m["selected"] == ["img01", "img05"] and m["counter_examples"] == ["img03"] and m["n_counter"] == 1 and m["mode"] == "det"
    assert "IoU ≥ 0.5" in m["rule"] and "strongest on that frame" in m["rule"] and m["scores"]["img02"] == 0
    assert m["per_method_totals"]["ours"] == {"tp": 7, "fp": 0, "fn": 2} and m["per_method_totals"]["base1"] == {"tp": 6, "fp": 3, "fn": 3}
    all_rows = _rows(tmp_path / "samples.all.csv"); assert len(all_rows) == 5                  # nothing is hidden


def test_group_quota_limits_the_frames_per_group(tmp_path):
    write(tmp_path / "frames.csv", "image,condition\nimg01,night\nimg05,night\nimg04,night\nimg02,day\nimg03,day\n")
    _sel(tmp_path, "--k", "2", "--group-csv", tmp_path / "frames.csv", "--group-col", "condition")
    rows = _rows(tmp_path / "samples.csv")
    assert [x["image"] for x in rows] == ["img01", "img02"] and {x["group"] for x in rows} == {"night", "day"}      # the two best frames are both night: quota is 1 per group
    m = _meta(tmp_path); assert m["group_quota"] == 1 and m["groups"] == {"day": 2, "night": 3} and "at most 1 per condition" in m["rule"]


def test_group_csv_with_a_missing_column_fails(tmp_path):
    write(tmp_path / "frames.csv", "image,condition\nimg01,night\n")
    r = _sel(tmp_path, "--group-csv", tmp_path / "frames.csv", "--group-col", "nope"); assert r.returncode == 1 and "no column 'nope'" in r.out


def test_typical_adds_the_median_score_frame_as_honest_context(tmp_path):
    _sel(tmp_path, "--k", "2", "--typical", "1")
    rows = _rows(tmp_path / "samples.csv")
    assert [x["image"] for x in rows] == ["img01", "img05", "img04"] and [x["kind"] for x in rows] == ["win", "win", "typical"]      # median of [2, 0, -4, 1.5, 2] is 1.5
    assert _meta(tmp_path)["typical"] == ["img04"] and "median-score" in _meta(tmp_path)["rule"]


def test_min_score_drops_low_confidence_predictions(tmp_path):
    spec = {"a": {"gt": 1, "pred": {"base1": (0, 0), "base2": (0, 0), "ours": (1, 0)}}}
    _scene(tmp_path, spec)
    write(tmp_path / "pred" / "base1" / "a.txt", box(0, 0.1) + "\n")                         # a hit, but at confidence 0.1
    r = run("select_samples.py", "det", "--gt-dir", tmp_path / "gt", "--pred-dir", tmp_path / "pred", "--methods", METHODS, "--ours", "ours", "--min-score", "0.25", "--out", tmp_path / "s.csv", cwd=tmp_path)
    row = _rows(tmp_path / "s.csv")[0]; assert (row["tp_base1"], row["fn_base1"]) == ("0", "1"), r.out
    run("select_samples.py", "det", "--gt-dir", tmp_path / "gt", "--pred-dir", tmp_path / "pred", "--methods", METHODS, "--ours", "ours", "--min-score", "0.05", "--out", tmp_path / "s.csv", cwd=tmp_path)
    assert _rows(tmp_path / "s.csv")[0]["tp_base1"] == "1"


def test_missing_prediction_file_is_a_warning_and_counts_as_no_detections(tmp_path):
    _scene(tmp_path, SPEC); (tmp_path / "pred" / "base1" / "img01.txt").unlink()
    r = run("select_samples.py", "det", "--gt-dir", tmp_path / "gt", "--pred-dir", tmp_path / "pred", "--methods", METHODS, "--ours", "ours", "--out", tmp_path / "s.csv", cwd=tmp_path)
    assert r.returncode == 0 and "[WARN] method 'base1': no prediction file for 1 of 5" in r.out, r.out


def test_only_a_few_frames_with_ours_ahead_is_warned(tmp_path):
    _sel(tmp_path, "--k", "5"); r = run("select_samples.py", "det", "--gt-dir", tmp_path / "gt", "--pred-dir", tmp_path / "pred", "--methods", METHODS, "--ours", "ours", "--k", "5", "--out", tmp_path / "s.csv", cwd=tmp_path)
    assert "[WARN] only 3 of 5 chosen frame(s) show ours ahead" in r.out, r.out


def test_bad_arguments_fail_cleanly(tmp_path):
    _scene(tmp_path, SPEC)
    r = run("select_samples.py", "det", "--gt-dir", tmp_path / "gt", "--pred-dir", tmp_path / "pred", "--methods", METHODS, "--ours", "nobody", "--out", tmp_path / "s.csv", cwd=tmp_path)
    assert r.returncode == 1 and "not among --methods" in r.out and not r.crashed
    r = run("select_samples.py", "det", "--gt-dir", tmp_path / "gt", "--pred-dir", tmp_path / "pred", "--methods", "ours", "--ours", "ours", "--out", tmp_path / "s.csv", cwd=tmp_path)
    assert r.returncode == 1 and "at least one baseline" in r.out
    r = run("select_samples.py", "det", "--gt-dir", tmp_path / "nope", "--pred-dir", tmp_path / "pred", "--methods", METHODS, "--ours", "ours", "--out", tmp_path / "s.csv", cwd=tmp_path)
    assert r.returncode == 1 and "not a directory" in r.out


def test_pixel_xyxy_labels_with_img_size_and_gt_in_a_GT_subdirectory(tmp_path):
    write(tmp_path / "gt" / "GT" / "a.txt", "0 10 10 50 50\n"); write(tmp_path / "gt" / "GT" / "b.txt", "0 20 20 60 60\n")
    for m, hit in (("base1", 0), ("ours", 1)):
        write(tmp_path / "pred" / m / "a.txt", "0 10 10 50 50 0.9\n" if hit else "")
        write(tmp_path / "pred" / m / "b.txt", "0 20 20 60 60 0.9\n")
    r = run("select_samples.py", "det", "--gt-dir", tmp_path / "gt", "--pred-dir", tmp_path / "pred", "--methods", "base1,ours", "--ours", "ours", "--label-fmt", "xyxy", "--img-size", "100,100", "--k", "1",
            "--out", tmp_path / "s.csv", cwd=tmp_path)
    assert r.returncode == 0, r.out
    row = _rows(tmp_path / "s.csv")[0]; assert row["image"] == "a" and row["tp_ours"] == "1" and row["tp_base1"] == "0"


# ------------------------------------------------------------------ cam
def _cam_scene(tmp_path):
    """GT box = the left half of a 10 x 10 map (yolo cx .25 cy .5 w .5 h 1). `left` maps put all mass left, `right` maps right, `flat` is uniform"""
    left = np.zeros((10, 10)); left[:, :5] = 1.0; right = np.zeros((10, 10)); right[:, 5:] = 1.0; flat = np.full((10, 10), 0.7)
    spec = {"c1": (left, right), "c2": (right, left), "c3": (left, flat), "c4": (flat, left)}      # (ours, baseline)
    for img, (o, b) in spec.items():
        write(tmp_path / "gt" / f"{img}.txt", "0 0.25 0.5 0.5 1.0\n")
        for m, arr in (("ours", o), ("base1", b)):
            p = tmp_path / "ov" / m / f"{img}.npy"; p.parent.mkdir(parents=True, exist_ok=True); np.save(p, arr)
    write(tmp_path / "gt" / "c5.txt", "")                                                           # no ground-truth box: skipped
    return spec


def test_cam_in_box_share_selects_by_advantage_and_reports_counter_examples(tmp_path):
    _cam_scene(tmp_path)
    r = run("select_samples.py", "cam", "--overlay-dir", tmp_path / "ov", "--gt-dir", tmp_path / "gt", "--methods", "base1,ours", "--ours", "ours", "--k", "2", "--out", tmp_path / "cam.csv", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    rows = {x["image"]: x for x in _rows(tmp_path / "cam.csv")}
    assert list(rows) == ["c1", "c3"]
    allrows = {x["image"]: x for x in _rows(tmp_path / "cam.all.csv")}
    assert float(allrows["c1"]["inbox_ours"]) == pytest.approx(1.0) and float(allrows["c1"]["inbox_base1"]) == pytest.approx(0.0)
    assert float(allrows["c3"]["inbox_base1"]) == pytest.approx(0.5)                                # a flat map carries no information: share = box area fraction
    assert float(allrows["c1"]["score"]) == pytest.approx(1.0) and float(allrows["c3"]["score"]) == pytest.approx(0.5)
    assert float(allrows["c2"]["score"]) == pytest.approx(-1.0) and "c5" not in allrows            # c5 has no GT boxes
    m = _meta(tmp_path, "cam")
    assert m["mode"] == "cam" and (m["n_images"], m["wins"], m["losses"], m["ties"]) == (4, 2, 2, 0) and m["skipped"]["no GT boxes"] == 1
    assert m["counter_examples"] == ["c2", "c4"] and m["counter_margin"] == pytest.approx(0.5), m["counter_examples"]
    assert "activation mass" in m["rule"]
    assert "[WARN] 1 image(s) skipped: no GT boxes" in r.out


def test_cam_group_quota_and_missing_overlay(tmp_path):
    _cam_scene(tmp_path)
    write(tmp_path / "frames.csv", "sample,time\nc1,day\nc3,day\nc2,night\nc4,night\n")
    r = run("select_samples.py", "cam", "--overlay-dir", tmp_path / "ov", "--gt-dir", tmp_path / "gt", "--methods", "base1,ours", "--ours", "ours", "--k", "2", "--group-csv", tmp_path / "frames.csv",
            "--group-col", "time", "--out", tmp_path / "cam.csv", cwd=tmp_path)
    rows = _rows(tmp_path / "cam.csv")
    assert [(x["image"], x["group"]) for x in rows] == [("c1", "day"), ("c4", "night")]            # quota 1 per group: c3 (also a win) is left out; night has no win, its best frame is shown
    assert "[WARN] only 1 of 2 chosen frame(s) show ours ahead" in r.out, r.out
    (tmp_path / "ov" / "ours" / "c1.npy").unlink()
    r = run("select_samples.py", "cam", "--overlay-dir", tmp_path / "ov", "--gt-dir", tmp_path / "gt", "--methods", "base1,ours", "--ours", "ours", "--out", tmp_path / "cam2.csv", cwd=tmp_path)
    assert "ours has no overlay" in r.out and "c1" not in _ids(tmp_path / "cam2.all.csv"), r.out
