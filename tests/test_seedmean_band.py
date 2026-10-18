# -*- coding: utf-8 -*-
"""validation round 20: ablation noise band scales with the number of seeds an ablation row averages."""
from conftest import read, run, write
import csv, io, os


def _abl(research, text):
    write(research / "results" / "ablation.csv", text)


def test_resolve_single_run_unchanged(research):
    """fixture rows are single runs: the historical σ√2 rule and wording stay"""
    r = run("ablation_plan.py", "resolve", cwd=research)
    assert "|Δ| ≥ 2·σ_ref·√2）" in r.out and "n=" not in r.out.split("可解读格")[0].split("σ_ref:")[-1], r.out


def test_resolve_per_seed_rows_resolve_a_small_mean_shift(research):
    """no_cons mean 0.206 vs ref 0.202 (σ_ref 0.002, 3 seeds): single run z≈1.4 (not), 5-seed mean z≈2.7 (resolvable)"""
    rows = ["ablation,run_id,seed,hardware,rmse_E1,rmse_E2", "no_dom,abl_no_dom,0,A2000,0.250,0.355"]
    rows += [f"no_cons,abl_no_cons_s{s},{s},A2000,{v},0.304" for s, v in enumerate([0.205, 0.206, 0.207, 0.206, 0.206])]
    _abl(research, "\n".join(rows) + "\n")
    r = run("ablation_plan.py", "resolve", cwd=research)
    line = next(l for l in r.out.splitlines() if l.startswith("no_cons"))
    assert "(n=5)" in line and "~" not in line.split()[1], line
    assert "√(1/n+1/n_ref)" in r.out, r.out


def test_resolve_n_seeds_column_is_honoured(research):
    _abl(research, "ablation,run_id,seed,hardware,n_seeds,rmse_E1,rmse_E2\nno_dom,abl_no_dom,mean,A2000,1,0.250,0.355\nno_cons,abl_no_cons,mean,A2000,5,0.206,0.304\n")
    r = run("ablation_plan.py", "resolve", cwd=research)
    line = next(l for l in r.out.splitlines() if l.startswith("no_cons"))
    assert "(n=5)" in line, line


def test_figure_band_shrinks_for_seed_means(research):
    _abl(research, "ablation,run_id,seed,hardware,n_seeds,rmse_E1,rmse_E2\nno_dom,abl_no_dom,mean,A2000,1,0.250,0.355\nno_cons,abl_no_cons,mean,A2000,5,0.206,0.304\n")
    r = run("make_figure.py", "ablation", "--project", ".", "--out", "figures/fig_ab.png", "--metrics", "rmse_E1", cwd=research)
    assert r.returncode == 0, r.out
    src = {s["ablation"]: s for s in csv.DictReader(io.open(research / "figures" / "fig_ab.source.csv", encoding="utf-8"))}
    assert float(src["no_cons"]["band"]) < float(src["no_dom"]["band"]), src
    assert src["no_cons"]["n_seeds"] == "5" and src["no_cons"]["resolvable"] == "True", src
