# -*- coding: utf-8 -*-
"""Metric direction (metric_direction.py, 2026-10-15): draft_plan picks the "strongest baseline" as min or max of the primary
metric. delta_rel_Ta (a cross-protocol relative drop, lower is better) matched no lower-is-better name, so draft_plan took the
max, named the WORST method (coral) and demanded "pde vs coral ≈ -63 %" while the real strongest alternative is zstd (pde 23 %
lower). Direction now comes from results.metric_direction / primary_direction, then the name regex."""
import json, sys

import pytest

from conftest import SCRIPTS, edit, read, run, write

sys.path.insert(0, str(SCRIPTS))
import metric_direction as mdir

MAIN = "run_id,method,seed,{m}\npde_s0,pde,0,0.100\ncoral_s0,coral,0,0.400\nzstd_s0,zstd,0,0.130\nnone_s0,none,0,0.250\n"


def _project(tmp_path, metric, extra=""):
    write(tmp_path / "results" / "main.csv", MAIN.format(m=metric))
    write(tmp_path / "research-state.yaml", "results:\n  main_table: results/main.csv\n  primary_metric: " + metric +
          "\n  group_key: method\n  reference_method: pde\n" + extra)
    return tmp_path


def _strongest(project):
    r = run("draft_plan.py", "plan", "--project", ".", cwd=project)
    assert r.returncode == 0 and not r.crashed, r.out
    items = json.loads(read(project / "paper" / "draft_plan.json"))
    name = [i for i in items if i["source"] == "main.csv 主指标" and i["kind"] == "name"]
    rel = [i for i in items if i["source"] == "main.csv 主指标" and i["kind"] == "number_pm1"]
    assert len(name) == 1 and len(rel) == 1, items
    return name[0]["probe"], int(rel[0]["probe"])


@pytest.mark.parametrize("extra", ["  primary_direction: lower\n", "  metric_direction: {cross_protocol_Ta: lower}\n"])
def test_explicit_lower_picks_minimum(tmp_path, extra):
    """a name no regex knows: the explicit key decides, and the strongest baseline is the minimum (zstd), pde 23 % lower"""
    assert mdir.direction("cross_protocol_Ta") is None
    assert _strongest(_project(tmp_path, "cross_protocol_Ta", extra)) == ("zstd", 23)


def test_unknown_name_without_key_falls_back_to_higher(tmp_path):
    """the old default, kept for names the regex cannot place; G4 WARNs about it (test_g4_direction_*)"""
    assert _strongest(_project(tmp_path, "cross_protocol_Ta"))[0] == "coral"


def test_delta_name_defaults_to_lower(tmp_path):
    """the cvpr2027_medical case without any state key: delta/drop/shift/gap/... are lower-is-better by default"""
    for m in ("delta_rel_Ta", "acc_drop", "domain_shift", "gen_gap", "auc_degradation", "dice_decline", "asr"):
        assert mdir.direction(m) == "lower", m
    assert _strongest(_project(tmp_path, "delta_rel_Ta")) == ("zstd", 23)


def test_explicit_key_overrides_regex(tmp_path):
    """per-column map > primary_direction > regex: a 'delta' column that is a gain can be declared higher"""
    p = _project(tmp_path, "delta_rel_Ta", "  primary_direction: lower\n  metric_direction: {delta_rel_Ta: higher}\n")
    assert _strongest(p)[0] == "coral"


def test_invalid_direction_fails_cleanly(tmp_path):
    r = run("draft_plan.py", "plan", "--project", ".", cwd=_project(tmp_path, "delta_rel_Ta", "  primary_direction: sideways\n"))
    assert r.returncode != 0 and not r.crashed and "[FAIL]" in r.out and "sideways" in r.out, r.out


def test_make_comparison_seeds_bolds_minimum_for_lower(tmp_path):
    """seeds table used to bold max() unconditionally; with the direction from --project it bolds the lowest mean"""
    _project(tmp_path, "delta_rel_Ta", "  primary_direction: lower\n")
    write(tmp_path / "results" / "seeds.csv", "setting,seed,delta_rel_Ta\npde,0,0.10\npde,1,0.12\ncoral,0,0.40\ncoral,1,0.42\n")
    r = run("make_comparison.py", "seeds", "--csv", "results/seeds.csv", "--out", "tab_seeds.tex", "--metrics", "delta_rel_Ta",
            "--project", ".", "--md", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    tex = read(tmp_path / "tab_seeds.tex")
    assert r"\textbf{pde}" in tex and r"\textbf{coral}" not in tex, tex


def test_make_comparison_ablation_honours_lower(tmp_path):
    """ablation tables ignored --lower: an error column was ranked as if higher were better"""
    write(tmp_path / "abl.csv", "A,B,rmse\n1,0,0.30\n0,1,0.20\n1,1,0.10\n")
    r = run("make_comparison.py", "ablation", "--csv", "abl.csv", "--out", "tab.tex", "--components", "A,B", "--metrics", "rmse",
            "--lower", "rmse", "--md", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    best = [l for l in read(tmp_path / "tab.tex").splitlines() if r"\textcolor{red}" in l]
    assert len(best) == 1 and "0.100" in best[0], best


def test_ablation_sign_flip_reads_state():
    """prereg signs are in error convention; a higher-is-better column flips them, an explicit lower does not"""
    sys.path.insert(0, str(SCRIPTS)); import ablation_plan as ap
    assert ap.sign_for_metric("+", "auc") == "-"
    assert ap.sign_for_metric("+", "auc", {"metric_direction": {"auc": "lower"}}) == "+"
    assert ap.sign_for_metric("+", "cross_protocol_Ta", {"primary_metric": "cross_protocol_Ta", "primary_direction": "higher"}) == "-"


def test_g4_direction_invalid_fails(research):
    edit(research / "research-state.yaml", "  primary_metric: rmse_E1\n  min_seeds", "  primary_metric: rmse_E1\n  primary_direction: sideways\n  min_seeds")
    r = run("results_check.py", cwd=research)
    assert r.fails >= 1 and "sideways" in r.out, r.out


def test_g4_direction_unguessable_warns(research):
    """fixture primary metric renamed to a column the regex cannot place: WARN, and the WARN goes once the key is set"""
    st = research / "research-state.yaml"
    edit(st, "  primary_metric: rmse_E1\n  min_seeds", "  primary_metric: cross_protocol_Ta\n  min_seeds")
    r = run("results_check.py", cwd=research)
    assert "primary_direction" in r.out, r.out
    edit(st, "  primary_metric: cross_protocol_Ta\n", "  primary_metric: cross_protocol_Ta\n  primary_direction: lower\n")
    assert "results.primary_direction 写" not in run("results_check.py", cwd=research).out
