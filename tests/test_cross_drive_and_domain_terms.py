# -*- coding: utf-8 -*-
"""Regressions found in the RGB-IR fusion project (2026-10-16):
latex_check.py widths crashed with ValueError when the template dir and the project were on different Windows drives;
transfer_scan.py count sent comma-separated --domain terms into the OpenAlex filter, where commas split the filter (HTTP 400)."""
import argparse
import os
import sys

from conftest import SCRIPTS

sys.path.insert(0, str(SCRIPTS))
import latex_check  # noqa: E402
import transfer_scan  # noqa: E402


# ------------------------------------------------------------------ latex_check: relpath across drives
def _cross_drive_relpath(real):
    def fake(path, start=os.curdir):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")
    return fake


def test_relpath_falls_back_to_absolute(monkeypatch):
    monkeypatch.setattr(os.path, "relpath", _cross_drive_relpath(os.path.relpath))
    p = os.path.abspath("some_dir")
    assert latex_check._relpath(p, os.path.abspath("other")) == p
    assert latex_check._relpath(p) == p


def test_widths_survives_failed_pdflatex_on_another_drive(tmp_path, monkeypatch, capsys):
    (tmp_path / "main.tex").write_text("\\documentclass{nosuchclass}\n\\begin{document}\nx\n\\end{document}\n", encoding="utf-8")

    class Failed:
        stdout = "! LaTeX Error: File `nosuchclass.cls' not found."
        stderr = ""

    monkeypatch.setattr(latex_check.shutil, "which", lambda name: "pdflatex")
    monkeypatch.setattr(latex_check.subprocess, "run", lambda *a, **k: Failed())
    monkeypatch.setattr(os.path, "relpath", _cross_drive_relpath(os.path.relpath))
    latex_check.widths(argparse.Namespace(project=str(tmp_path), tex="main.tex", cls=None, options=""))
    out = capsys.readouterr().out
    assert "pdflatex 未能编译" in out and "nosuchclass.cls" in out and str(tmp_path) in out


# ------------------------------------------------------------------ transfer_scan: comma-separated --domain
def test_domain_terms_split_and_dedupe():
    assert transfer_scan.domain_terms("RGB-infrared, RGB-thermal ,rgb-infrared;") == ["RGB-infrared", "RGB-thermal"]
    assert transfer_scan.domain_terms("infrared") == ["infrared"]
    assert transfer_scan.domain_terms("") == []


def test_count_queries_commas_become_or_alternatives():
    qs = transfer_scan.count_queries("Mertens fusion", transfer_scan.domain_terms("RGB-infrared,RGB-thermal"))
    assert "," not in qs["oa"], qs["oa"]                      # a comma would split the OpenAlex filter
    assert qs["oa"] == '(Mertens fusion) AND ("RGB-infrared" OR "RGB-thermal")'
    assert qs["s2"] == '(Mertens fusion) + ("RGB-infrared" | "RGB-thermal")'
    assert qs["arxiv"] == "all:Mertens AND all:fusion AND ((all:RGB-infrared) OR (all:RGB-thermal))"
    assert qs["local"] == ["Mertens fusion RGB-infrared", "Mertens fusion RGB-thermal"]


def test_count_queries_sanitises_method_name():
    qs = transfer_scan.count_queries('Foo, "Bar": baz|qux', ["infrared"])
    assert not any(c in qs["oa"].replace('"infrared"', "") for c in ',:|'), qs["oa"]


def test_count_queries_without_domain_terms():
    qs = transfer_scan.count_queries("Mertens fusion", [])
    assert qs["oa"] == "Mertens fusion" and qs["local"] == ["Mertens fusion"] and qs["arxiv"] == "all:Mertens AND all:fusion"
