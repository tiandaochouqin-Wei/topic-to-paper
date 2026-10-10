# -*- coding: utf-8 -*-
"""`t2p.py lock`: write the prereg / protocol sha256 into its gate entry, whatever quoting the gates block currently uses.

Found 2026-10-11 on a real project: after `check` had rewritten the gates block, the empty lock field came back as
`prereg_sha256: ''` (yaml single quotes) while the template ships `prereg_sha256: ""`, so locking by hand with a regex
on double quotes silently matched nothing. Locking is now a command that parses the inline dict instead.
"""
import hashlib
import re

import yaml

from conftest import read, run, write


def _state(p):
    return yaml.safe_load(read(p / "research-state.yaml"))


def _sha(p, doc):
    return hashlib.sha256(read(p / doc).encode("utf-8")).hexdigest()


def test_lock_research_after_check_rewrote_the_block(research):
    run("t2p.py", "check", "--project", ".", cwd=research)                      # rewrites gates with yaml quoting
    p = research / "research-state.yaml"
    write(p, re.sub(r"prereg_sha256: '?[0-9a-f]*'?", "prereg_sha256: ''", read(p)))
    assert "prereg_sha256: ''" in read(p)                                       # yaml writes an empty value single-quoted
    r = run("t2p.py", "lock", "--project", ".", cwd=research)
    assert r.returncode == 0, r.out
    assert _state(research)["gates"]["G2"]["prereg_sha256"] == _sha(research, "prereg.md")
    assert _state(research)["gates"]["G2"]["status"] == "pass"                  # the other keys survive
    assert run("prereg_check.py", cwd=research).fails == 0


def test_lock_survey_uses_protocol(survey):
    p = survey / "research-state.yaml"
    write(p, re.sub(r'protocol_sha256: "[0-9a-f]*"', 'protocol_sha256: ""', read(p)))
    r = run("t2p.py", "lock", "--project", ".", cwd=survey)
    assert r.returncode == 0, r.out
    assert _state(survey)["gates"]["G-S2"]["protocol_sha256"] == _sha(survey, "protocol.md")


def test_relock_warns_about_convention_changes(research):
    run("t2p.py", "lock", "--project", ".", cwd=research)
    write(research / "prereg.md", read(research / "prereg.md") + "\nAn added line.\n")
    r = run("t2p.py", "lock", "--project", ".", cwd=research)
    assert r.returncode == 0 and "convention_changes" in r.out
    assert _state(research)["gates"]["G2"]["prereg_sha256"] == _sha(research, "prereg.md")


def test_lock_refuses_an_untouched_template(tmp_path):
    proj = tmp_path / "fresh"
    run("t2p.py", "init", "--project", str(proj), "--venue", "CVPR", cwd=tmp_path)
    r = run("t2p.py", "lock", "--project", ".", cwd=proj)
    assert r.returncode == 1 and "仍是" in r.out


def test_status_points_at_lock_when_unlocked(research):
    p = research / "research-state.yaml"
    write(p, re.sub(r'prereg_sha256: "[0-9a-f]*"', 'prereg_sha256: ""', read(p)))
    assert "t2p.py lock" in run("t2p.py", "status", "--project", ".", cwd=research).out
    run("t2p.py", "lock", "--project", ".", cwd=research)
    assert "t2p.py lock" not in run("t2p.py", "status", "--project", ".", cwd=research).out
