# -*- coding: utf-8 -*-
"""Shared helpers for the topic-to-paper regression tests.

Two fixtures are copied from tests/fixtures/ into a temp dir per test:
  research  -> research_min: a minimal research-branch project where every offline gate PASSes
  survey    -> survey_min:   a minimal survey-branch project where G-S2 / G-S3 / G-S5 PASS
Tests mutate the copy and assert that the responsible gate FAILs. The copy step re-locks the
preregistration / protocol hash (text-mode sha256, as the gate scripts compute it) and bumps the
eval.json mtimes so that the fixture does not depend on checkout order or line endings.
"""
import hashlib, io, os, re, shutil, subprocess, sys, time
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PY = sys.executable
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
GBK_ENV = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "gbk"}   # a Chinese Windows console


def run(script, *args, cwd, env=None):
    """Run scripts/<script> <args> inside <cwd>. Adds .out (stdout+stderr), .fails (#[FAIL] lines) and .crashed."""
    r = subprocess.run([PY, str(SCRIPTS / script), *map(str, args)], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env or ENV)
    r.out = r.stdout + r.stderr
    r.fails = len(re.findall(r"^\[FAIL\]", r.out, re.M))
    r.crashed = "Traceback (most recent call last)" in r.stderr
    return r


def read(path):
    return io.open(path, encoding="utf-8").read()


def write(path, text):
    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)


def edit(path, old, new, count=-1):
    """Replace `old` with `new` in a text file; asserts that `old` is present so a stale mutation cannot pass silently."""
    s = read(path)
    assert old in s, f"{old!r} not found in {path}"
    write(path, s.replace(old, new, count))


def touch(path, delta=0.0):
    t = time.time() + delta
    os.utime(path, (t, t))


def lock(project, doc, key):
    """Write sha256(<doc> as text) into research-state.yaml at `<key>: "..."`; returns the hash."""
    sha = hashlib.sha256(read(project / doc).encode("utf-8")).hexdigest()
    sp = project / "research-state.yaml"
    s2, n = re.subn(key + r': "[0-9a-f]*"', f'{key}: "{sha}"', read(sp))
    assert n == 1, f"{key} must appear exactly once in research-state.yaml"
    write(sp, s2)
    return sha


def copy_fixture(kind, tmp_path):
    dst = tmp_path / kind
    shutil.copytree(FIXTURES / kind, dst)
    if kind == "research_min":
        lock(dst, "prereg.md", "prereg_sha256")
        for ev in dst.glob("runs/*/eval.json"):
            touch(ev, +2)          # evaluation after the training log, whatever order the files were checked out in
    else:
        lock(dst, "protocol.md", "protocol_sha256")
    return dst


@pytest.fixture
def research(tmp_path):
    return copy_fixture("research_min", tmp_path)


@pytest.fixture
def survey(tmp_path):
    return copy_fixture("survey_min", tmp_path)
