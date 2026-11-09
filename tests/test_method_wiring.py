# -*- coding: utf-8 -*-
"""Method track wiring: the three gates G1c / G2m / G4m on the t2p.py board, `init --paper-type`, and the prereg_check rules.
The gate logic itself (method_track.py) is tested in test_method_track.py; here only the front door is exercised, on the
research_min fixture with `project.paper_type` flipped."""
import json
import re

import yaml

from conftest import SKILL, edit, lock, read, run, write

METHOD = ("G1c", "G2m", "G4m")
SHA = "0123456789abcdef" * 4


def _state(p):
    return yaml.safe_load(read(p / "research-state.yaml"))


def _as_method(p):
    edit(p / "research-state.yaml", "  entry: topic_only\n", "  entry: topic_only\n  paper_type: method\n")


def _append_state(p, text):
    write(p / "research-state.yaml", read(p / "research-state.yaml").rstrip("\n") + "\n" + text)


def _board(p, *extra):
    return run("t2p.py", "check", "--project", ".", "--no-write", *extra, cwd=p)


def _line(r, gate):
    m = re.search(rf"(?m)^\[(\w[\w/]*)\] {gate}: (.*)$", r.out)
    return (m.group(1), m.group(2)) if m else (None, None)


# ------------------------------------------------------------------ visibility
def test_analysis_board_has_no_method_gates(research):
    r = _board(research)
    for g in METHOD:
        assert f"] {g}:" not in r.out, r.out
    assert r.returncode == 0, r.out


def test_analysis_ignores_a_method_block(research):
    """a filled method: block does nothing unless paper_type is method"""
    _append_state(research, 'method: {benchmark: {name: "COCO"}, baseline: {name: "X", code: "c"}}')
    r = _board(research)
    for g in METHOD:
        assert f"] {g}:" not in r.out, r.out
    assert r.returncode == 0, r.out


def test_survey_never_shows_method_gates(survey):
    edit(survey / "research-state.yaml", "  entry: topic_only\n", "  entry: topic_only\n  paper_type: method\n")
    r = _board(survey)
    for g in METHOD:
        assert f"] {g}:" not in r.out, r.out


def test_method_project_shows_three_pending_gates_in_order(research):
    _as_method(research)
    r = _board(research)
    for g in METHOD:
        assert _line(r, g)[0] == "PENDING", f"{g}\n{r.out}"
    pos = {g: r.out.index(f"] {g}:") for g in METHOD + ("G1b", "G2", "G4", "G5")}
    assert pos["G1b"] < pos["G1c"] < pos["G2m"] < pos["G2"], r.out        # headroom before designing, dev loop before the lock
    assert pos["G4"] < pos["G4m"] < pos["G5"], r.out
    assert "method_track.py init" in _line(r, "G1c")[1]
    assert _line(r, "G2")[0] == "FAIL", r.out                              # the fixture prereg is locked and there is no state.method.freeze: "freeze before lock"


def test_method_gates_are_na_for_draft_entry(research):
    _as_method(research)
    edit(research / "research-state.yaml", "  entry: topic_only\n", "  entry: have_draft\n")
    r = _board(research)
    for g in METHOD:
        assert _line(r, g)[0] == "N/A", f"{g}\n{r.out}"


def test_check_writes_method_gates_into_state(research):
    _as_method(research)
    run("t2p.py", "check", "--project", ".", cwd=research)
    gates = _state(research)["gates"]
    assert all(g in gates and gates[g]["status"] == "pending" for g in METHOD), gates


# ------------------------------------------------------------------ the gates run once their inputs exist
def test_g1c_runs_when_state_method_is_started(research):
    _as_method(research)
    _append_state(research, 'method: {benchmark: {name: "COCO"}}')
    r = _board(research)
    st, msg = _line(r, "G1c")
    assert st == "FAIL" and "headroom" in msg, r.out                       # the rest of the block is empty: method_track.py headroom FAILs
    assert r.returncode >= 1


def test_g2m_pending_while_iterations_has_only_a_commented_example(research):
    _as_method(research)
    write(research / "method" / "iterations.csv", "id,date,hypothesis,change,runs\n# I01,2026-11-10,h,c,runs/i01_s*\n")
    assert _line(_board(research), "G2m")[0] == "PENDING"


def test_g2m_runs_once_an_iteration_row_exists(research):
    _as_method(research)
    write(research / "method" / "iterations.csv", "id,date,hypothesis,change,runs\nI01,2026-11-10,h,c,runs/nothing_s*\n")
    st, msg = _line(_board(research), "G2m")
    assert st == "FAIL" and "dev-check" in msg and "K=1" in msg and "未冻结" in msg, msg


def test_g4m_pending_until_a_confirm_run_exists_then_runs(research):
    _as_method(research)
    assert _line(_board(research), "G4m")[0] == "PENDING"
    d = research / "runs" / "conf_s0"
    write(d / "args.json", json.dumps({"eval_split": "dev", "role": "ours"}))
    assert _line(_board(research), "G4m")[0] == "PENDING"                  # a dev run is not a confirmation
    write(d / "args.json", json.dumps({"eval_split": "confirm", "role": "ours"}))
    st, msg = _line(_board(research), "G4m")
    assert st == "FAIL" and "confirm-check" in msg, msg                    # no freeze yet: confirm-check FAILs, the board says so


# ------------------------------------------------------------------ init / status
def test_init_paper_type_method(tmp_path):
    proj = tmp_path / "m"
    r = run("t2p.py", "init", "--project", str(proj), "--venue", "CVPR", "--field", "cv", "--paper-type", "method", cwd=tmp_path)
    assert r.returncode == 0, r.out
    assert "paper_type=method" in r.out and "method-track.md" in r.out, r.out
    st = _state(proj)
    assert st["project"]["paper_type"] == "method" and "method" in st and st["method"]["budget"]["max_iters"] == 30
    c = run("t2p.py", "check", "--project", ".", cwd=proj)
    assert all(_line(c, g)[0] == "PENDING" for g in METHOD), c.out
    s = run("t2p.py", "status", "--project", ".", cwd=proj)
    assert "类型: method" in s.out and "G1c" in s.out, s.out


def test_init_default_is_analysis_and_hides_the_gates(tmp_path):
    proj = tmp_path / "a"
    r = run("t2p.py", "init", "--project", str(proj), "--venue", "CVPR", cwd=tmp_path)
    assert r.returncode == 0 and "paper_type=analysis" in r.out and "method-track" not in r.out, r.out
    assert _state(proj)["project"]["paper_type"] == "analysis"
    c = run("t2p.py", "check", "--project", ".", cwd=proj)
    assert not any(f"] {g}:" in c.out for g in METHOD), c.out
    assert "类型: method" not in run("t2p.py", "status", "--project", ".", cwd=proj).out


def test_init_method_survey_is_refused(tmp_path):
    proj = tmp_path / "s"
    r = run("t2p.py", "init", "--project", str(proj), "--branch", "survey", "--paper-type", "method", cwd=tmp_path)
    assert r.returncode == 1 and "[FAIL]" in r.out and not proj.exists(), r.out


def test_init_rejects_an_unknown_paper_type(tmp_path):
    r = run("t2p.py", "init", "--project", str(tmp_path / "x"), "--paper-type", "theory", cwd=tmp_path)
    assert r.returncode == 2, r.out


# ------------------------------------------------------------------ prereg_check
def _prereg(p, *args):
    return run("prereg_check.py", *args, cwd=p)


def test_prereg_analysis_unchanged(research):
    r = _prereg(research)
    assert r.fails == 0 and "freeze" not in r.out, r.out


def test_prereg_method_locked_before_freeze_fails(research):
    _as_method(research)
    r = _prereg(research)
    assert r.fails == 1 and "方法轨道先 freeze 再锁预注册" in r.out, r.out
    assert "[WARN] prereg: 方法轨道：prereg 没有 `freeze: <sha8>`" in r.out


def test_prereg_method_after_freeze_passes(research):
    _as_method(research)
    _append_state(research, f'method: {{freeze: {{date: "2026-11-09", iteration: I12, code_sha256: "{SHA}"}}}}')
    write(research / "prereg.md", read(research / "prereg.md").rstrip("\n") + "\n\n方法轨道补充：freeze: 01234567\n")
    lock(research, "prereg.md", "prereg_sha256")
    r = _prereg(research)
    assert r.fails == 0 and "freeze" not in r.out.replace("方法轨道", ""), r.out


def test_prereg_method_freeze_sha_mismatch_warns(research):
    _as_method(research)
    _append_state(research, f'method: {{freeze: {{date: "2026-11-09", iteration: I12, code_sha256: "{SHA}"}}}}')
    write(research / "prereg.md", read(research / "prereg.md").rstrip("\n") + "\n\nfreeze: deadbeef\n")
    lock(research, "prereg.md", "prereg_sha256")
    r = _prereg(research)
    assert r.fails == 0 and "[WARN]" in r.out and "deadbeef" in r.out and "01234567" in r.out, r.out


def test_prereg_dev_runs_before_the_lock_are_post_hoc_only_for_analysis(research):
    """11 runs exist and the prereg is not locked: analysis FAILs as post-hoc; the method track expects dev runs before the lock"""
    edit(research / "research-state.yaml", re.search(r'prereg_sha256: "[0-9a-f]+"', read(research / "research-state.yaml")).group(0), 'prereg_sha256: ""')
    assert "事后注册" in _prereg(research).out
    _as_method(research)
    r = _prereg(research)
    assert "事后注册" not in r.out and r.fails == 0, r.out


def test_prereg_template_carries_the_method_block():
    t = read(SKILL / "templates" / "prereg.md")
    assert "方法轨道补充" in t and "freeze: <sha8>" in t
    s = yaml.safe_load(read(SKILL / "templates" / "research-state.yaml"))
    assert s["project"]["paper_type"] == "analysis"
    assert {"min_effect", "headroom", "splits", "budget", "freeze", "confirm", "outcome"} <= set(s["method"])
