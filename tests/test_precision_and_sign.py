# -*- coding: utf-8 -*-
"""Regressions from cvpr2027_medical (2026-10-16).

1. G4 trace: results_check counted decimals as len(s.split(".")[1]), so "9.067581424695854e-05" had 19 "decimals" (the "e-05"
   included), round(v, 19) dropped a real digit and an exact copy of eval.json FAILed. Precision now comes from the Decimal exponent.
2. draft_plan number_pm1: a negative relative change only matched as "-4%"; "4% worse" (or "4% higher" for a lower-is-better
   metric) did not, and a positive "4%" matched inside "-4%". The ref-vs-baseline mean used seed 0 only; it now averages every
   seed all methods share and the checklist line names them."""
import json, sys

import pytest

from conftest import SCRIPTS, edit, read, run, write

sys.path.insert(0, str(SCRIPTS))
import draft_plan as dp
import results_check as rc

REAL = "9.067581424695854e-05"   # cvpr2027_medical results/main.csv


# ---------------------------------------------------------------- 1. G4 precision
@pytest.mark.parametrize("cell,v", [
    (REAL, float(REAL)),                 # the real case: an exact copy
    ("9.07e-05", float(REAL)),           # rounded to 3 significant digits
    ("9.0676E-5", float(REAL)),
    ("1.2E+3", 1234.5),                  # last printed digit is the hundreds
    ("0.12", 0.125),                     # tie at half a last digit
    ("0.200", 0.2), ("12", 12.3), ("-0.0976", -0.09759112429454998),
])
def test_cell_matches_printed_precision(cell, v):
    assert rc.cell_matches(cell, v)


@pytest.mark.parametrize("cell,v", [
    ("9.08e-05", float(REAL)), ("9.067581424695855e-05", float(REAL) * (1 + 1e-12)), ("1.1E+3", 1234.5),
    ("0.13", 0.12), ("n/a", 0.1), ("9.067581424695854e-04", float(REAL)),
])
def test_cell_mismatch_still_fails(cell, v):
    assert not rc.cell_matches(cell, v)


def _tiny_column(research, cell, value):
    """an extra metric column filled only on ours_s0, mapped to a tiny value in its eval.json"""
    mc = research / "results" / "main.csv"
    lines = read(mc).splitlines()
    write(mc, "\n".join([lines[0] + ",drift"] + [l + ("," + cell if l.startswith("ours_s0,") else ",") for l in lines[1:]]) + "\n")
    ev = research / "runs" / "ours_s0" / "eval.json"
    d = json.loads(read(ev)); d["E1"]["drift"] = value; write(ev, json.dumps(d))
    edit(research / "research-state.yaml", "metric_map: {rmse_E1: E1.rmse, rmse_E2: E2.rmse}", "metric_map: {rmse_E1: E1.rmse, rmse_E2: E2.rmse, drift: E1.drift}")


def test_g4_scientific_notation_cell_passes(research):
    _tiny_column(research, REAL, float(REAL))
    r = run("results_check.py", cwd=research)
    assert r.fails == 0 and not r.crashed, r.out


def test_g4_scientific_notation_mismatch_fails(research):
    _tiny_column(research, "9.2e-05", float(REAL))
    r = run("results_check.py", cwd=research)
    assert r.fails >= 1 and "ours_s0.drift = 9.2e-05" in r.out, r.out


# ---------------------------------------------------------------- 2. number_pm1 sign
WORSE_LOWER = dp.direction_words(False, True)    # ref worse on a lower-is-better metric: "worse", "higher", ...
BETTER_LOWER = dp.direction_words(True, True)


@pytest.mark.parametrize("text", [
    "Ours has a -4% relative change.", "Ours: −4% versus base.", "RMSE is -3.6% relative to base.",
    "Ours is 4% worse than base.", "Its RMSE is 5% higher than base.", "Ours trails base by 3%.",
])
def test_negative_change_signed_or_with_direction_word(text):
    assert dp.pct_change_stated(-4, text, WORSE_LOWER), text


@pytest.mark.parametrize("text", [
    "Ours is 4% better than base.",                        # wrong direction word
    "Ours changes RMSE by 4%.",                            # no direction word
    "Ours is 4%. It is worse on E2.",                      # direction word in another sentence
])
def test_negative_change_needs_the_right_word_in_the_same_sentence(text):
    assert not dp.pct_change_stated(-4, text, WORSE_LOWER), text


def test_negative_change_old_plan_without_dir_is_signed_only():
    assert dp.pct_change_stated(-4, "Ours: -4%.") and not dp.pct_change_stated(-4, "Ours is 4% worse.")


def test_positive_change_is_not_matched_inside_a_negative_one():
    assert not dp.pct_change_stated(4, "Ours is -4% versus base.", BETTER_LOWER)
    assert not dp.pct_change_stated(4, "Ours is −5% versus base.", BETTER_LOWER)
    for text in ("Ours reduces RMSE by 4%.", "Ours: +4%.", "a 3-4% reduction", "(4%)"):
        assert dp.pct_change_stated(4, text, BETTER_LOWER), text


# ---------------------------------------------------------------- 2. seed averaging
# seed 0 alone: ours 0.300 vs base 0.250 -> -20 %. All shared seeds: 0.2333 vs 0.250 -> +7 %.
# base seed 3 exists only for base; counting it would make base 0.4375 and the change +47 %.
SEEDS = ("run_id,method,seed,rmse\n"
         "o0,ours,0,0.300\no1,ours,1,0.200\no2,ours,2,0.200\n"
         "b0,base,0,0.250\nb1,base,1,0.250\nb2,base,2,0.250\nb3,base,3,1.000\n")


def _plan(tmp_path, main):
    write(tmp_path / "results" / "main.csv", main)
    write(tmp_path / "research-state.yaml", "results:\n  main_table: results/main.csv\n  primary_metric: rmse\n  primary_direction: lower\n"
          "  group_key: method\n  reference_method: ours\n")
    r = run("draft_plan.py", "plan", "--project", ".", cwd=tmp_path)
    assert r.returncode == 0 and not r.crashed, r.out
    return [i for i in json.loads(read(tmp_path / "paper" / "draft_plan.json")) if i["kind"] == "number_pm1"][0]


def test_relative_change_averages_shared_seeds(tmp_path):
    it = _plan(tmp_path, SEEDS)
    assert it["probe"] == "7", it
    assert "3 个共同 seed 的均值（seed 0, 1, 2）" in it["must"] and "不计" in it["must"], it["must"]


def test_relative_change_without_seed_column(tmp_path):
    it = _plan(tmp_path, "run_id,method,rmse\no,ours,0.24\nb,base,0.25\n")
    assert it["probe"] == "4" and "无 seed 列" in it["must"], it


def test_negative_change_end_to_end(tmp_path):
    """ours worse than base on a lower-is-better metric: the plan asks for -4 %, "4% higher" in Results satisfies it"""
    it = _plan(tmp_path, "run_id,method,seed,rmse\no0,ours,0,0.26\no1,ours,1,0.26\nb0,base,0,0.25\nb1,base,1,0.25\n")
    assert it["probe"] == "-4" and it["dir"], it
    write(tmp_path / "paper" / "manuscript.md", "# T\n\n## Results\n\nOurs has a 4% higher RMSE than base.\n")
    r = run("draft_plan.py", "check", "--project", ".", cwd=tmp_path)
    assert f"[PASS] {it['id']}" in r.out, r.out
    write(tmp_path / "paper" / "manuscript.md", "# T\n\n## Results\n\nOurs has a 4% lower RMSE than base.\n")
    r = run("draft_plan.py", "check", "--project", ".", cwd=tmp_path)
    assert f"[PASS] {it['id']}" not in r.out, r.out
