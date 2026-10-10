# -*- coding: utf-8 -*-
"""refs gate, DOI title resolution: publisher markup must not count as words, and DataCite DOIs must resolve.

Found 2026-10-10 on a real remote-sensing project: the TGRS DOI of "D²FT-Net" resolved correctly but CrossRef returns the
title as "D<sup>2</sup>FT-Net: …". norm() turned the tags into the tokens "sup" and "sup", the ratio fell to 0.85 and a
correct reference was reported as FAIL. Two KITopen DOIs (10.5445/ir/…) are registered with DataCite, not CrossRef, so
CrossRef answered 404 and they were never verified.
"""
import difflib
import importlib.util

from conftest import SCRIPTS


def _gc():
    spec = importlib.util.spec_from_file_location("gate_check", SCRIPTS / "gate_check.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def _ratio(m, a, b):
    return difflib.SequenceMatcher(None, m.norm(a), m.norm(b)).ratio()


def test_superscript_markup_does_not_break_the_match():
    m = _gc()
    bib = "D 2 FT-Net: Frequency-Spatial Dual Domain Fine-Tuning of Vision Foundation Models for Remote Sensing Domain Generalization Semantic Segmentation"
    crossref = "D\n                    <sup>2</sup>\n                    FT-Net: Frequency-Spatial Dual Domain Fine-Tuning of Vision Foundation Models for Remote Sensing Domain Generalization Semantic Segmentation"
    assert _ratio(m, crossref, bib) >= 0.85, m.norm(crossref)
    assert "sup" not in m.norm(crossref).split()


def test_other_publisher_markup_and_entities_are_stripped():
    m = _gc()
    for registered, plain in [
        ("Detection of <i>in vivo</i> lesions", "Detection of in vivo lesions"),
        ("Water &amp; sediment transport", "Water and sediment transport"),
        ("CO<sub>2</sub> flux over boreal forest", "CO2 flux over boreal forest"),
        ("<mml:math><mml:mi>k</mml:mi></mml:math>-space reconstruction", "k-space reconstruction"),
        ("Effect of &#x03B2;-amyloid", "Effect of beta-amyloid"),
    ]:
        assert _ratio(m, registered, plain) >= 0.85, (registered, m.norm(registered))


def test_norm_is_whitespace_stable():
    m = _gc()
    assert m.norm("  A   Title\n with   gaps ") == "a title with gaps"


def test_crossref_title_falls_back_to_datacite(monkeypatch):
    """A 404 from CrossRef must be retried on DataCite; any other HTTP error still propagates."""
    import urllib.error
    m = _gc()
    calls = []

    def fake(url, timeout=20):
        calls.append(url)
        if "crossref" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return {"data": {"attributes": {"titles": [{"title": "A Critical Synthesis of Uncertainty Quantification"}]}}}

    monkeypatch.setattr(m, "_get_json", fake)
    assert m.crossref_title("10.5445/ir/1000195477").startswith("A Critical Synthesis")
    assert len(calls) == 2 and "datacite" in calls[1]

    def fake500(url, timeout=20):
        raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)

    monkeypatch.setattr(m, "_get_json", fake500)
    try:
        m.crossref_title("10.1000/x"); assert False, "a 500 must not be swallowed"
    except urllib.error.HTTPError as ex:
        assert ex.code == 500


def test_crossref_empty_title_falls_back_to_datacite(monkeypatch):
    m = _gc()

    def fake(url, timeout=20):
        if "crossref" in url:
            return {"message": {"title": []}}
        return {"data": {"attributes": {"titles": [{"title": "Fallback title"}]}}}

    monkeypatch.setattr(m, "_get_json", fake)
    assert m.crossref_title("10.1234/empty") == "Fallback title"
