# -*- coding: utf-8 -*-
"""G6d page limit (latex_check.py check -> pdf_check.run_checks -> page_limit / body_end) on synthetic two-column US-letter PDFs written next
to the fixture's paper/latex/main.tex, each with a review header, the margin ruler and a page number: body within the limit PASS; body lines
before the end-matter heading on page limit+1 FAIL (the tpami_medimg page-9 overflow; the heading merges into the body's text block as in the
real PDF), also with the heading in the right column after a full left column, and one page further; heading variants (numbered, upper case,
IEEE small caps, Bibliography, LLM Usage Statement before References); page_limit_end none / custom; no heading in a longer PDF WARN;
stale or missing PDF WARN; no page_limit INFO. The other PDF checks: tests/test_pdf_check.py."""
import re

import fitz
import pytest

from conftest import edit, run, touch

W, H = 612.0, 792.0                                  # US letter
LEFT, RIGHT = 54.0, 318.0                            # column x (CVPR: 0.75 in margin, 3.25 in columns, 0.3125 in gap)
BODY = "We measure the risk of every rater on held-out"  # one column line
REF = "[12] A. Author. A title. In CVPR, 2025."
STATE = "research-state.yaml"
FONT = fitz.Font("helv").buffer                      # embedded, so the font check stays quiet


def B(n): return [("body", BODY)] * n
def R(n): return [("ref", REF)] * n
def HEAD(t="References"): return [("head", t)]
FULL = (B(48), B(48))


def _pdf(project, pages):
    """pages: [(left items, right items)] -> paper/latex/main.pdf, newer than the .tex sources"""
    pdf = project / "paper" / "latex" / "main.pdf"
    doc = fitz.open()
    for i, cols in enumerate(pages, 1):
        p = doc.new_page(width=W, height=H)
        p.insert_font(fontname="F0", fontbuffer=FONT)
        p.insert_text((140, 30), "CVPR 2027 Submission #*****. CONFIDENTIAL REVIEW COPY. DO NOT DISTRIBUTE.", fontname="F0", fontsize=8)
        for k in range(50):                                                        # the review ruler in both margins
            p.insert_text((22, 84 + 12.5 * k), f"{k + 50 * (i - 1):03d}", fontname="F0", fontsize=7)
            p.insert_text((W - 38, 84 + 12.5 * k), f"{k + 50 * (i - 1):03d}", fontname="F0", fontsize=7)
        for x, items in zip((LEFT, RIGHT), cols):
            y = 84
            for kind, text in items:
                y += 4 if kind == "head" else 0
                p.insert_text((x, y), text, fontname="F0", fontsize=11 if kind == "head" else 9.5)
                y += 16 if kind == "head" else 12.5
        p.insert_text((W / 2 - 4, H - 28), str(i), fontname="F0", fontsize=9)       # page number
    doc.save(str(pdf)); doc.close()
    touch(pdf, +5)
    return pdf


def _limit(project, n=8, end=None):
    edit(project / STATE, "page_limit: null", f"page_limit: {n}" + (f"\n  page_limit_end: \"{end}\"" if end is not None else ""))


def _check(project, *keys):
    """latex_check.py check -> (result, the first output line holding main.pdf and every key; default key: page_limit)"""
    r = run("latex_check.py", "check", cwd=project)
    keys = keys or ("page_limit",)
    line = next((l for l in r.out.splitlines() if "main.pdf" in l and all(k in l for k in keys)), "")
    return r, line


def test_body_within_the_limit_passes(research):
    _limit(research); _pdf(research, [FULL] * 8 + [(HEAD() + R(40), R(48))])
    r, line = _check(research)
    assert line.startswith("[PASS]") and "正文止于第 8 页，≤ page_limit 8" in line and "'References' 从第 9 页起不计页" in line, r.out
    assert r.fails == 0, r.out


def test_body_lines_before_the_heading_on_the_next_page_fail(research):
    """tpami_medimg 2026-11-08: 18 lines of the Limitations ran onto page 9 above the end-matter heading"""
    _limit(research); _pdf(research, [FULL] * 8 + [(B(18) + HEAD("LLM Usage Statement") + B(4) + HEAD() + R(16), R(48))])
    r, line = _check(research)
    assert line.startswith("[FAIL]") and "止于第 9 页" in line and "'LLM Usage Statement' 之前还有 18 行正文" in line, r.out


def test_heading_in_the_right_column_after_a_full_left_column_fails(research):
    _limit(research); _pdf(research, [FULL] * 8 + [(B(48), HEAD() + R(40))])
    r, line = _check(research)
    assert line.startswith("[FAIL]") and "之前还有 48 行正文" in line, r.out


def test_heading_a_page_later_fails(research):
    _limit(research); _pdf(research, [FULL] * 9 + [(HEAD() + R(40), R(48))])
    r, line = _check(research)
    assert line.startswith("[FAIL]") and "止于第 9 页" in line, r.out


def test_short_body_passes(research):
    _limit(research); _pdf(research, [FULL] * 6 + [(B(20) + HEAD() + R(20), R(48)), (R(48), R(48))])
    r, line = _check(research)
    assert line.startswith("[PASS]") and "正文止于第 7 页" in line, r.out


@pytest.mark.parametrize("head", ["7. References", "REFERENCES", "R EFERENCES", "VII. REFERENCES", "Bibliography", "LLM Usage Statement"])
def test_heading_variants_are_found(research, head):
    _limit(research); _pdf(research, [FULL] * 8 + [(HEAD(head) + B(6) + R(30), R(48))])
    r, line = _check(research)
    assert line.startswith("[PASS]") and f"{head!r} 从第 9 页起不计页" in line, r.out


def test_page_limit_end_none_counts_every_page(research):
    _limit(research, end="none"); _pdf(research, [FULL] * 8 + [(HEAD() + R(40), R(48))])
    r, line = _check(research)
    assert line.startswith("[FAIL]") and "共 9 页 > page_limit 8" in line, r.out


def test_custom_page_limit_end(research):
    """an appendix before the references: the default counts it as body, `Appendix|References` stops at it"""
    pages = [FULL] * 8 + [(HEAD("Appendix") + B(40), B(48)), (HEAD() + R(40), R(48))]
    _limit(research); _pdf(research, pages)
    assert _check(research)[1].startswith("[FAIL]")
    edit(research / STATE, "page_limit: 8", 'page_limit: 8\n  page_limit_end: "Appendix|References"')
    r, line = _check(research)
    assert line.startswith("[PASS]") and "'Appendix' 从第 9 页起不计页" in line, r.out


def test_no_heading_in_a_longer_pdf_warns(research):
    _limit(research); _pdf(research, [FULL] * 10)
    r, line = _check(research)
    assert line.startswith("[WARN]") and "找不到" in line and "page_limit_end" in line and r.fails == 0, r.out


def test_stale_pdf_is_not_trusted(research):
    _limit(research); pdf = _pdf(research, [FULL] * 9 + [(HEAD() + R(40), R(48))])
    touch(pdf, -600)                                                                # older than the .tex sources
    r, line = _check(research, "比 .tex 源旧")
    assert line.startswith("[WARN]") and r.fails == 0, r.out
    assert len([l for l in r.out.splitlines() if "] pdf: " in l and "main.pdf" in l]) == 1, r.out    # nothing else is judged on a stale PDF


def test_missing_pdf_warns_and_no_limit_is_info(research):
    _limit(research)
    r, line = _check(research)
    assert line.startswith("[WARN]") and "没有 main.pdf" in line and r.fails == 0, r.out
    edit(research / STATE, "page_limit: 8", "page_limit: null"); _pdf(research, [FULL] * 9 + [(HEAD() + R(40), R(48))])
    r, line = _check(research)
    assert line.startswith("[INFO]") and "page_limit 未填" in line and r.fails == 0, r.out
