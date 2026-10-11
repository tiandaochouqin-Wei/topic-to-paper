# -*- coding: utf-8 -*-
"""Regressions from the first real P4 (RS_nowcast, 2026-10-12): string switch values, Chinese prereg rows, documented proxy metrics."""
import importlib.util

from conftest import SCRIPTS, edit, lock, read, run, write


def _mod(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_truthy_knows_string_off_values():
    """audit_check read `--cond none` as ON and failed the nominal baseline for having no conditioning evidence."""
    t = _mod("audit_check").truthy
    for v in ("none", "None", "off", "no", "false", "0", "0.0", "", 0, 0.0, None, False):
        assert not t(v), v
    for v in ("srf", "cwl", "1", 1, 0.1, True, "yes"):
        assert t(v), v


def _chinese_row(research, with_alias):
    """prereg §6 row 'no_dom' becomes Chinese prose; with_alias registers results.aliases {no_dom: 域对抗}."""
    edit(research / "prereg.md", "| no_dom | worse: RMSE rises (+), large effect |", "| 去掉域对抗正则项 | worse: RMSE rises (+), large effect |")
    lock(research, "prereg.md", "prereg_sha256")
    if with_alias:
        edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n  aliases: {no_dom: \"域对抗\"}\n")


def test_chinese_prereg_row_without_alias_fails_everywhere(research):
    _chinese_row(research, with_alias=False)
    r = run("bundle.py", "check", cwd=research); assert r.fails >= 1 and "coverage" in r.out and "去掉域对抗正则项" in r.out, r.out
    r = run("results_check.py", cwd=research); assert r.fails >= 1 and "去掉域对抗正则项" in r.out, r.out
    r = run("ablation_plan.py", "resolve", cwd=research); assert r.fails >= 1 and "没有 run" in r.out, r.out


def test_chinese_prereg_row_with_alias_passes_everywhere(research):
    _chinese_row(research, with_alias=True)
    r = run("bundle.py", "check", cwd=research); assert r.fails == 0, r.out
    r = run("results_check.py", cwd=research); assert r.fails == 0, r.out
    r = run("ablation_plan.py", "resolve", cwd=research); assert r.fails == 0 and "可解读格 2/4" in r.out, r.out


def test_coverage_waiver_is_a_warning_not_a_pass_through(research):
    edit(research / "prereg.md", "| baseB | [3] | re-implemented from the paper | RMSE E1 0.26–0.28 |",
         "| baseB | [3] | re-implemented from the paper | RMSE E1 0.26–0.28 |\n| 光流外推（pySTEPS） | — | default | RMSE 0.30 |")
    lock(research, "prereg.md", "prereg_sha256")
    r = run("results_check.py", cwd=research); assert r.fails >= 1 and "光流外推" in r.out, r.out
    edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n  coverage_waiver: {\"光流外推\": \"原型阶段不跑\"}\n")
    r = run("results_check.py", cwd=research); assert r.fails == 0 and "豁免" in r.out, r.out


def test_proxy_primary_metric_documented_in_convention_changes_is_a_warning(research):
    p = research / "prereg.md"
    write(p, read(p).replace("RMSE of the predicted force against the sensor reading", "Error of the predicted force against the sensor reading").replace("(function rmse_contact); rmse_E2 is the secondary metric", "(function err_contact); the E2 error is the secondary metric"))
    lock(research, "prereg.md", "prereg_sha256")
    r = run("results_check.py", cwd=research); assert r.fails >= 1 and "prereg §2 没有提到主指标" in r.out, r.out
    edit(research / "research-state.yaml", "  convention_changes: []", "  convention_changes:\n    - {date: 2026-10-12, what: \"proxy primary metric rmse_E1\", why: \"prototype\"}")
    r = run("results_check.py", cwd=research); assert r.fails == 0 and "convention_changes 登记了它" in r.out, r.out
