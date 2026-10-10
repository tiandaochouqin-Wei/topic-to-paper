# -*- coding: utf-8 -*-
"""survey_search.py on saved API responses (tests/fixtures/api_samples): parsers, dedup/merge, search log, snowball, triage, PRISMA, fix-dois."""
import csv
import io
import json

from conftest import FIXTURES, edit, read, run, write

SAMPLES = FIXTURES / "api_samples"


def _rows(p):
    return list(csv.DictReader(io.open(p, encoding="utf-8-sig")))


def _search(proj):
    r = run("survey_search.py", "search", "--query", "multimodal fusion clinical", "--since", "2015", "--until", "2026", "--abstracts", "--from-dir", str(SAMPLES), cwd=proj)
    assert r.returncode == 0, r.out
    return r


def test_search_merges_three_sources_and_dedups(tmp_path):
    _search(tmp_path)
    rows = _rows(tmp_path / "literature" / "candidates.csv")
    titles = {r["title"]: r for r in rows}
    assert len(rows) == 7, [r["title"] for r in rows]                       # 3 pubmed + 2 arxiv + 3 openalex, A shared by pubmed and openalex
    a = titles["Study A: image and report fusion for diagnosis"]
    assert a["doi"] == "10.1000/fix.a" and a["pmid"] == "30000001" and a["openalex_id"] == "W1000000001" and set(a["source"].split("|")) == {"openalex", "pubmed"}
    assert "unimodal baseline" in a["abstract"]                                     # abstracts kept with --abstracts
    assert titles["Study B: records plus imaging for prognosis"]["year"] == "2022"  # MedlineDate "2022 Jan-Feb"
    assert titles["Study E: multi-sequence MRI fusion"]["doi"] == ""               # the reference-list DOI must NOT be taken
    assert titles["Study D: graph fusion of records and signals"]["arxiv_id"] == "2401.00001"   # version suffix dropped, title whitespace folded
    assert titles["Study H: text only clinical model"]["doi"] == "10.1000/fix.h"
    assert titles["Study C: attention fusion of image and text"]["abstract"] == "Attention fusion with a unimodal baseline."


def test_search_log_has_one_entry_per_source(tmp_path):
    _search(tmp_path)
    log = json.loads(read(tmp_path / "literature" / "search_log.json"))
    srcs = {s["source"]: s for s in log["sources"]}
    assert set(srcs) == {"pubmed", "arxiv", "openalex"}
    for s in srcs.values():
        assert s["query"] and s["date"] and isinstance(s["count"], int)
    assert srcs["pubmed"]["count"] == 3 and srcs["arxiv"]["count"] == 2 and srcs["openalex"]["count"] == 3
    assert srcs["arxiv"]["query"].startswith("all:")                 # plain words become an arXiv field query
    assert log["dedup_total"] == 7
    r = run("survey_check.py", "search", cwd=_survey_state(tmp_path)); assert r.fails == 0, r.out


def _survey_state(proj):
    """a minimal state so survey_check can run in the scratch project"""
    write(proj / "research-state.yaml", "branch: survey\nsurvey:\n  prior_surveys: literature/prior_surveys.csv\n")
    write(proj / "literature" / "prior_surveys.csv", "title,year,venue,doi,how_this_differs\nA prior survey,2022,Journal,10.1000/prior,organised by modality; no baseline audit\n")
    return proj


def test_search_is_incremental(tmp_path):
    _search(tmp_path)
    n1 = len(_rows(tmp_path / "literature" / "candidates.csv"))
    r = _search(tmp_path)                                                     # same responses again
    assert len(_rows(tmp_path / "literature" / "candidates.csv")) == n1 and "新增 0" in r.out
    assert len(json.loads(read(tmp_path / "literature" / "search_log.json"))["sources"]) == 6   # every run is logged


def test_snowball_merges_and_logs(tmp_path):
    _search(tmp_path)
    r = run("survey_search.py", "snowball", "--dois", "10.1000/fix.a", "--from-dir", str(SAMPLES), cwd=tmp_path)
    assert r.returncode == 0, r.out
    rows = {x["title"]: x for x in _rows(tmp_path / "literature" / "candidates.csv")}
    assert len(rows) == 9                                                     # C already known (gains the s2 source), R and Q new
    assert "s2:references" in rows["Study C: attention fusion of image and text"]["source"]
    assert rows["Study R: an early fusion review"]["pmid"] == "29000001" and rows["Study Q: citing work on fusion gains"]["arxiv_id"] == "2502.00009"
    log = json.loads(read(tmp_path / "literature" / "search_log.json"))
    assert any(s["source"].startswith("semantic_scholar") for s in log["sources"])


def test_triage_rules_and_prisma(tmp_path):
    _search(tmp_path)
    r = run("survey_search.py", "triage", "--include-any", "fusion", "--exclude", "multi-sequence", "--since", "2021", cwd=tmp_path)
    assert r.returncode == 0, r.out
    sheet = {x["title"]: x for x in _rows(tmp_path / "coding" / "screening_sheet.csv")}
    assert sheet["Study E: multi-sequence MRI fusion"]["decision"] == "exclude" and sheet["Study E: multi-sequence MRI fusion"]["reason"].startswith("rule: year")
    assert sheet["Study G: imaging only transformer"]["reason"] == "rule: no include-any term"
    assert sheet["Study A: image and report fusion for diagnosis"]["decision"] == "maybe"
    pr = json.loads(read(tmp_path / "literature" / "prisma_flow.json"))
    # rules: E (2020) by year; B, G, H have no "fusion" in title+abstract; A, C, D survive for Claude's screening
    assert sheet["Study B: records plus imaging for prognosis"]["reason"] == "rule: no include-any term"
    assert pr["identified"] == 8 and pr["deduplicated"] == 7 and pr["screened_title"] == 7 and pr["screened_abstract"] == 3 and pr["included"] == 0


def test_triage_keeps_claude_decisions(tmp_path):
    _search(tmp_path)
    run("survey_search.py", "triage", "--include-any", "fusion", cwd=tmp_path)
    p = tmp_path / "coding" / "screening_sheet.csv"
    edit(p, "maybe,rule pre-screen passed; title/abstract screening pending,title-rule\n", "include,two families and a unimodal baseline,abstract\n", count=1)
    run("survey_search.py", "triage", "--include-any", "fusion", cwd=tmp_path)           # re-run after new candidates arrive
    sheet = _rows(p)
    assert sum(1 for x in sheet if x["decision"] == "include") == 1
    assert json.loads(read(tmp_path / "literature" / "prisma_flow.json"))["included"] == 1


def test_fix_dois_uses_pubmeddata_only(tmp_path):
    (tmp_path / "literature").mkdir()
    write(tmp_path / "literature" / "candidates.csv", "source,doi,pmid,arxiv_id,openalex_id,title,year,venue,abstract,first_seen\n"
          "pubmed,,30000001,,,Study A,2021,MedIA,,2026-10-10\npubmed,,30000005,,,Study E,2020,Radiology,,2026-10-10\n")
    r = run("survey_search.py", "fix-dois", "--from-dir", str(SAMPLES), cwd=tmp_path)
    assert r.returncode == 0, r.out
    rows = {x["pmid"]: x for x in _rows(tmp_path / "literature" / "candidates.csv")}
    assert rows["30000001"]["doi"] == "10.1000/fix.a"
    assert rows["30000005"]["doi"] == ""                                      # only a reference-list DOI exists for E: must stay empty


def test_no_net_without_samples_touches_nothing(tmp_path):
    r = run("survey_search.py", "search", "--query", "x", "--no-net", cwd=tmp_path)
    assert r.returncode == 0 and "candidates.csv 0 行" in r.out
