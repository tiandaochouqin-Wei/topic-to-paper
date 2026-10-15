# -*- coding: utf-8 -*-
"""tests for validation round 17: make_figure curves, --lower direction, routing has no dangling skill."""
from conftest import edit, read, run, write
import csv, io, os


def _curves_csv(path):
    rows = ["dataset,method,seed,epoch,val_loss"]
    for ds in ("A", "B"):
        for m, base in (("ours", 1.0), ("ref", 1.2)):
            for s in (0, 1, 2):
                for e in (1, 2, 4, 8):
                    rows.append(f"{ds},{m},{s},{e},{base / e + 0.01 * s:.4f}")
    write(path, "\n".join(rows) + "\n")


def test_curves_writes_pdf_source_and_registers(research):
    _curves_csv(research / "results" / "curves.csv")
    r = run("make_figure.py", "curves", "--project", ".", "--csv", "results/curves.csv", "--out", "figures/fig_curves.png",
            "--x", "epoch", "--y", "val_loss", "--series", "method", "--panel", "dataset", "--ours", "ours", "--width-mm", "88", cwd=research)
    assert r.returncode == 0, r.out
    for ext in (".png", ".pdf", ".source.csv"):
        assert os.path.exists(research / "figures" / ("fig_curves" + ext)), ext
    src = list(csv.DictReader(io.open(research / "figures" / "fig_curves.source.csv", encoding="utf-8")))
    assert {s["panel"] for s in src} == {"A", "B"} and {s["series"] for s in src} == {"ours", "ref"}
    assert all(s["n"] == "3" for s in src), "three seeds per point should be collapsed"
    assert any(s["file"] == "figures/fig_curves.png" for s in csv.DictReader(io.open(research / "figures.csv", encoding="utf-8-sig")))


def test_curves_fails_on_missing_column(research):
    _curves_csv(research / "results" / "curves.csv")
    r = run("make_figure.py", "curves", "--project", ".", "--csv", "results/curves.csv", "--out", "figures/f.png", "--x", "epoch", "--y", "nope", cwd=research)
    assert r.returncode != 0 and "column nope" in r.out, r.out


def test_main_best_flag_follows_lower(research):
    """fixture: ours rmse 0.20 < baseA 0.25; without --lower the higher rmse would be 'best'"""
    r = run("make_figure.py", "main", "--project", ".", "--out", "figures/fig_m.png", "--metrics", "rmse_E1", "--lower", "rmse_E1", cwd=research)
    assert r.returncode == 0, r.out
    src = {s["method"]: s["best"] for s in csv.DictReader(io.open(research / "figures" / "fig_m.source.csv", encoding="utf-8"))}
    assert src["ours"] == "True" and all(v == "False" for k, v in src.items() if k != "ours"), src
    r = run("make_figure.py", "main", "--project", ".", "--out", "figures/fig_m2.png", "--metrics", "rmse_E1", cwd=research)
    src = {s["method"]: s["best"] for s in csv.DictReader(io.open(research / "figures" / "fig_m2.source.csv", encoding="utf-8"))}
    assert src["ours"] == "True", "without --lower, rmse is lower-is-better by name (metric_direction.py)"
    edit(research / "research-state.yaml", "  primary_metric: rmse_E1\n", "  primary_metric: rmse_E1\n  metric_direction: {rmse_E1: higher}\n")
    r = run("make_figure.py", "main", "--project", ".", "--out", "figures/fig_m3.png", "--metrics", "rmse_E1", cwd=research)
    src = {s["method"]: s["best"] for s in csv.DictReader(io.open(research / "figures" / "fig_m3.source.csv", encoding="utf-8"))}
    assert src["ours"] == "False", "state.results.metric_direction overrides the name regex"


def test_comparison_seeds_bold_follows_lower(tmp_path):
    write(tmp_path / "s.csv", "setting,seed,nll\nbase,0,0.10\nbase,1,0.12\nipw,0,0.20\nipw,1,0.22\n")
    r = run("make_comparison.py", "seeds", "--csv", tmp_path / "s.csv", "--out", tmp_path / "t.tex", "--metrics", "nll", "--lower", "nll", cwd=tmp_path)
    assert r.returncode == 0, r.out
    tex = read(tmp_path / "t.tex")
    assert "\\textbf{base}" in tex and "\\textbf{ipw}" not in tex, tex
    r = run("make_comparison.py", "seeds", "--csv", tmp_path / "s.csv", "--out", tmp_path / "t2.tex", "--metrics", "nll", cwd=tmp_path)
    assert "\\textbf{base}" in read(tmp_path / "t2.tex"), "nll is lower-is-better by name (metric_direction.py) even without --lower"
    write(tmp_path / "u.csv", "setting,seed,score\nbase,0,0.10\nbase,1,0.12\nipw,0,0.20\nipw,1,0.22\n")
    r = run("make_comparison.py", "seeds", "--csv", tmp_path / "u.csv", "--out", tmp_path / "t3.tex", "--metrics", "score", cwd=tmp_path)
    assert "\\textbf{ipw}" in read(tmp_path / "t3.tex"), "a name no regex knows stays higher-is-better"


def test_routing_names_only_installed_or_bundled_skills():
    """P5/routing must not send the writer to a skill that is not shipped with this repo or standard;
    the default non-standard-data-figure route is scipilot-figure-skill (round 17b)"""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for rel in ("references/phases/P5.md", "references/routing.md"):
        txt = read(os.path.join(root, rel))
        assert "cs-experiment-figure-studio" not in txt, rel
        assert "scipilot-figure-skill" in txt, rel
