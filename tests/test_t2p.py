# -*- coding: utf-8 -*-
"""t2p.py front door: the status board on the two fixtures, and the rule that a crashed gate is never a PASS."""
import importlib.util

from conftest import SCRIPTS, edit, run, write


def _t2p():
    spec = importlib.util.spec_from_file_location("t2p", SCRIPTS / "t2p.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_run_reports_crash_not_pass(tmp_path):
    t2p = _t2p()
    bad = tmp_path / "bad.py"; write(bad, "print('[PASS] looks fine')\nraise RuntimeError('boom')\n")
    rc, fails, warns, out = t2p.run([str(bad)], str(tmp_path))
    assert rc != 0 and fails == 0
    assert out.startswith("[CRASH]"), out
    assert t2p.verdict(fails, out) == "CRASH"


def test_run_nonzero_exit_without_fail_line_is_crash(tmp_path):
    t2p = _t2p()
    bad = tmp_path / "bad.py"; write(bad, "import sys; print('usage: wrong args'); sys.exit(2)\n")
    rc, fails, warns, out = t2p.run([str(bad)], str(tmp_path))
    assert t2p.verdict(fails, out) == "CRASH"


def test_run_fail_and_pass_verdicts(tmp_path):
    t2p = _t2p()
    f = tmp_path / "f.py"; write(f, "import sys; print('[FAIL] x: bad'); print('[WARN] y'); sys.exit(1)\n")
    p = tmp_path / "p.py"; write(p, "print('[PASS] x: good')\n")
    rc, fails, warns, out = t2p.run([str(f)], str(tmp_path)); assert (fails, warns) == (1, 1) and t2p.verdict(fails, out) == "FAIL"
    rc, fails, warns, out = t2p.run([str(p)], str(tmp_path)); assert fails == 0 and t2p.verdict(fails, out) == "PASS"


def test_research_board_all_pass(research):
    assert run("draft_plan.py", "plan", "--project", ".", cwd=research).returncode == 0
    r = run("t2p.py", "check", "--project", ".", cwd=research)
    assert "[FAIL]" not in r.out and "[CRASH]" not in r.out, r.out
    for g in ("G0", "G1b", "G2", "G3", "G4", "G5", "G6", "G6b", "G6c", "G6e", "G7", "G8"):
        assert f"[PASS] {g}:" in r.out, f"{g} not PASS\n{r.out}"
    assert "[SKIP] G1:" in r.out            # bib exists, DOI resolution needs --net
    assert r.returncode == 0, r.out


def test_crashed_gate_shows_as_crash_on_the_board(research):
    """A non-numeric cell makes results_check.py and ablation_plan.py resolve raise ValueError. Neither prints a [FAIL] line,
    so the old board reported G4 as PASS; it must read CRASH and count towards the exit code."""
    edit(research / "results" / "ablation.csv", "no_cons,abl_no_cons,0,A2000,0.203,0.304", "no_cons,abl_no_cons,0,A2000,0.203,n/a")
    r = run("t2p.py", "check", "--project", ".", cwd=research)
    assert "[CRASH] G4:" in r.out, r.out
    assert "[PASS] G4:" not in r.out
    assert r.returncode >= 1


def test_survey_board_all_pass(survey):
    r = run("t2p.py", "check", "--project", ".", cwd=survey)
    assert "[FAIL]" not in r.out and "[CRASH]" not in r.out, r.out
    for g in ("G0", "G-S0", "G-S1", "G-S2", "G-S3", "G-S4", "G-S5"):
        assert f"[PASS] {g}:" in r.out, f"{g} not PASS\n{r.out}"
    assert "] G2:" not in r.out and "] G3:" not in r.out and "] G4:" not in r.out    # research-only gates are hidden for a survey
    assert r.returncode == 0, r.out
