# -*- coding: utf-8 -*-
"""tests for validation round 18: fonttype 42, in-memory layout audit, grayscale preview, G5 font-embedding check."""
from conftest import read, run, write
import csv, io, os, sys


def _fonts(pdf):
    from pypdf import PdfReader
    out = set()
    for pg in PdfReader(pdf).pages:
        for _, fo in ((pg.get("/Resources") or {}).get("/Font") or {}).items():
            fo = fo.get_object(); out.add(str(fo.get("/Subtype", "")))
    return out


def test_make_figure_pdf_has_no_type3_fonts_and_writes_grayscale(research):
    r = run("make_figure.py", "main", "--project", ".", "--out", "figures/fig_q.png", "--metrics", "rmse_E1", cwd=research)
    assert r.returncode == 0, r.out
    assert "Type3" not in _fonts(research / "figures" / "fig_q.pdf"), _fonts(research / "figures" / "fig_q.pdf")
    assert os.path.exists(research / "figures" / "fig_q_gray.png")
    assert "layout audit clean" in r.out, r.out


def test_g5_fails_on_type3_pdf(research):
    """a PDF saved with matplotlib's default fonttype 3 must FAIL the embedding check"""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    matplotlib.rcParams["pdf.fonttype"] = 3
    fig, ax = plt.subplots(figsize=(3.5, 2)); ax.plot([0, 1], [0, 1]); ax.set_xlabel("x label", fontsize=8); ax.set_ylabel("y", fontsize=8)
    fig.savefig(research / "figures" / "fig_t3.pdf"); plt.close(fig)
    rows = list(csv.DictReader(io.open(research / "figures.csv", encoding="utf-8-sig")))
    rows.append({"file": "figures/fig_t3.pdf", "print_width_mm": "88", "source_data": "results/summary.csv", "inspected": "yes", "issues": ""})
    with io.open(research / "figures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "print_width_mm", "source_data", "inspected", "issues"]); w.writeheader(); w.writerows(rows)
    r = run("gate_check.py", "dpi", cwd=research)
    assert "Type 3" in r.out and "fig_t3.pdf" in r.out and r.fails >= 1, r.out


def test_audit_layout_flags_overlapping_ticks_and_missing_glyph():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    import make_figure as mf
    fig, ax = plt.subplots(figsize=(1.2, 1.0))
    ax.set_xticks(range(12)); ax.set_xticklabels([f"very long label {i}" for i in range(12)], fontsize=9)
    issues = mf.audit_layout(fig); plt.close(fig)
    assert any(sv == "WARN" and "overlapping tick" in m for sv, m in issues), issues
    fig, ax = plt.subplots(figsize=(3, 2)); ax.set_title("中文标题 − test", fontfamily="DejaVu Sans")
    issues = mf.audit_layout(fig); plt.close(fig)
    assert any(sv == "FAIL" and "glyph" in m for sv, m in issues), issues


def test_audit_layout_clean_on_fixture_figure(research):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    import make_figure as mf
    fig, ax = plt.subplots(figsize=(3.5, 2)); ax.plot([0, 1], [0, 1]); ax.set_xlabel("x"); ax.set_ylabel("y")
    assert mf.audit_layout(fig) == [], mf.audit_layout(fig)
    plt.close(fig)


def test_g5_passes_fonttype42_pdf_as_embedded(research):
    """fonttype 42 produces a Type0 font whose program lives on the descendant font; must count as embedded, not WARN"""
    r = run("make_figure.py", "main", "--project", ".", "--out", "figures/fig_q42.png", "--metrics", "rmse_E1", cwd=research)
    assert r.returncode == 0, r.out
    rows = list(csv.DictReader(io.open(research / "figures.csv", encoding="utf-8-sig")))
    for row in rows:
        if row["file"] == "figures/fig_q42.png": row["file"] = "figures/fig_q42.pdf"; row["inspected"] = "yes"
    with io.open(research / "figures.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    r = run("gate_check.py", "dpi", cwd=research)
    assert "fig_q42.pdf 字体可能未嵌入" not in r.out and "fig_q42.pdf 含 Type 3" not in r.out, r.out


def test_audit_layout_flags_text_over_other_panel():
    """a long title on the left panel that runs into the right panel's plotting area is real clipping tight-bbox cannot fix"""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    import make_figure as mf
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(3, 1.5))
    a1.text(0.5, 0.5, "an extremely long annotation that spills far to the right", fontsize=9, transform=a1.transAxes)
    issues = mf.audit_layout(fig); plt.close(fig)
    assert any(sv == "WARN" and "another panel" in m for sv, m in issues), issues
