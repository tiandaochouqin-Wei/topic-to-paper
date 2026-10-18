# -*- coding: utf-8 -*-
"""round 20b: --out x.pdf must not crash (PIL cannot read the PDF for the grayscale preview)."""
from conftest import run


def test_out_pdf_writes_png_pdf_and_gray(research):
    r = run("make_figure.py", "ablation", "--project", ".", "--out", "figures/fig_abpdf.pdf", "--metrics", "rmse_E1", cwd=research)
    assert r.returncode == 0, r.out
    for ext in (".pdf", ".png", "_gray.png", ".source.csv"):
        assert (research / "figures" / ("fig_abpdf" + ext)).exists(), ext
