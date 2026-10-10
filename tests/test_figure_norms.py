# -*- coding: utf-8 -*-
"""figure_norms.py: caption classification rules, panel/statistics detection, topic grouping, and the report on a tiny per-paper table."""
import importlib.util
import re

from conftest import SCRIPTS, read, run, write


def _mod():
    spec = importlib.util.spec_from_file_location("figure_norms", SCRIPTS / "figure_norms.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def _types(m, caption):
    return {name for name, rx in m.FIGURE_TYPES if re.search(rx, caption, re.I)}


def test_caption_rules_cover_the_common_figure_kinds():
    m = _mod()
    assert "overview" in _types(m, "Overview of the proposed framework. The encoder ...")
    assert "overview" in _types(m, "The training procedure of the retrieval module.")
    assert "concept" in _types(m, "We present OffsetOPT for explicit surface reconstruction.")
    assert "qualitative" in _types(m, "Qualitative comparison on Cityscapes; red boxes mark errors.")
    assert "comparison" in _types(m, "Comparison results of integration modules and training paradigms.")
    assert "curves" in _types(m, "mIoU versus the number of training iterations.")
    assert "ablation" in _types(m, "Ablation on the number of layers.")
    assert "embedding" in _types(m, "t-SNE visualization of the learned features.")
    assert "heatmap" in _types(m, "Grad-CAM attention maps of the last block.")
    assert "roc_pr" in _types(m, "ROC curves and reliability diagram of the calibrated model.")
    assert "scatter" in _types(m, "Bland-Altman plot of predicted and measured force.")
    assert "flowchart" in _types(m, "PRISMA flow diagram of study selection.")
    assert "clinical" in _types(m, "Kaplan-Meier curves by risk group.")
    assert "failure" in _types(m, "Failure cases of our method on thin structures.")
    assert _types(m, "Lorem ipsum dolor sit amet.") == set()


def test_panel_and_statistics_detection():
    m = _mod()
    assert m.PANEL_RE.search("Results. (a) Input image. (b) Our prediction.")
    assert m.PANEL_RE.search("Manipulation of gut microbiota. a Outline of treatment regimens. b–e Wild-type mice ...")
    assert m.PANEL_RE.search("Top row: inputs; bottom row: outputs.")
    assert not m.PANEL_RE.search("We show a single qualitative example of the output.")
    assert m.STAT_RE.search("Data are mean ± s.d.; n = 6 mice per group; two-sided t-test.")
    assert not m.STAT_RE.search("Overview of the pipeline.")


def test_captions_of_joins_wrapped_lines_and_stops_at_blank_line():
    m = _mod()
    full = "text\n\nFig. 1. Overview of our\nmethod with three stages.\n\nBody paragraph here.\nFigure 2: Qualitative results on COCO.\n\n"
    caps = dict(m.captions_of(full, len(full)))
    assert caps[1] == "Overview of our method with three stages." and caps[2].startswith("Qualitative results")


def test_topic_grouping_order():
    m = _mod()
    assert m.topic_group("CVPR", "retrieval", "KP-RED: 3D shape retrieval from point clouds", None) == "perception3d"
    assert m.topic_group("CVPR", "", "Vision-Language-Action model for robots", None) == "vlm"
    assert m.topic_group("TIP", "denois", "Low-dose CT denoising", None) == "medical"          # medical wins over low-level
    assert m.topic_group("MICCAI", "", "anything", None) == "medical"
    assert m.topic_group("NatCommun", "", "x", "Medicine") == "medical" and m.topic_group("Nature", "", "x", "Biochemistry, Genetics and Molecular Biology") == "life_sciences"


def test_report_on_a_tiny_table(tmp_path):
    cols = ["paper", "title", "venue", "family", "topic", "year", "pages", "n_fig", "n_tab", "teaser_p1", "raster_images", "vector_paths", "all_vector", "multi_panel", "stat_caption", "unclassified"] + [n for n, _ in _mod().FIGURE_TYPES]
    rows = [["p1", "t1", "CVPR", "cs_conf", "perception2d", "2025", "10", "6", "4", "1", "30", "500", "0", "3", "0", "1"] + ["1", "1", "2", "1", "1", "0", "1", "0", "1", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
            ["p2", "t2", "NatCommun", "nature", "life_sciences", "2024", "18", "5", "0", "0", "10", "90", "0", "5", "5", "0"] + ["0", "0", "1", "0", "0", "1", "0", "0", "0", "0", "0", "1", "1", "0", "0", "0", "1", "1", "0"]]
    p = tmp_path / "pp.csv"
    write(p, "\n".join(",".join(r) for r in [cols] + rows) + "\n")
    r = run("figure_norms.py", "report", "--per-paper", str(p), "--out", str(tmp_path / "norms.md"), cwd=tmp_path)
    assert r.returncode == 0, r.out
    md = read(tmp_path / "norms.md")
    assert "## 按 venue" in md and "| CVPR | 1 |" in md and "| nature | 1 |" in md and "最常见的五种图" in md
