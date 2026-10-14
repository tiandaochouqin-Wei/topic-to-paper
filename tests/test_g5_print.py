# -*- coding: utf-8 -*-
"""tests for the G5 extension: printed font size, figure-type coverage, dual axis."""
from conftest import edit, read, run, write
import csv, io


def _tiny_text_pdf(path, width_mm=180.0, font_pt=7.0):
    """a vector PDF with one 7 pt label at a 180 mm native width; registered at 45 mm it prints at 1.75 pt"""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, 40 / 25.4)); ax.plot([0, 1], [0, 1]); ax.set_xlabel("x axis label", fontsize=font_pt); ax.set_ylabel("y", fontsize=font_pt)
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)


def _dual_axis_pdf(path):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(88 / 25.4, 50 / 25.4)); ax.plot([0, 1], [0, 1]); ax.set_ylabel("left quantity", fontsize=8); ax.set_xlabel("x", fontsize=8)
    ax2 = ax.twinx(); ax2.plot([0, 1], [1, 0]); ax2.set_ylabel("right quantity", fontsize=8)
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)


def _register(research, file, width):
    rows = list(csv.DictReader(io.open(research / "figures.csv", encoding="utf-8-sig")))
    rows.append({"file": file, "print_width_mm": str(width), "source_data": "results/summary.csv", "inspected": "yes", "issues": ""})
    with io.open(research / "figures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "print_width_mm", "source_data", "inspected", "issues"]); w.writeheader(); w.writerows(rows)


def test_g5_printed_font_too_small_fails(research):
    _tiny_text_pdf(research / "figures" / "fig_small.pdf"); _register(research, "figures/fig_small.pdf", 45)
    r = run("gate_check.py", "dpi", cwd=research)
    assert r.fails >= 1 and "印刷最小字号" in r.out and "fig_small.pdf" in r.out, r.out


def test_g5_printed_font_ok_at_native_width(research):
    _tiny_text_pdf(research / "figures" / "fig_ok.pdf", width_mm=88.0, font_pt=7.0); _register(research, "figures/fig_ok.pdf", 88)
    r = run("gate_check.py", "dpi", cwd=research)
    assert "fig_ok.pdf 印刷字号" in r.out and "fig_ok.pdf 印刷最小字号" not in r.out, r.out


def test_g5_dual_axis_warns(research):
    _dual_axis_pdf(research / "figures" / "fig_dual.pdf"); _register(research, "figures/fig_dual.pdf", 88)
    r = run("gate_check.py", "dpi", cwd=research)
    assert "双纵轴" in r.out and "fig_dual.pdf" in r.out, r.out


def test_g5_figure_type_coverage_warns_and_waiver_clears(research):
    """fixture: cs_journal, one overview caption -> qualitative/comparison/ablation missing (WARN); a 'no <type>: why' note in figures.csv issues clears each"""
    r = run("gate_check.py", "dpi", cwd=research)
    assert "图类型本文题注没有命中" in r.out and "qualitative" in r.out, r.out
    rows = list(csv.DictReader(io.open(research / "figures.csv", encoding="utf-8-sig")))
    rows[0]["issues"] = "no qualitative: force regression has no image output; no comparison: Table 1 carries it; no ablation: Table 2 carries it"
    with io.open(research / "figures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "print_width_mm", "source_data", "inspected", "issues"]); w.writeheader(); w.writerows(rows)
    r = run("gate_check.py", "dpi", cwd=research)
    assert "图类型本文题注没有命中" not in r.out and "均有题注命中或已写明豁免" in r.out, r.out


def test_g5_coverage_satisfied_by_captions(research):
    m = research / "paper" / "manuscript.md"
    edit(m, "**Fig. 1.** Architecture overview", "**Fig. 2.** Qualitative examples of predicted forces, a comparison of methods, and the effect of the adversarial term (ablation).\n\n**Fig. 1.** Architecture overview", 1)
    r = run("gate_check.py", "dpi", cwd=research)
    assert "图类型本文题注没有命中" not in r.out, r.out
