# -*- coding: utf-8 -*-
"""log_adapters.py: training logs -> epoch-level long CSV. Units are never guessed; gaps / duplicates / NaN are reported, not hidden."""
import csv, importlib.util, io, json, sys

import pytest

from conftest import SCRIPTS, run, write

ULTRA = ("                   epoch,      train/box_loss,   metrics/precision(B),      metrics/mAP50(B),\n"
         "                       1,            1.20,             0.40,             0.30,\n"
         "                       2,            1.00,             0.50,             0.45,\n"
         "                       3,            0.90,             0.55,             0.52,\n"
         "                       4,            0.80,             0.60,             0.58,\n"
         "                       5,            0.70,             0.62,             0.60,\n")


def _rows(p):
    return list(csv.DictReader(io.open(p, encoding="utf-8")))


def _ad(tmp_path, *args):
    return run("log_adapters.py", *args, cwd=tmp_path)


def _ultra(tmp_path, text=ULTRA):
    write(tmp_path / "results.csv", text)
    return ["--adapter", "ultralytics", "--input", "results.csv", "--metric-col", "metrics/mAP50(B)", "--method", "yolo", "--dataset", "D1", "--out", "out.csv"]


def test_ultralytics_fraction_is_multiplied_and_recorded(tmp_path):
    r = _ad(tmp_path, *_ultra(tmp_path), "--units", "fraction")
    assert r.fails == 0 and not r.crashed, r.out
    rows = _rows(tmp_path / "out.csv")
    assert [x["epoch"] for x in rows] == ["1", "2", "3", "4", "5"] and rows[0]["epoch_base"] == "1"
    assert [float(x["value"]) for x in rows] == pytest.approx([30, 45, 52, 58, 60])
    x = rows[0]
    assert (x["units_in"], x["units_out"], x["method"], x["dataset"], x["seed"], x["metric"], x["adapter"]) == ("fraction", "percent", "yolo", "D1", "0", "metrics/mAP50(B)", "ultralytics")
    assert x["source_file"] == "results.csv" and len(x["source_sha256"]) == 64
    assert list(rows[0])[:10] == ["epoch", "value", "method", "dataset", "seed", "metric", "units_in", "units_out", "source_file", "source_sha256"]


def test_ultralytics_zero_based_epoch_is_preserved(tmp_path):
    text = ULTRA.replace("    1,", "    0,").replace("    2,", "    1,").replace("    3,", "    2,").replace("    4,", "    3,").replace("    5,", "    4,")
    r = _ad(tmp_path, *_ultra(tmp_path, text), "--units", "fraction")
    rows = _rows(tmp_path / "out.csv")
    assert r.fails == 0 and rows[0]["epoch"] == "0" and rows[0]["epoch_base"] == "0", r.out


def test_units_are_mandatory(tmp_path):
    r = _ad(tmp_path, *_ultra(tmp_path))
    assert r.fails == 1 and "单位必须显式给出" in r.out and not (tmp_path / "out.csv").exists(), r.out


def test_percent_with_all_values_le_one_warns(tmp_path):
    r = _ad(tmp_path, *_ultra(tmp_path), "--units", "percent")
    assert r.fails == 0 and "[WARN] adapt: 全部 ≤ 1 但声明为 percent，确认不是小数" in r.out, r.out
    assert [float(x["value"]) for x in _rows(tmp_path / "out.csv")][0] == pytest.approx(0.30)       # unchanged: the warning does not rewrite


def test_percent_with_fewer_than_five_values_does_not_warn(tmp_path):
    r = _ad(tmp_path, *_ultra(tmp_path, "epoch,metrics/mAP50(B)\n1,0.3\n2,0.4\n3,0.5\n"), "--units", "percent")
    assert r.fails == 0 and "≤ 1" not in r.out, r.out


def test_fraction_with_percent_looking_values_fails(tmp_path):
    r = _ad(tmp_path, *_ultra(tmp_path, "epoch,metrics/mAP50(B)\n1,30\n2,45\n3,52\n"), "--units", "fraction")
    assert r.fails == 1 and "1.5" in r.out and not (tmp_path / "out.csv").exists(), r.out


def test_percent_values_pass_through_unchanged(tmp_path):
    r = _ad(tmp_path, *_ultra(tmp_path, "epoch,metrics/mAP50(B)\n1,30.5\n2,45\n3,52\n"), "--units", "percent")
    assert r.fails == 0 and [float(x["value"]) for x in _rows(tmp_path / "out.csv")] == pytest.approx([30.5, 45, 52]), r.out


def test_unknown_metric_column_lists_the_columns(tmp_path):
    args = _ultra(tmp_path); args[args.index("--metric-col") + 1] = "metrics/nope"
    r = _ad(tmp_path, *args, "--units", "fraction")
    assert r.fails == 1 and "metrics/mAP50(B)" in r.out, r.out


def test_mmengine_val_lines_only_and_epochless_lines_counted(tmp_path):
    lines = [{"mode": "train", "epoch": 1, "iter": 50, "loss": 1.0},
             {"mode": "val", "epoch": 1, "coco/bbox_mAP": 0.21},
             {"mode": "train", "epoch": 2, "iter": 50, "loss": 0.9},
             {"mode": "val", "epoch": 2, "coco/bbox_mAP": 0.27},
             {"mode": "val", "coco/bbox_mAP": 0.99},                                  # no epoch -> skipped, counted
             {"mode": "val", "epoch": 3, "coco/bbox_mAP": 0.31}]
    write(tmp_path / "x.log.json", "\n".join(json.dumps(l) for l in lines) + "\nnot json\n")
    r = _ad(tmp_path, "--adapter", "mmengine", "--input", "x.log.json", "--metric-col", "coco/bbox_mAP", "--method", "m", "--dataset", "D", "--units", "fraction", "--out", "o.csv")
    assert r.fails == 0 and "1 行没有 epoch" in r.out and "不是合法 JSON" in r.out, r.out
    assert [float(x["value"]) for x in _rows(tmp_path / "o.csv")] == pytest.approx([21, 27, 31])


def test_mmengine_without_val_lines_fails(tmp_path):
    write(tmp_path / "x.log.json", json.dumps({"mode": "train", "epoch": 1, "loss": 1}) + "\n")
    r = _ad(tmp_path, "--adapter", "mmengine", "--input", "x.log.json", "--metric-col", "acc", "--method", "m", "--units", "fraction", "--out", "o.csv")
    assert r.fails == 1 and "mode=val" in r.out, r.out


LIGHT = ("epoch,step,train_loss,val_acc\n"
         "0,49,0.9,\n0,99,0.8,0.50\n"
         "1,149,0.7,\n1,199,0.6,0.62\n1,200,,0.64\n"       # epoch 1 validated twice -> duplicate epoch
         "2,249,0.5,\n2,299,0.4,0.70\n")


def test_lightning_keeps_last_per_epoch_and_warns_about_duplicates(tmp_path):
    write(tmp_path / "metrics.csv", LIGHT)
    r = _ad(tmp_path, "--adapter", "lightning", "--input", "metrics.csv", "--metric-col", "val_acc", "--method", "m", "--dataset", "D", "--units", "fraction", "--out", "o.csv")
    assert r.fails == 0 and "重复" in r.out and "保留最后一条" in r.out, r.out
    rows = _rows(tmp_path / "o.csv")
    assert [x["epoch"] for x in rows] == ["0", "1", "2"] and [float(x["value"]) for x in rows] == pytest.approx([50, 64, 70])


def test_generic_csv_gap_and_nan_are_reported(tmp_path):
    write(tmp_path / "g.csv", "ep,acc\n0,0.5\n1,0.6\n4,0.7\n5,nan\n6,0.75\n")
    r = _ad(tmp_path, "--adapter", "csv", "--input", "g.csv", "--epoch-col", "ep", "--metric-col", "acc", "--method", "m", "--units", "fraction", "--out", "o.csv")
    assert r.fails == 0 and "[2, 3, 5]" in r.out and "NaN/inf 已丢弃" in r.out, r.out
    assert [x["epoch"] for x in _rows(tmp_path / "o.csv")] == ["0", "1", "4", "6"]


def test_generic_csv_inf_is_dropped(tmp_path):
    write(tmp_path / "g.csv", "epoch,acc\n0,0.5\n1,inf\n2,0.7\n")
    r = _ad(tmp_path, "--adapter", "csv", "--input", "g.csv", "--metric-col", "acc", "--method", "m", "--units", "fraction", "--out", "o.csv")
    assert r.fails == 0 and "NaN/inf" in r.out and len(_rows(tmp_path / "o.csv")) == 2, r.out


def test_append_merges_methods_and_replaces_reruns(tmp_path):
    base = _ultra(tmp_path)
    assert _ad(tmp_path, *base, "--units", "fraction").fails == 0
    write(tmp_path / "b.csv", "epoch,acc\n1,0.2\n2,0.3\n")
    other = ["--adapter", "csv", "--input", "b.csv", "--metric-col", "acc", "--method", "base", "--dataset", "D1", "--units", "fraction", "--out", "out.csv", "--append"]
    r = _ad(tmp_path, *other, "--extra", "backbone=r50", "arch=cnn")
    assert r.fails == 0, r.out
    rows = _rows(tmp_path / "out.csv")
    assert sorted({x["method"] for x in rows}) == ["base", "yolo"] and len(rows) == 7
    assert {x["backbone"] for x in rows if x["method"] == "base"} == {"r50"} and {x["backbone"] for x in rows if x["method"] == "yolo"} == {""}
    r = _ad(tmp_path, *other)                                          # re-running the same method replaces, not duplicates
    assert r.fails == 0 and "被替换" in r.out and len(_rows(tmp_path / "out.csv")) == 7, r.out


def test_extra_key_colliding_with_a_fixed_column_fails(tmp_path):
    r = _ad(tmp_path, *_ultra(tmp_path), "--units", "fraction", "--extra", "method=x")
    assert r.fails == 1 and "重名" in r.out, r.out


def test_header_comment_is_opt_in_and_append_survives_it(tmp_path):
    base = _ultra(tmp_path)
    assert _ad(tmp_path, *base, "--units", "fraction", "--header-comment").fails == 0
    assert io.open(tmp_path / "out.csv", encoding="utf-8").readline().startswith("# adapter=ultralytics, input=results.csv, units_in=fraction")
    write(tmp_path / "b.csv", "epoch,acc\n1,0.2\n")
    r = _ad(tmp_path, "--adapter", "csv", "--input", "b.csv", "--metric-col", "acc", "--method", "base", "--units", "fraction", "--out", "out.csv", "--append")
    lines = io.open(tmp_path / "out.csv", encoding="utf-8").read().splitlines()
    assert r.fails == 0 and lines[0].startswith("# adapter=") and len(list(csv.DictReader(l for l in lines if not l.startswith("#")))) == 6, r.out
    assert _ad(tmp_path, *_ultra(tmp_path)[:-1], "plain.csv", "--units", "fraction").fails == 0
    assert io.open(tmp_path / "plain.csv", encoding="utf-8").readline().startswith("epoch,value")


def test_tensorboard_needs_step_is_epoch(tmp_path):
    write(tmp_path / "events.out.tfevents.0", "x")
    r = _ad(tmp_path, "--adapter", "tensorboard", "--input", "events.out.tfevents.0", "--metric-col", "val/acc", "--method", "m", "--units", "fraction", "--out", "o.csv")
    assert r.fails == 1 and "iteration" in r.out and "--step-is-epoch" in r.out, r.out


def test_tensorboard_missing_package_fails_with_install_hint(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("log_adapters_mod", SCRIPTS / "log_adapters.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    write(tmp_path / "events.out.tfevents.0", "x")
    for k in [k for k in sys.modules if k == "tensorboard" or k.startswith("tensorboard.")]: monkeypatch.delitem(sys.modules, k)
    monkeypatch.setitem(sys.modules, "tensorboard", None)               # `import tensorboard...` now raises ImportError
    rc = m.main(["--adapter", "tensorboard", "--input", str(tmp_path / "events.out.tfevents.0"), "--metric-col", "val/acc", "--method", "m", "--units", "fraction",
                 "--out", str(tmp_path / "o.csv"), "--step-is-epoch"])
    out = capsys.readouterr().out
    assert rc == 1 and "pip install tensorboard" in out and not (tmp_path / "o.csv").exists(), out


def test_tensorboard_happy_path(tmp_path):
    pytest.importorskip("tensorboard")
    import time
    from tensorboard.summary.writer.event_file_writer import EventFileWriter
    from tensorboard.compat.proto.event_pb2 import Event
    from tensorboard.compat.proto.summary_pb2 import Summary
    logdir = tmp_path / "tb"; logdir.mkdir()
    w = EventFileWriter(str(logdir))
    for step, v in [(0, 0.5), (1, 0.75), (2, 0.875)]:
        w.add_event(Event(wall_time=time.time(), step=step, summary=Summary(value=[Summary.Value(tag="val/acc", simple_value=v)])))
    w.close()
    r = _ad(tmp_path, "--adapter", "tensorboard", "--input", "tb", "--metric-col", "val/acc", "--method", "m", "--dataset", "D", "--units", "fraction", "--out", "o.csv", "--step-is-epoch")
    assert r.fails == 0, r.out
    assert [float(x["value"]) for x in _rows(tmp_path / "o.csv")] == pytest.approx([50, 75, 87.5]) and len(_rows(tmp_path / "o.csv")[0]["source_sha256"]) == 64


def test_output_feeds_make_figure_curves_end_to_end(research):
    p = research
    for meth, scale in (("ours", 1.0), ("base", 0.9)):
        write(p / f"{meth}.csv", "epoch,metrics/mAP50(B)\n" + "".join(f"{e},{(0.3 + 0.05 * e) * scale:.4f}\n" for e in range(1, 9)))
        r = run("log_adapters.py", "--adapter", "ultralytics", "--input", f"{meth}.csv", "--metric-col", "metrics/mAP50(B)", "--method", meth, "--dataset", "D1",
                "--units", "fraction", "--out", "results/curves_x.csv", "--append", cwd=p)
        assert r.fails == 0, r.out
    r = run("make_figure.py", "curves", "--project", ".", "--csv", "results/curves_x.csv", "--out", "figures/fig_curves_x.png", "--x", "epoch", "--y", "value",
            "--series", "method", "--ema", "0.12", "--ours", "ours", cwd=p)
    assert r.returncode == 0 and not r.crashed, r.out
    assert (p / "figures" / "fig_curves_x.pdf").exists()
    src = list(csv.DictReader(io.open(p / "figures" / "fig_curves_x.source.csv", encoding="utf-8")))
    assert {s.get("series", s.get("method", "")) for s in src} >= {"ours", "base"}, src[:3]
