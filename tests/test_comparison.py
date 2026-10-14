# -*- coding: utf-8 -*-
"""make_comparison.py: row names and dataset headers with inline math (found in a real TPAMI project, validation round 12)."""
from conftest import read, run, write


def test_esc_leaves_inline_math_alone(tmp_path):
    write(tmp_path / "m.csv", 'method,task,worst,size\n'
                              'Single-rater CRC,prostate_t1,0.129,0.995\n'
                              '"REC, $\\delta = 1/(K_{\\mathrm{cal}}+1)$",prostate_t1,0.107,1.072\n')
    r = run("make_comparison.py", "sota", "--csv", tmp_path / "m.csv", "--out", tmp_path / "t.tex", "--metrics", "worst,size", "--lower", "worst,size", "--name-col", "method", cwd=tmp_path)
    assert r.returncode == 0, r.out
    tex = read(tmp_path / "t.tex")
    assert "$\\delta = 1/(K_{\\mathrm{cal}}+1)$" in tex and "K\\_{" not in tex     # inline math passes through untouched
    assert "Single-rater CRC" in tex


def test_plain_identifiers_are_still_escaped(tmp_path):
    write(tmp_path / "m.csv", "method,task,worst\nrec_quantile,prostate_t1,0.1\nother_method,prostate_t1,0.2\n")
    r = run("make_comparison.py", "sota", "--csv", tmp_path / "m.csv", "--out", tmp_path / "t.tex", "--metrics", "worst", "--lower", "worst", cwd=tmp_path)
    assert r.returncode == 0, r.out
    assert "rec\\_quantile" in read(tmp_path / "t.tex")


def test_dataset_labels_in_tex_and_md(tmp_path):
    write(tmp_path / "m.csv", "method,task,worst\nA,prostate_t1,0.1\nA,kidney_t1,0.2\nB,prostate_t1,0.3\nB,kidney_t1,0.4\n")
    r = run("make_comparison.py", "multi", "--csv", tmp_path / "m.csv", "--out", tmp_path / "t.tex", "--md", "--metrics", "worst", "--lower", "worst",
            "--datasets", "prostate_t1,kidney_t1", "--dataset-col", "task", "--dataset-labels", "prostate_t1=Prostate ($K{=}6$),kidney_t1=Kidney ($K{=}3$)", cwd=tmp_path)
    assert r.returncode == 0, r.out
    tex, md = read(tmp_path / "t.tex"), read(tmp_path / "t.md")
    assert "Prostate ($K{=}6$)" in tex and "prostate\\_t1" not in tex
    assert "Prostate (K{=}6) worst" in md and "prostate_t1" not in md


def test_multi_without_dataset_labels_keeps_escaped_identifiers(tmp_path):
    write(tmp_path / "m.csv", "method,task,worst\nA,prostate_t1,0.1\nB,prostate_t1,0.3\n")
    r = run("make_comparison.py", "multi", "--csv", tmp_path / "m.csv", "--out", tmp_path / "t.tex", "--metrics", "worst", "--lower", "worst", "--datasets", "prostate_t1", "--dataset-col", "task", cwd=tmp_path)
    assert r.returncode == 0, r.out
    assert "prostate\\_t1" in read(tmp_path / "t.tex")
