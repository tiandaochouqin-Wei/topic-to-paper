# -*- coding: utf-8 -*-
"""G6d: the manuscript in the venue's LaTeX template, every figure a PDF, multi-panel figures composed from one PDF per panel."""
import csv
import io
import shutil

from conftest import SKILL, edit, read, run, touch, write

MAIN = ("paper", "latex", "main.tex")
ABL = ("paper", "latex", "figs", "fig_abl.tex")


def _p(project, parts):
    return project.joinpath(*parts)


# ------------------------------------------------------------------ check
def test_latex_check_pass(research):
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails == 0, r.out
    assert "elsarticle" in r.out and "组合图逐子图引用" in r.out


def test_board_reports_g6d(research):
    run("draft_plan.py", "plan", "--project", ".", cwd=research)
    r = run("t2p.py", "check", "--project", ".", cwd=research)
    assert "[PASS] G6d:" in r.out, r.out


def test_png_figure_fails(research):
    edit(_p(research, MAIN), "{fig_main.pdf}", "{fig_main.png}")       # the png exists; only the extension rule fires
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "是 .png" in r.out, r.out


def test_missing_graphic_fails(research):
    edit(_p(research, ABL), "fig_abl_b.pdf", "fig_abl_missing.pdf")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "找不到文件" in r.out


def test_two_graphics_without_subfigure_fails(research):
    write(_p(research, ABL), "\\begin{figure}[t]\n  \\centering\n  \\includegraphics[width=0.48\\textwidth]{fig_abl_a.pdf}\\hfill\n"
                             "  \\includegraphics[width=0.48\\textwidth]{fig_abl_b.pdf}\n  \\caption{Two panels glued together.}\n  \\label{fig:abl}\n\\end{figure}\n")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "subfigure" in r.out


def test_precomposited_panels_caption_fails(research):
    edit(_p(research, MAIN), "Main comparison on both platforms (fixture).", "(a) E1 and (b) E2 (fixture).")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "预合成" in r.out


def test_missing_subcaption_package_fails(research):
    edit(_p(research, MAIN), "\\usepackage{subcaption}\n", "")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "subcaption" in r.out


def test_dangling_ref_fails(research):
    edit(_p(research, MAIN), "\\ref{tab:main}", "\\ref{tab:nowhere}")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "tab:nowhere" in r.out


def test_missing_input_file_fails(research):
    edit(_p(research, MAIN), "\\input{figs/fig_abl}", "\\input{figs/fig_gone}")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "input" in r.out


def test_stale_manuscript_fails(research):
    touch(_p(research, MAIN), +60)
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "比 LaTeX 源旧" in r.out


def test_state_class_mismatch_fails(research):
    edit(_p(research, MAIN), "{elsarticle}", "{IEEEtran}")
    r = run("latex_check.py", "check", cwd=research)
    assert r.fails >= 1 and "latex_class" in r.out


def test_width_mismatch_warns(research):
    edit(research / "figures.csv", "figures/fig_main.pdf,89,", "figures/fig_main.pdf,150,")
    r = run("latex_check.py", "check", cwd=research)
    assert "印刷宽度不一致" in r.out and "fig_main.pdf" in r.out


def test_no_latex_project_has_no_g6d(research):
    shutil.rmtree(research / "paper" / "latex")
    run("draft_plan.py", "plan", "--project", ".", cwd=research)
    r = run("t2p.py", "check", "--project", ".", cwd=research)
    assert "G6d" not in r.out and r.returncode == 0, r.out


# ------------------------------------------------------------------ skeleton
def test_skeleton_elsevier(tmp_path):
    r = run("latex_check.py", "skeleton", "--venue", "Engineering Applications of Artificial Intelligence", "--family", "cs_journal", "--project", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 0, r.out
    t = read(tmp_path / "paper" / "latex" / "main.tex")
    assert "\\documentclass[preprint,review,12pt]{elsarticle}" in t
    assert "\\usepackage{subcaption}" in t and "\\begin{frontmatter}" in t and "\\begin{subfigure}" in t
    assert "\\section{Introduction}" in t and "\\section{Related Work}" in t and "\\bibliography{../refs}" in t
    assert "\\graphicspath{{../../figures/}}" in t


def test_fresh_skeleton_passes_the_gate(tmp_path):
    """A skeleton has no figures yet (P5 makes them), so its figure examples must be commented out:
    a live \\includegraphics of a missing file made G6d FAIL on a freshly generated skeleton (found 2026-10-10)."""
    import io
    run("latex_check.py", "skeleton", "--venue", "Remote Sensing", "--project", str(tmp_path), cwd=tmp_path)
    t = read(tmp_path / "paper" / "latex" / "main.tex")
    live = [ln for ln in t.splitlines() if "includegraphics" in ln and not ln.lstrip().startswith("%")]
    assert not live, live
    assert "\\begin{subfigure}" in t and "P5 出图后取消注释" in t            # the example is still there to uncomment
    assert all(ln.lstrip().startswith("%") for ln in t.splitlines() if "subfigure}" in ln or "\\caption{<caption>}" in ln)
    io.open(tmp_path / "paper" / "refs.bib", "w", encoding="utf-8").write("@misc{x, title = {T}, year = {2026}, doi = {10.1/x}}\n")
    r = run("latex_check.py", "check", "--project", str(tmp_path), cwd=tmp_path)
    assert r.fails == 0, r.out


def test_skeleton_ieee_uses_subfig(tmp_path):
    r = run("latex_check.py", "skeleton", "--venue", "TPAMI", "--project", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 0, r.out
    t = read(tmp_path / "paper" / "latex" / "main.tex")
    assert "\\documentclass[journal]{IEEEtran}" in t and "{subfig}" in t and "\\subfloat[" in t and "\\columnwidth" in t


def test_skeleton_nature(tmp_path):
    r = run("latex_check.py", "skeleton", "--venue", "Nature Communications", "--project", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 0, r.out
    t = read(tmp_path / "paper" / "latex" / "main.tex")
    assert "{article}" in t and "\\section*{Results}" in t and "\\section*{Methods}" in t and "naturemag" in t


def test_skeleton_compiles_with_pdflatex(tmp_path):
    """The generated skeleton must be valid LaTeX: compile it when pdflatex and the class are installed (skip otherwise)."""
    import pytest, subprocess
    pdflatex = shutil.which("pdflatex")
    if not pdflatex or subprocess.run(["kpsewhich", "elsarticle.cls"], capture_output=True).returncode != 0:
        pytest.skip("pdflatex or elsarticle.cls not installed")
    run("latex_check.py", "skeleton", "--venue", "Information Fusion", "--title", "Compile test", "--project", str(tmp_path), cwd=tmp_path)
    from PIL import Image
    (tmp_path / "figures").mkdir()
    for n in ("fig_main", "fig_a", "fig_b"):
        Image.new("RGB", (400, 300), "white").save(tmp_path / "figures" / f"{n}.pdf", "PDF", resolution=300)
    r = subprocess.run([pdflatex, "-interaction=nonstopmode", "-halt-on-error", "main.tex"], cwd=str(tmp_path / "paper" / "latex"), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert r.returncode == 0, r.stdout[-1500:]
    assert (tmp_path / "paper" / "latex" / "main.pdf").exists()


def test_skeleton_refuses_to_overwrite(tmp_path):
    run("latex_check.py", "skeleton", "--venue", "TPAMI", "--project", str(tmp_path), cwd=tmp_path)
    r = run("latex_check.py", "skeleton", "--venue", "TPAMI", "--project", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 1 and "已存在" in r.out


# ------------------------------------------------------------------ figure block
def test_figure_block_from_panels(research):
    r = run("latex_check.py", "figure", "--panels", "figures/fig_abl_a.pdf,figures/fig_abl_b.pdf", "--labels", "First,Second",
            "--caption", "Composed.", "--label", "fig:t", "--out", "figs/fig_t.tex", cwd=research)
    assert r.returncode == 0, r.out
    t = read(research / "paper" / "latex" / "figs" / "fig_t.tex")
    assert t.count("\\begin{subfigure}") == 2 and "../../figures/fig_abl_a.pdf" in t and "\\label{fig:t-b}" in t and "\\caption{Composed.}" in t
    edit(_p(research, MAIN), "\\input{figs/fig_abl}", "\\input{figs/fig_abl}\n\\input{figs/fig_t}\nSee Fig.~\\ref{fig:t}.")
    touch(research / "paper" / "manuscript.md", +120)
    assert run("latex_check.py", "check", cwd=research).fails == 0


def test_figure_block_rejects_png_panel(research):
    r = run("latex_check.py", "figure", "--panels", "figures/fig_main.png,figures/fig_abl_b.pdf", cwd=research)
    assert r.returncode == 1 and "不是 PDF" in r.out


# ------------------------------------------------------------------ widths
def test_widths_article_class(research):
    r = run("latex_check.py", "widths", "--class", "article", "--options", "12pt", cwd=research)
    assert r.returncode == 0, r.out
    assert "textwidth" in r.out and "mm" in r.out            # measured when pdflatex is installed, table/default values otherwise


# ------------------------------------------------------------------ tex_to_md on a LaTeX project
def test_tex_to_md_expands_inputs_and_merges_figures_csv(research):
    r = run("tex_to_md.py", "paper/latex/main.tex", ".", "--bib", "paper/refs.bib", cwd=research)
    assert r.returncode == 0, r.out
    md = read(research / "paper" / "manuscript.md")
    assert "**Fig. 1.** Main comparison" in md and "**Fig. 2.** Ablations composed" in md and "(a) Removing the adversarial term" in md
    assert "**Table 1.**" in md and "Keywords: force estimation; domain shift; surgical robotics" in md
    assert "\\begin{frontmatter}" not in md and "Fixture University" not in md
    rows = {r["file"]: r for r in csv.DictReader(io.open(research / "figures.csv", encoding="utf-8-sig"))}
    assert rows["figures/fig_main.pdf"]["inspected"] == "yes" and rows["figures/fig_main.pdf"]["source_data"] == "results/summary.csv"
    assert rows["figures/fig_abl_a.pdf"]["print_width_mm"].startswith("91") and rows["figures/fig_main.png"]["inspected"] == "yes"   # earlier rows survive
    assert "he2016resnet" in read(research / "paper" / "refs.bib")             # the project bib is not rewritten with r1..rN keys


def test_tex_to_md_nested_tabular_preamble_and_number_math(research):
    """p{0.62\\columnwidth} / @{} in a tabular preamble must not leak into the table rows (the 0.62 would trip the numbers gate);
    inline math that is only a signed number ($-19$) is unwrapped so the number stays visible to the gates."""
    m = _p(research, MAIN)
    edit(m, "\\begin{tabular}{lcc}", "\\begin{tabular}{@{}p{0.62\\columnwidth}cc@{}}")
    edit(m, "\\section{Conclusion}", "The change is $-19$\\% on E1.\n\n\\section{Conclusion}")
    r = run("tex_to_md.py", "paper/latex/main.tex", ".", "--bib", "paper/refs.bib", cwd=research)
    assert r.returncode == 0, r.out
    md = read(research / "paper" / "manuscript.md")
    assert "0.62" not in md and "columnwidth" not in md
    assert "| baseA | 0.250 | 0.352 |" in md
    assert "-19% on E1" in md
