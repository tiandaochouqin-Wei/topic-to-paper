# -*- coding: utf-8 -*-
"""G3 走哪条分支：有真实 run 走 audit_check，没有但配了远程矩阵走 bundle check。

2026-10-11 真项目 P3 实测：`t2p.py init` 自己把 run-card 模板放进 runs/，于是 `os.listdir(runs)` 永远非空，
G3 一直走 audit_check 并在"0 个 run 进入审计"的情况下 PASS，远程实验包那条分支在新项目上永远不触发。
"""
import importlib.util
import shutil

from conftest import SCRIPTS, run, write


def _t2p():
    spec = importlib.util.spec_from_file_location("t2p", SCRIPTS / "t2p.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_n_runs_ignores_template_and_hidden(tmp_path):
    t = _t2p()
    (tmp_path / "runs").mkdir()
    write(tmp_path / "runs" / "_run_card_template.md", "# tpl\n")
    (tmp_path / "runs" / ".cache").mkdir()
    assert t.n_runs(str(tmp_path), "runs") == 0
    (tmp_path / "runs" / "ours_s0").mkdir()
    assert t.n_runs(str(tmp_path), "runs") == 1
    assert t.n_runs(str(tmp_path), "nope") == 0


def test_fresh_project_with_matrix_uses_bundle_check(tmp_path):
    """init 之后 runs/ 只有模板：G3 必须走 bundle check 并说明 runs/ 尚空。"""
    from conftest import FIXTURES
    proj = tmp_path / "p"
    shutil.copytree(FIXTURES / "research_min", proj)
    shutil.rmtree(proj / "runs")
    run("t2p.py", "init", "--project", str(proj), "--venue", "EAAI", cwd=tmp_path)   # 只补回 runs/ 与模板
    assert (proj / "runs" / "_run_card_template.md").exists()
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=proj)
    assert "bundle check" in r.out and "runs/ 尚空" in r.out, r.out


def test_project_with_runs_uses_audit_check(research):
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=research)
    assert "audit_check" in r.out and "bundle check" not in r.out, r.out
