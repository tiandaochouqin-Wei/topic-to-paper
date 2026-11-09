# -*- coding: utf-8 -*-
"""figure_plan.py exemplars --gallery: the top-conference Figure-1 gallery as a style-reference source (motivation / method roles).
A synthetic gallery in tmp_path (data/figures.json shaped like the real one, tiny JPGs made with PIL, an ICLR OpenReview file for the tier) stands in for the clone;
nothing here touches the network or the real clone."""
import csv
import io
import json
import os
import sys

import pytest

from conftest import SCRIPTS, edit, read, run, write

sys.path.insert(0, str(SCRIPTS))
import figure_plan as fp  # noqa: E402
import figure_review as fr  # noqa: E402

PIL = pytest.importorskip("PIL.Image")
from test_figure_plan import world, ex as corpus_ex  # noqa: E402

DOMAIN = "infrared|thermal|rgb-t|multispectral, detection|detector|fusion"
QUERY = "infrared thermal rgb detection fusion"


def rec(i, venue, year, title, pattern, paper=None, score=60.0, size=(1600, 900)):
    return {"id": f"{venue}{year}-{i:04d}", "venue": venue, "year": year, "title": title, "authors": ["A. Author", "B. Writer"], "pattern": pattern,
            "image": f"images/{venue}/final/{venue}{year}-{i:04d}.jpg", "paper": paper or f"https://example.org/{venue}/{year}/{i}", "pdf_source": "", "score": score, "w": size[0], "h": size[1]}


RECS = [
    rec(1, "cvpr", 2025, "Thermal infrared detection with a teaser of modality gaps", "teaser", score=70),             # domain match, CVPR, newest
    rec(2, "cvpr", 2025, "Thermal infrared detection with a teaser of modality gaps revisited", "teaser", score=65),    # near-identical title of #1
    rec(3, "iclr", 2024, "A conceptual view of language agents", "conceptual", score=80),                               # no domain match
    rec(4, "cvpr", 2024, "RGB thermal multispectral detection network", "architecture", paper="https://example.org/cvpr/2025/4", score=60, size=(300, 200)),     # domain match
    rec(5, "neurips", 2023, "A giant transformer for graphs", "architecture", score=90),
    rec(6, "iclr", 2025, "Pipeline for protein folding", "pipeline", paper="https://openreview.net/forum?id=ORAL1", score=50),
    rec(7, "iclr", 2025, "Pipeline for weather nowcasting", "pipeline", paper="https://openreview.net/forum?id=POSTER1", score=50),
    rec(8, "aaai", 2023, "Agent framework for tool use", "framework", score=55),
    rec(9, "cvpr", 2025, "A taxonomy of surveys", "taxonomy", score=55),
    rec(10, "cvpr", 2025, "Infrared fusion detector second view", "architecture", paper="https://example.org/cvpr/2025/4", score=99),   # same paper URL as #4 -> one per paper
]


def make_gallery(tmp_path, recs=None, tier_notes=True):
    g = tmp_path / "gallery"; recs = RECS if recs is None else recs
    write(g / "data" / "figures.json", json.dumps(recs))
    for r in recs:
        p = g / r["image"]; p.parent.mkdir(parents=True, exist_ok=True)
        PIL.new("RGB", (r["w"], r["h"]), (200, 120, 60)).save(p, "JPEG")
    if tier_notes:
        notes = [{"forum": "ORAL1", "content": {"venue": {"value": "ICLR 2025 Oral"}}}, {"forum": "POSTER1", "content": {"venue": {"value": "ICLR 2025 Poster"}}},
                 {"forum": "V1", "content": "old v1 content"}]
        write(g / "data" / "openreview" / "iclr2025_0.json", json.dumps({"notes": notes}))
    return g


def gx(project, *args, gallery=None, env=None, query=QUERY, domain=DOMAIN):
    a = ["exemplars", "--project", ".", "--papers", str(project / "nopapers"), "--index", "no.sqlite", "--query", query, "--venues", "CVPR"]
    if domain: a += ["--domain", domain]
    if gallery is not None: a += ["--gallery", str(gallery)]
    return run("figure_plan.py", *a, *args, cwd=project, env=env)


def csvrows(path): return list(csv.DictReader(io.open(path, encoding="utf-8")))


def exdir(p): return p / "literature" / "exemplars"


def gallery_picks(p):
    ex = {r["paper_id"]: r for r in csvrows(exdir(p) / "exemplars.csv") if r["source"] == "gallery"}
    return [(f["role"], ex[f["paper_id"]]) for f in csvrows(exdir(p) / "exemplar_figures.csv") if f["paper_id"] in ex]


def ids_of(picks, role=None): return [e["title"] for r, e in picks if role in (None, r)]


def test_acl_is_excluded_for_a_vision_target_unless_asked(research, tmp_path):
    # RGB-IR trial: "multimodal fusion" in ACL titles (video-language, fake news) outranked every vision paper as a Figure-1 reference
    recs = RECS + [rec(11, "acl", 2025, "Thermal infrared detection fusion of dialogue and video", "teaser", score=99)]
    g = make_gallery(tmp_path, recs)
    gx(research, gallery=g)
    assert not [e for _, e in gallery_picks(research) if e["venue"] == "ACL"], gallery_picks(research)
    gx(research, "--gallery-venues", "acl,cvpr", gallery=g)
    assert "Thermal infrared detection fusion of dialogue and video" in ids_of(gallery_picks(research), "motivation")


# ------------------------------------------------------------------ configuration
def test_missing_gallery_dir_is_one_info_line_and_no_rows(research, tmp_path):
    r = gx(research, gallery=tmp_path / "nope")
    assert r.returncode == 0 and not r.crashed, r.out
    info = [l for l in r.out.splitlines() if l.startswith("[INFO] figure_plan:") and "git clone --depth 1 https://github.com/qwdwqfwq/topconf-paper-figure-gallery" in l]
    assert len(info) == 1, r.out
    assert not gallery_picks(research) and not (exdir(research) / "gallery_attribution.md").exists()


def test_unreadable_figures_json_is_the_same_info(research, tmp_path):
    g = tmp_path / "gallery"; write(g / "data" / "figures.json", "{not json")
    r = gx(research, gallery=g)
    assert r.returncode == 0 and not r.crashed and "[INFO] figure_plan:" in r.out and "git clone --depth 1" in r.out and not gallery_picks(research), r.out


def test_not_configured_is_an_info_line_too(research):
    r = gx(research)
    assert r.returncode == 0 and "没配画廊" in r.out and not gallery_picks(research), r.out


def test_env_var_and_state_path_both_work(research, tmp_path):
    g = make_gallery(tmp_path)
    r = gx(research, env={**os.environ, "PYTHONUTF8": "1", "T2P_GALLERY": str(g)})
    assert gallery_picks(research) and "references (" in r.out, r.out
    n_env = len(gallery_picks(research))
    (exdir(research) / "exemplars.csv").unlink()
    edit(research / "research-state.yaml", "figures:\n", f"figures:\n  gallery: {json.dumps(str(g))}\n")
    gx(research)
    assert len(gallery_picks(research)) == n_env > 0
    # the --gallery flag wins over the state path
    r = gx(research, gallery=tmp_path / "nope")
    assert "git clone --depth 1" in r.out and not gallery_picks(research)


# ------------------------------------------------------------------ selection
def test_role_mapping_and_survey_only_taxonomy(research, tmp_path):
    g = make_gallery(tmp_path)
    r = gx(research, gallery=g)
    assert r.returncode == 0 and not r.crashed, r.out
    pats = {role: {f["types"] for f in csvrows(exdir(research) / "exemplar_figures.csv") if f["role"] == role and f["paper_id"].startswith("gallery_")} for role in ("motivation", "method", "analysis")}
    assert pats["motivation"] <= {"teaser", "conceptual"} and pats["motivation"] and pats["method"] <= {"architecture", "framework", "pipeline"} and pats["method"] and not pats["analysis"]
    assert "A taxonomy of surveys" not in ids_of(gallery_picks(research))
    gx(research, "--gallery-roles", "motivation,method,analysis", gallery=g)
    assert ids_of(gallery_picks(research), "analysis") == ["A taxonomy of surveys"]
    edit(research / "research-state.yaml", "branch: research", "branch: survey")                   # a survey asks for taxonomy references by itself
    gx(research, gallery=g)
    assert ids_of(gallery_picks(research), "analysis") == ["A taxonomy of surveys"]


def test_domain_matched_records_rank_first_and_are_flagged_style_only_otherwise(research, tmp_path):
    g = make_gallery(tmp_path)
    r = gx(research, gallery=g)
    picks = gallery_picks(research)
    mot = [(e["title"], e["topic_match"]) for role, e in picks if role == "motivation"]
    assert mot[0] == ("Thermal infrared detection with a teaser of modality gaps", "yes"), mot
    assert ("A conceptual view of language agents", "no") in mot                                      # not a hard filter: kept as a style reference
    met = [(e["title"], e["topic_match"]) for role, e in picks if role == "method"]
    assert met[0][1] == "yes" and "RGB thermal multispectral detection network" == met[0][0] and all(m == "no" for _, m in met[1:]), met
    assert "references (" in r.out and "topic-matched, rest style-only) from" in r.out and "gallery: " in r.out


def test_one_per_paper_and_no_near_identical_titles(research, tmp_path):
    g = make_gallery(tmp_path)
    gx(research, gallery=g)
    t = ids_of(gallery_picks(research))
    assert "Thermal infrared detection with a teaser of modality gaps revisited" not in t           # near-identical to the first teaser
    assert "Infrared fusion detector second view" not in t                                           # same paper URL as 'RGB thermal multispectral detection network'
    urls = [e["url"] for _, e in gallery_picks(research)]
    assert len(urls) == len(set(urls))


def test_tier_decides_when_text_and_domain_do_not(research, tmp_path):
    g = make_gallery(tmp_path)
    gx(research, "--gallery-roles", "method", "--gallery-k", "6", gallery=g, query="zzzz", domain="")
    met = gallery_picks(research)
    order = ids_of(met, "method")
    assert order.index("Pipeline for protein folding") < order.index("Pipeline for weather nowcasting")      # ICLR Oral (OpenReview) before Poster
    tiers = {e["title"]: e["tier"] for _, e in met}
    assert tiers["Pipeline for protein folding"] == "Oral" and tiers["Pipeline for weather nowcasting"] == ""
    fig = {f["paper_id"]: f for f in csvrows(exdir(research) / "exemplar_figures.csv")}
    cap = [f["caption_first"] for f in fig.values() if f["paper_id"].startswith("gallery_") and "protein" in f["caption_first"]][0]
    assert cap == "[gallery, ICLR 2025, Oral] Pipeline for protein folding"


def test_tier_and_award_fields_of_figures_json_are_used(research, tmp_path):
    recs = [dict(rec(1, "icml", 2025, "Alpha pipeline method", "pipeline"), tier="spotlight"), dict(rec(2, "icml", 2025, "Bravo pipeline system", "pipeline"), tier="oral"),
            dict(rec(3, "icml", 2025, "Charlie pipeline design", "pipeline"), tier="oral", award="honorable"), rec(4, "icml", 2025, "Delta pipeline model", "pipeline")]
    g = make_gallery(tmp_path, recs, tier_notes=False)
    gx(research, "--gallery-roles", "method", "--gallery-k", "4", gallery=g, query="zzzz", domain="")
    assert [(e["title"].split()[0], e["tier"]) for _, e in gallery_picks(research)] == [("Charlie", "Best"), ("Bravo", "Oral"), ("Alpha", "Spotlight"), ("Delta", "")]


def test_tier_label_parsing_and_record_fields():
    assert [fp.tier_label(x) for x in ("ICLR 2025 Oral", "ICLR 2023 notable top 5%", "ICLR 2024 spotlight", "ICLR 2023 notable top 25%", "Outstanding Paper", "ICLR 2025 Poster", "Submitted to ICLR 2025", None)] == \
        ["Oral", "Oral", "Spotlight", "Spotlight", "Best", "", "", ""]


def test_venue_then_year_decide_the_rest(research, tmp_path):
    recs = [rec(1, "neurips", 2025, "Alpha pipeline method", "pipeline"), rec(2, "cvpr", 2023, "Bravo pipeline method", "pipeline"), rec(3, "cvpr", 2025, "Charlie pipeline method", "pipeline"),
            rec(4, "aaai", 2025, "Delta pipeline method", "pipeline"), rec(5, "icml", 2024, "Echo pipeline method", "pipeline")]
    g = make_gallery(tmp_path, recs, tier_notes=False)
    edit(research / "research-state.yaml", "family: cs_journal", "family: cs_conf")
    gx(research, "--gallery-roles", "method", "--gallery-k", "5", gallery=g, query="zzzz", domain="")
    # cs_conf: CVPR first, then ICLR/ICML/NeurIPS, then the rest; newer year inside a group
    assert ids_of(gallery_picks(research)) == ["Charlie pipeline method", "Bravo pipeline method", "Alpha pipeline method", "Echo pipeline method", "Delta pipeline method"]
    edit(research / "research-state.yaml", "family: cs_conf", "family: cs_journal")
    gx(research, "--gallery-roles", "method", "--gallery-k", "5", gallery=g, query="zzzz", domain="")
    # journal family: no venue preference, newer year first (2025: neurips / cvpr / aaai in score-then-input order), then 2024, then 2023
    assert [e["year"] for _, e in gallery_picks(research)] == ["2025", "2025", "2025", "2024", "2023"]


def test_gallery_score_is_the_last_tie_break(research, tmp_path):
    recs = [rec(1, "cvpr", 2025, "Alpha pipeline method", "pipeline", score=10), rec(2, "cvpr", 2025, "Bravo pipeline system", "pipeline", score=90)]
    g = make_gallery(tmp_path, recs, tier_notes=False)
    gx(research, "--gallery-roles", "method", gallery=g, query="zzzz", domain="")
    assert ids_of(gallery_picks(research)) == ["Bravo pipeline system", "Alpha pipeline method"]


# ------------------------------------------------------------------ files
def test_thumbs_are_downscaled_project_relative_and_attributed(research, tmp_path):
    g = make_gallery(tmp_path)
    gx(research, gallery=g)
    figs = [f for f in csvrows(exdir(research) / "exemplar_figures.csv") if f["paper_id"].startswith("gallery_")]
    assert figs
    for f in figs:
        assert f["kind"] == "fig" and f["n"] == "1" and f["page"] == "1" and f["panels"] == "1" and f["thumb"].startswith("literature/exemplars/thumbs/gallery_") and f["thumb"].endswith(".jpg")
        assert f["caption_first"].startswith("[gallery, ") and f["role"] in ("motivation", "method")
        with PIL.open(research / f["thumb"]) as im:
            assert max(im.size) <= 900
    big = [f for f in figs if "teaser of modality" in f["caption_first"]][0]
    with PIL.open(research / big["thumb"]) as im: assert im.size == (900, 506)
    small = [f for f in figs if "multispectral detection network" in f["caption_first"]][0]
    with PIL.open(research / small["thumb"]) as im: assert im.size == (300, 200)                    # never upscaled
    att = read(exdir(research) / "gallery_attribution.md")
    for e in [e for _, e in gallery_picks(research)]:
        assert e["title"] in att and e["url"] in att
    assert "A. Author, B. Writer" in att and "Image © the original authors; used as a design reference only (gallery: https://github.com/qwdwqfwq/topconf-paper-figure-gallery, images policy: IMAGES_POLICY.md)" in att
    assert all(f"`{r['id']}`" in att for r in RECS if f"gallery_{r['id']}" in {f['paper_id'] for f in figs})
    md = read(exdir(research) / "exemplars.md")
    assert "## Gallery (Figure 1 style references)" in md and "topic_match" in md
    # nothing was copied into the skill repo
    assert not list(SCRIPTS.parent.rglob("gallery_*.jpg"))


def test_rerun_replaces_the_previous_gallery_files(research, tmp_path):
    g = make_gallery(tmp_path)
    gx(research, gallery=g)
    n = len(list((exdir(research) / "thumbs").glob("gallery_*.jpg")))
    gx(research, "--gallery-k", "1", gallery=g)
    assert 0 < len(list((exdir(research) / "thumbs").glob("gallery_*.jpg"))) < n
    gx(research, gallery=tmp_path / "nope")
    assert not list((exdir(research) / "thumbs").glob("gallery_*.jpg")) and not (exdir(research) / "gallery_attribution.md").exists()


def test_image_path_outside_the_clone_is_ignored(research, tmp_path):
    g = make_gallery(tmp_path, [rec(1, "cvpr", 2025, "Alpha pipeline method", "pipeline")], tier_notes=False)
    recs = json.loads(read(g / "data" / "figures.json")); recs[0]["image"] = "../secret.jpg"
    PIL.new("RGB", (10, 10)).save(tmp_path / "secret.jpg", "JPEG")
    write(g / "data" / "figures.json", json.dumps(recs))
    gx(research, gallery=g, query="zzzz", domain="")
    assert not gallery_picks(research)


# ------------------------------------------------------------------ readers of exemplars.csv / exemplar_figures.csv
def test_exemplars_csv_has_the_trailing_url_column_and_readers_still_work(research, tmp_path):
    g = make_gallery(tmp_path)
    gx(research, gallery=g)
    head = io.open(exdir(research) / "exemplars.csv", encoding="utf-8").readline().strip().split(",")
    assert head[:9] == ["paper_id", "title", "venue", "year", "cited", "fresh", "bm25", "source", "pdf"] and head[9] == "url"
    r = run("figure_plan.py", "plan", "--project", ".", cwd=research)
    assert r.returncode == 0 and not r.crashed, r.out
    r = run("figure_plan.py", "check", "--project", ".", cwd=research)
    assert not r.crashed and "只有 0 篇范文" in r.out, r.out                                         # gallery rows are style references, not the >= 3 same-topic exemplars
    # figure_review reads the same two csv files: a method figure gets the gallery thumbnails as exemplars
    rows = csvrows(research / "paper" / "figure_plan.csv")
    for r_ in rows:
        if r_["role"] == "method": r_["files"] = "figures/fig_arch"
    gp = {"id": "fig_arch", "stems": {"figures/fig_arch": {}}}
    ex_rows = csvrows(exdir(research) / "exemplars.csv"); fig_rows = csvrows(exdir(research) / "exemplar_figures.csv")
    exs, role = fr.exemplars_for(str(research), gp, rows, fig_rows, ex_rows)
    assert role == "method" and exs and all(x["paper_id"].startswith("gallery_") and x["thumb"].startswith("literature/exemplars/thumbs/gallery_") for x in exs)
    assert exs[0]["venue_year"] in ("CVPR 2024", "ICLR 2025", "NeurIPS 2023", "AAAI 2023")


# ------------------------------------------------------------------ plan
def test_plan_uses_a_gallery_exemplar_when_the_corpus_has_none(research, tmp_path):
    g = make_gallery(tmp_path)
    gx(research, gallery=g)
    run("figure_plan.py", "plan", "--project", ".", cwd=research)
    rows = csvrows(research / "paper" / "figure_plan.csv")
    m = [r for r in rows if r["role"] == "method"][0]
    assert m["exemplar"] == "仿 RGB thermal multispectral detection netw (CVPR 2024, gallery, 主题相同)", m["exemplar"]
    assert m["thumb"].startswith("literature/exemplars/thumbs/gallery_") and m["exemplar_caption"].startswith("[gallery, CVPR 2024]")
    mot = [r for r in rows if r["role"] == "motivation"][0]
    assert mot["exemplar"].startswith("仿 Thermal infrared detection with a teaser") and mot["exemplar"].endswith("(CVPR 2025, gallery, 主题相同)")
    # style-only wording
    gx(research, gallery=g, query="zzzz", domain="")
    run("figure_plan.py", "plan", "--project", ".", "--force", cwd=research)
    m = [r for r in csvrows(research / "paper" / "figure_plan.csv") if r["role"] == "method"][0]
    assert m["exemplar"].endswith("gallery, 仅版式参考)"), m["exemplar"]
    # result rows never get a gallery exemplar
    assert all("gallery" not in r["exemplar"] for r in csvrows(research / "paper" / "figure_plan.csv") if r["role"] not in ("motivation", "method"))


def test_plan_prefers_the_corpus_exemplar_when_it_exists(research, tmp_path):
    papers = world(tmp_path); g = make_gallery(tmp_path)
    r = corpus_ex(research, papers, "--gallery", str(g), "--k", "6", "--domain", "dose|noise, detection")
    assert r.returncode == 0 and not r.crashed, r.out
    assert gallery_picks(research)
    run("figure_plan.py", "plan", "--project", ".", cwd=research)
    rows = csvrows(research / "paper" / "figure_plan.csv")
    m = [x for x in rows if x["role"] == "method"][0]
    assert m["exemplar"].startswith("仿 ") and "Fig 2" in m["exemplar"] and "gallery" not in m["exemplar"] and "gallery_" not in m["thumb"]
    mot = [x for x in rows if x["role"] == "motivation"][0]
    assert "Fig 1" in mot["exemplar"] and "gallery" not in mot["exemplar"]
    # the corpus counts still ignore the gallery rows: 4 corpus exemplars, not 4 + gallery
    r = run("figure_plan.py", "check", "--project", ".", cwd=research)
    assert "只有" not in r.out, r.out
    # a corpus figure without a thumbnail hands the row to the gallery
    p = exdir(research) / "exemplar_figures.csv"; fr_ = csvrows(p)
    for x in fr_:
        if x["role"] == "method" and not x["paper_id"].startswith("gallery_"): x["thumb"] = ""
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fp.FIG_COLS); w.writeheader(); w.writerows(fr_)
    run("figure_plan.py", "plan", "--project", ".", "--force", cwd=research)
    m = [x for x in csvrows(research / "paper" / "figure_plan.csv") if x["role"] == "method"][0]
    assert "gallery" in m["exemplar"] and "画廊" in m["note"]
