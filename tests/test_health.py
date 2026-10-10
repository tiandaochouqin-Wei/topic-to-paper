# -*- coding: utf-8 -*-
"""Every script must answer --help, even on a console that cannot print UTF-8 symbols, and doctor must be clean."""
import subprocess

import pytest

from conftest import GBK_ENV, PY, SCRIPTS, SKILL, read, run

SCRIPT_NAMES = sorted(p.name for p in SCRIPTS.glob("*.py"))


def test_doctor_is_clean():
    r = run("t2p.py", "doctor", cwd=SKILL)
    assert r.returncode == 0, r.out
    assert "BROKEN" not in r.out and "MISSING" not in r.out, r.out


def test_doctor_skills_lists_every_routed_skill():
    r = run("t2p.py", "doctor", "--skills", "--project", str(SKILL), cwd=SKILL)
    assert r.returncode == 0, r.out
    for name in ("academic-paper-reviewer", "nature-figure", "nature-writing", "nature-response"):
        assert name in r.out, f"{name} not listed\n{r.out}"
    assert "个路由到的外部 skill 在本机可见" in r.out


@pytest.mark.parametrize("script", SCRIPT_NAMES)
def test_help_survives_a_gbk_console(script):
    """Regression: make_comparison.py and survey_check.py used to die with UnicodeEncodeError on 'gbk' before printing help."""
    r = subprocess.run([PY, str(SCRIPTS / script), "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=GBK_ENV)
    assert r.returncode == 0, r.stderr[-800:]
    assert "UnicodeEncodeError" not in r.stderr


@pytest.mark.parametrize("script", SCRIPT_NAMES)
def test_every_script_reconfigures_stdout(script):
    assert 'reconfigure(encoding="utf-8"' in read(SCRIPTS / script), f"{script}: missing the UTF-8 stdout header (copy it from any other script)"
