# -*- coding: utf-8 -*-
"""Every script must answer --help, even on a console that cannot print UTF-8 symbols, and doctor must be clean."""
import ast
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


SIBLINGS = {p.stem for p in SCRIPTS.glob("*.py")}


@pytest.mark.parametrize("script", SCRIPT_NAMES)
def test_sibling_imports_survive_python_isolated_mode(script):
    """`python -I` leaves the script directory off sys.path, and --help never reaches an import inside a function: review_check.py (shape_check),
    latex_check.py (make_algorithm) and make_algorithm.py (latex_check) crashed with ModuleNotFoundError (2.12.1). Every import of another script
    must come after a sys.path.insert(0, HERE) (module level, or on the same line in the function)."""
    tree = ast.parse(read(SCRIPTS / script))
    inserts = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) in ("sys.path.insert", "sys.path.append")]
    for n in ast.walk(tree):
        names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module] if isinstance(n, ast.ImportFrom) and n.module and not n.level else []
        for name in names:
            if name.split(".")[0] in SIBLINGS - {script[:-3]}:
                assert any(l <= n.lineno for l in inserts), f"{script}:{n.lineno} imports {name} with the script directory not yet on sys.path (python -I)"
