# -*- coding: utf-8 -*-
"""round 20c: arXiv ids are title-checked; bare eprint ids are recognised; official proceedings URLs count as identifiers.
Network is monkeypatched, so these run offline."""
import importlib.util, os, sys, types

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def _gc():
    spec = importlib.util.spec_from_file_location("gate_check_r19c", os.path.join(SCRIPTS, "gate_check.py"))
    m = importlib.util.module_from_spec(spec); sys.path.insert(0, SCRIPTS); spec.loader.exec_module(m)
    return m


BIB = r"""
@inproceedings{lim2018rmsn,
  title={Forecasting Treatment Responses Over Time Using Recurrent Marginal Structural Networks},
  author={Lim, Bryan},
  url={https://proceedings.neurips.cc/paper_files/paper/2018/file/56e6a93212e4482d99c84a639d254b67-Paper.pdf}
}
@article{bare,
  title={World Models},
  eprint={1803.10122},
}
@misc{blog,
  title={Some blog post},
  url={https://example.com/post}
}
"""


def _run(gc, tmp_path, monkeypatch, arxiv_titles, capsys):
    p = tmp_path / "refs.bib"; p.write_text(BIB, encoding="utf-8")
    monkeypatch.setattr(gc, "arxiv_title", lambda aid: arxiv_titles[aid])
    monkeypatch.setattr(gc, "venue_title", lambda url: (True, ""))
    monkeypatch.setattr(gc.time, "sleep", lambda s: None)
    gc.gate_refs(types.SimpleNamespace(bib=str(p)))
    return capsys.readouterr().out


def test_parse_bare_eprint_and_venue_url():
    gc = _gc(); es = {e["key"]: e for e in gc.parse_bib(BIB)}
    assert es["bare"]["arxiv"] == "1803.10122"
    assert es["lim2018rmsn"]["venue_url"].startswith("https://proceedings.neurips.cc/")
    assert es["blog"]["venue_url"] == ""


def test_venue_url_is_an_identifier_but_blog_url_is_not(tmp_path, monkeypatch, capsys):
    gc = _gc(); out = _run(gc, tmp_path, monkeypatch, {"1803.10122": "World Models"}, capsys)
    assert "lim2018rmsn 无" not in out
    assert "blog 无 DOI/PMID/arXiv" in out


def test_wrong_arxiv_id_fails(tmp_path, monkeypatch, capsys):
    gc = _gc()
    out = _run(gc, tmp_path, monkeypatch, {"1803.10122": "Two-dimensional topological quantum walks in the momentum space of structured light"}, capsys)
    assert "bare arXiv 标题不匹配" in out


def test_unreachable_arxiv_warns_not_fails(tmp_path, monkeypatch, capsys):
    gc = _gc(); p = tmp_path / "refs.bib"; p.write_text(BIB.split("@misc")[0], encoding="utf-8")
    def boom(aid): raise OSError("HTTP 429")
    monkeypatch.setattr(gc, "arxiv_title", boom); monkeypatch.setattr(gc, "venue_title", lambda url: (True, ""))
    monkeypatch.setattr(gc.time, "sleep", lambda s: None)
    gc.gate_refs(types.SimpleNamespace(bib=str(p)))
    out = capsys.readouterr().out
    assert "[WARN] refs: bare arXiv 1803.10122 无法核验" in out and "[FAIL]" not in out, out
