# -*- coding: utf-8 -*-
"""figure_plan.py: exemplar selection (index, filters, citations, path fallback), figure/table roles from the PDFs, the claim-first plan, check, and the G5 line.
Offline: a tiny papers root with synthetic PDFs (PyMuPDF) stands in for Z:/LDCT/papers; citations come from a replay dir."""
import csv
import datetime
import io
import json
import shutil
import sys

import pytest

from conftest import SCRIPTS, edit, read, run, write

sys.path.insert(0, str(SCRIPTS))
import figure_plan as fp  # noqa: E402

fitz = pytest.importorskip("fitz")
THIS_YEAR = datetime.date.today().year
BODY = ("Dose shift degrades detectors because the noise texture of low dose scans differs from the training distribution, so a routed expert is needed. " * 4)


def make_pdf(path, image=False, qual_caption="Qualitative comparison on three low-dose scans; red boxes mark misses."):
    """3 pages: p1 full-width rectangle + Figure 1 (motivation); p2 half-width rectangle + Figure 2 (overview, panels) + Table 1;
    p3 Figure 3 (qualitative, optional embedded image) + Figure 4 (accuracy-efficiency vs state of the art) + a References heading."""
    d = fitz.open()
    def page(): return d.new_page(width=612, height=792)
    def body(p, y=60): p.insert_textbox(fitz.Rect(72, y, 540, y + 70), BODY, fontsize=9)
    def cap(p, y, text): p.insert_textbox(fitz.Rect(72, y, 540, y + 40), text, fontsize=9)
    p1 = page(); body(p1)
    p1.draw_rect(fitz.Rect(72, 150, 540, 300), color=(0, 0, 0), fill=(0.8, 0.8, 0.9))
    cap(p1, 310, "Figure 1: Motivation of dose-robust detection. Existing detectors lose accuracy as the dose drops, while ours stays flat.")
    p2 = page(); body(p2)
    p2.draw_rect(fitz.Rect(72, 150, 306, 300), color=(0, 0, 0), fill=(0.9, 0.8, 0.8))
    cap(p2, 310, "Figure 2: Overview of the proposed framework. (a) encoder, (b) routed experts, (c) detection head.")
    cap(p2, 420, "Table 1: Comparison with state-of-the-art methods on the benchmark; best in bold.")
    p2.insert_textbox(fitz.Rect(72, 455, 540, 520), "method AP AP50\nours 41.2 60.1\nbase 38.0 57.7", fontsize=9)
    p3 = page(); body(p3)
    if image:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40)); pix.clear_with(180)
        p3.insert_image(fitz.Rect(72, 150, 300, 260), pixmap=pix)
    else:
        p3.draw_rect(fitz.Rect(72, 150, 300, 260), color=(0, 0, 0), fill=(0.8, 0.9, 0.8))
    cap(p3, 270, "Figure 3: " + qual_caption)
    p3.draw_rect(fitz.Rect(72, 350, 540, 480), color=(0, 0, 0), fill=(0.9, 0.9, 0.7))
    cap(p3, 490, "Figure 4: Accuracy-efficiency trade-off compared with state-of-the-art methods on the benchmark.")
    p3.insert_textbox(fitz.Rect(72, 600, 540, 640), "References\n[1] A. Author. Some paper. 2024.", fontsize=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path)); d.close()
    return path


def world(tmp_path, extra_rows=()):
    """papers root (metadata/index.csv + PDFs) and a project copy; returns (papers, project-less rows helper)"""
    papers = tmp_path / "papers"
    rows = [("CVPR", "2025", "Dose robust organ detection with adaptive routing", "CVPR/2025/a.pdf", False),
            ("CVPR", "2025", "Robust detection under dose shift with routed experts", "CVPR/2025/b.pdf", True),
            ("CVPR", "2025", "Detection under dose shift: a noise texture study", "CVPR/2025/c.pdf", False),
            ("ICCV", "2024", "Noise robust detection under dose shift", "ICCV/2024/d.pdf", False),
            ("CVPR", "2022", "Dose robust organ detection, the early version", "CVPR/2022/e.pdf", False),
            ("WACV", "2025", "Dose robust detection at WACV", "WACV/2025/f.pdf", False),
            ("NeurIPS", "2025", "Generating cooking recipes with language models", "NeurIPS/2025/g.pdf", False),
            ("ECCV", "2025", "A transformer for weather forecasting", "ECCV/2025/h.pdf", False)] + list(extra_rows)
    for v, y, t, rel, img in rows:
        make_pdf(papers / rel, image=img)
    write(papers / "metadata" / "index.csv", "venue,year,title,matched_kw,local_path\n" + "".join(f'{v},{y},"{t}",,{(papers / rel).as_posix()}\n' for v, y, t, rel, _ in rows))
    return papers


def ex(project, papers, *args, query="dose robust detection dose shift", venues="CVPR,ICCV,ECCV"):
    return run("figure_plan.py", "exemplars", "--project", ".", "--papers", papers, "--query", query, "--venues", venues, *args, cwd=project)


def csvrows(path): return list(csv.DictReader(io.open(path, encoding="utf-8")))


def exdir(project): return project / "literature" / "exemplars"


def titles(project): return {r["title"] for r in csvrows(exdir(project) / "exemplars.csv")}


@pytest.fixture
def planned(research, tmp_path):
    """project with exemplars (3 CVPR + 1 ICCV) and a first plan"""
    papers = world(tmp_path)
    r = ex(research, papers, "--k", "6")
    assert r.returncode == 0 and not r.crashed, r.out
    return research


def plan(project, *extra): return run("figure_plan.py", "plan", "--project", ".", *extra, cwd=project)


def plan_rows(project): return csvrows(project / "paper" / "figure_plan.csv")


def by(rows, **kw): return [r for r in rows if all(r[k] == v for k, v in kw.items())]


# ------------------------------------------------------------------ exemplars: selection
def test_index_is_built_when_missing_and_reused(research, tmp_path):
    papers = world(tmp_path)
    r = ex(research, papers)
    assert r.returncode == 0 and "building" in r.out and (research / "literature" / "lit_index.sqlite").exists(), r.out
    assert "query: dose robust detection dose shift" in r.out
    assert "building" not in ex(research, papers).out


def test_venue_and_year_filters(research, tmp_path):
    papers = world(tmp_path)
    ex(research, papers)
    t = titles(research)
    assert "Noise robust detection under dose shift" in t                                  # ICCV 2024 is inside the venue list and the year window
    assert not {x for x in t if "early version" in x or "WACV" in x or "cooking" in x or "weather" in x}, t
    ex(research, papers, "--min-year", "2025")
    assert "Noise robust detection under dose shift" not in titles(research)


def test_default_venues_follow_the_target_family_and_the_query_uses_topic_only(research, tmp_path):
    papers = world(tmp_path)
    edit(research / "research-state.yaml", 'topic: "vision-based surgical force estimation under robot-platform shift"', 'topic: "dose robust organ detection"')
    edit(research / "research-state.yaml", "family: cs_journal", "family: cs_conf")
    r = run("figure_plan.py", "exemplars", "--project", ".", "--papers", papers, cwd=research)           # no --query / --venues
    q = [l for l in r.out.splitlines() if l.startswith("query:")][0]
    # topic + title only: the claim statements ("regularizer", "lowers held-out RMSE") describe findings, not the topic
    # (on cvpr2027_fusion they pulled "Robot-Gated Imitation Learning" in as an exemplar)
    assert "dose" in q and "organ" in q and "regularizer" not in q and "ours" not in q.split(), q
    assert "没给 --domain" in r.out
    assert "Dose robust organ detection with adaptive routing" in titles(research) and not {x for x in titles(research) if "WACV" in x}


def test_domain_groups_must_all_match():
    assert fp.domain_ok("rgb|infrared|thermal, detection|detector", "WaveMamba Wavelet Driven Mamba Fusion for RGB Infrared Object Detection", "", [])
    assert not fp.domain_ok("rgb|infrared|thermal, detection|detector", "Robot Gated Interactive Imitation Learning", "", [])
    assert not fp.domain_ok("infrared|thermal, detection", "LoGoNet Towards Accurate 3D Object Detection with Local to Global Fusion", "", [])
    assert fp.domain_ok("", "Dose robust organ detection", "", ["dose", "robust", "organ"])               # no --domain: half the query words
    assert not fp.domain_ok("", "Quantum gated distillation", "", ["dose", "robust", "organ", "gated"])


# real captions from the 2026-10-28 trial (8 RGB-X / multimodal-detection exemplars) -> the role a reader would give them
REAL = [
    (1, 1, "(a) shows the averaged normalized information entropy of low- and high-frequency components from RGB and IR images.", "motivation"),
    (2, 4, "Illustrative diagram of the complete network and sub-modules.", "method"),
    (3, 7, "Heatmap visualization of several cross-modality object detection methods on M 3FD and DroneVehicle.", "qualitative"),
    (4, 8, "Detection results' visualization of several cross-modality object detection methods on M 3FD and DroneVehicle.", "qualitative"),
    (1, 1, "Pipelines of different Unaligned RGB-T fusion methods.", "motivation"),
    (2, 4, "Overview of the proposed UMFNet framework. The encoder-decoder network performs RGB-T feature fusion.", "method"),
    (1, 2, "Comparison between (a) global fusion and (b) local fusion.", "motivation"),
    (2, 4, "Examples of the DViSal dataset.", "dataset"),
    (3, 6, "Visual results of image fusion on M3FD. 3.4 Gradient Matrix Task-Alignment The MF and OD tasks conflict", "qualitative"),
    (5, 10, "Visualization of task dominance and conflicting gradients in joint learning of OD and MF.", "analysis"),
    (5, 8, "Shapley values analysis showing the importance of each component within the parallel RAM mechanism.", "ablation"),
]


@pytest.mark.parametrize("n,page,cap,role", REAL)
def test_figure_roles_on_real_captions(n, page, cap, role):
    assert fp.fig_role(n, page, [], cap) == role, cap


@pytest.mark.parametrize("cap,role", [
    ("Effects of the SFM and DFM on M 3FD dataset.", "ablation"),
    ("Comparison with state-of-the-art methods. Params and FLOPs are measured at 640.", "main_result"),
    ("Quantitative results of object detection on M3FD dataset among all the image fusion methods.", "main_result"),
    ("Comparison of Model Size, Inference Time and mAP.", "efficiency"),
    ("SOTA results on LLVIP.", "main_result"),                    # only the \bsota\b alternative matches: guards against \b written as a backspace
    ("Variants of the gate on M3FD.", "ablation"),
    ("Runtime in FPS on one A100.", "efficiency"),
])
def test_table_roles_on_real_captions(cap, role):
    assert fp.table_role(cap) == role, cap


def test_missing_user_pdf_says_missing_not_unreadable(research, tmp_path):
    papers = world(tmp_path)
    r = run("figure_plan.py", "exemplars", "--project", ".", "--papers", papers, "--pdf", str(tmp_path / "gone" / "main(2).pdf"), cwd=research)
    assert "不存在" in r.out and "literature/pdf/" in r.out, r.out


def test_at_most_three_per_venue(research, tmp_path):
    extra = [("CVPR", "2025", f"Dose shift detection variant {i}", f"CVPR/2025/x{i}.pdf", False) for i in range(3)]
    papers = world(tmp_path, extra)
    ex(research, papers, "--k", "8")
    venues = [r["venue"] for r in csvrows(exdir(research) / "exemplars.csv")]
    assert venues.count("CVPR") == 3 and "ICCV" in venues, venues


def test_user_pdfs_are_always_included_and_do_not_count_against_k(research, tmp_path):
    papers = world(tmp_path)
    mine = make_pdf(tmp_path / "mine" / "group_paper.pdf")
    ex(research, papers, "--k", "1", "--pdf", mine)
    rows = csvrows(exdir(research) / "exemplars.csv")
    assert len(rows) == 2 and sorted(r["source"] for r in rows) == ["corpus", "user"], rows
    assert {r["paper_id"] for r in csvrows(exdir(research) / "exemplar_figures.csv")} >= {"group_paper"}


def test_openalex_median_filter_with_replay_and_fresh_exemption(research, tmp_path):
    extra = [("CVPR", str(THIS_YEAR), "Dose shift detection, this year's paper", f"CVPR/{THIS_YEAR}/new.pdf", False)]
    papers = world(tmp_path, extra)
    cited = {"Dose robust organ detection with adaptive routing": 100, "Robust detection under dose shift with routed experts": 5,
             "Detection under dose shift: a noise texture study": 60, "Noise robust detection under dose shift": 1, "Dose shift detection, this year's paper": 0}
    replay = tmp_path / "replay"; replay.mkdir(); write(replay / "openalex_cited.json", json.dumps(cited))
    r = ex(research, papers, "--k", "8", "--from-dir", replay)
    rows = {x["title"]: x for x in csvrows(exdir(research) / "exemplars.csv")}
    assert "Robust detection under dose shift with routed experts" not in rows                      # 5 < median(100, 5, 60) of CVPR 2025
    assert rows["Dose robust organ detection with adaptive routing"]["cited"] == "100" and rows["Detection under dose shift: a noise texture study"]["cited"] == "60"
    assert rows["Noise robust detection under dose shift"]["cited"] == "1"                          # alone in its venue-year: median is itself
    fresh = rows["Dose shift detection, this year's paper"]
    assert fresh["fresh"] == "1" and fresh["cited"] == "0"                                         # 0 < median would drop it, the current year is exempt
    assert "引用不足淘汰 1" in r.out and "未核引用数" not in r.out
    assert "未核引用数：范文质量只按刊物和年份过滤" in ex(research, papers).out                       # without --net / replay: BM25 + venue + year only


def test_journal_rows_use_cited_by_from_the_index(research, tmp_path):
    papers = world(tmp_path)
    make_pdf(papers / "TIP" / "2025" / "j.pdf"); make_pdf(papers / "TIP" / "2025" / "k.pdf")
    write(papers / "metadata" / "journals.csv", "journal,year,title,abstract,doi,local_path,cited_by\n"
          f'TIP,2025,"Dose shift detection for CT in TIP","dose shift detection",,{(papers / "TIP/2025/j.pdf").as_posix()},120\n'
          f'TIP,2025,"Dose shift detection, an obscure TIP paper","dose shift detection",,{(papers / "TIP/2025/k.pdf").as_posix()},3\n')
    replay = tmp_path / "replay"; replay.mkdir()
    ex(research, papers, "--from-dir", replay, venues="TIP")                                          # empty replay: any OpenAlex lookup would give "unknown", so the counts come from the index
    rows = {x["title"]: x["cited"] for x in csvrows(exdir(research) / "exemplars.csv")}
    assert rows == {"Dose shift detection for CT in TIP": "120"}, rows


def test_pdf_path_falls_back_to_the_papers_root(tmp_path):
    papers = tmp_path / "papers"; make_pdf(papers / "CVPR" / "2025" / "a.pdf"); make_pdf(papers / "nature" / "Nature" / "2025" / "n.pdf")
    assert fp.resolve_pdf("D:\\claude\\pajinsen\\papaer\\CVPR\\2025\\a.pdf", "CVPR", "2025", str(papers)) == str(papers / "CVPR" / "2025" / "a.pdf")   # original download folder is not on this machine
    assert fp.resolve_pdf("D:/x/Nature/2025/n.pdf", "Nature", "2025", str(papers)) == str(papers / "nature" / "Nature" / "2025" / "n.pdf")
    own = papers / "CVPR" / "2025" / "a.pdf"
    assert fp.resolve_pdf(str(own), "CVPR", "2025", "") == str(own)                                    # local_path wins when it exists
    assert fp.resolve_pdf("D:\\gone\\CVPR\\2025\\zzz.pdf", "CVPR", "2025", str(papers)) == "" and fp.resolve_pdf("", "CVPR", "2025", str(papers)) == ""


def test_candidates_without_a_readable_pdf_are_skipped_and_counted(research, tmp_path):
    papers = world(tmp_path)
    (papers / "CVPR" / "2025" / "a.pdf").rename(papers / "CVPR" / "2025" / "moved.pdf")
    idx = papers / "metadata" / "index.csv"
    edit(idx, (papers / "CVPR/2025/b.pdf").as_posix(), "D:\\claude\\pajinsen\\papaer\\CVPR\\2025\\b.pdf")   # fallback: <papers>/CVPR/2025/b.pdf
    r = ex(research, papers)
    t = titles(research)
    assert "Robust detection under dose shift with routed experts" in t and "Dose robust organ detection with adaptive routing" not in t, t
    assert "无本地 PDF 跳过 1" in r.out, r.out


# ------------------------------------------------------------------ exemplars: what is read from the PDFs
def test_figures_roles_widths_panels_and_thumbs(planned):
    figs = csvrows(exdir(planned) / "exemplar_figures.csv")
    one = [r for r in figs if r["paper_id"] == figs[0]["paper_id"]]
    f = {r["n"]: r for r in one if r["kind"] == "fig"}
    assert f["1"]["role"] == "motivation" and f["1"]["page"] == "1" and f["1"]["width"] == "double"
    assert f["2"]["role"] == "method" and f["2"]["page"] == "2" and f["2"]["width"] == "single" and int(f["2"]["panels"]) == 3 and "overview" in f["2"]["types"]
    assert f["3"]["role"] == "qualitative" and f["3"]["width"] == "single"
    assert f["4"]["role"] == "main_result"
    assert f["1"]["caption_first"].startswith("Motivation of dose-robust detection")
    t = [r for r in one if r["kind"] == "table"]
    assert len(t) == 1 and t[0]["role"] == "main_result" and t[0]["page"] == "2" and t[0]["caption_first"].startswith("Comparison with state-of-the-art")
    for r in figs:
        if r["kind"] == "fig": assert r["thumb"].startswith("literature/exemplars/thumbs/") and (planned / r["thumb"]).exists(), r
    assert (exdir(planned) / "thumbs" / f"{one[0]['paper_id']}_fig1.png").stat().st_size > 500


def test_table_roles_by_keywords():
    assert fp.table_role("Ablation of the routing module.") == "ablation" and fp.table_role("Params and FLOPs of each model.") == "efficiency"
    assert fp.table_role("Comparison with state-of-the-art methods.") == "main_result" and fp.table_role("Dataset statistics.") == "other"


def test_exemplars_md_has_the_role_table_and_stats(planned):
    md = read(exdir(planned) / "exemplars.md")
    assert "角色 × 范文" in md and "| motivation |" in md
    line = [l for l in md.splitlines() if l.startswith("| main_result |")][0]
    assert "3/4" in line or "4/4" in line
    assert "各角色最能说明问题的两句题注" in md and "范文中位" in md and "查询：" in md


# ------------------------------------------------------------------ plan
def test_claim_roles_for_each_evidence_key_form():
    c = lambda s, key="", ef="results/main.csv", exp="1": {"claim_id": "C", "statement": s, "evidence_key": key, "evidence_file": ef, "expected": exp}
    assert fp.claim_role(c("ours beats baseA by 19%", "rel:rmse:ours:baseA")) == "main_result"
    assert fp.claim_role(c("ours reaches 0.202", "mean:rmse:ours")) == "main_result"
    assert fp.claim_role(c("the gain comes from the term", "z:rmse:no_dom")) == "ablation"
    assert fp.claim_role(c("degradation is dominated by an offset", "", "prereg.md", "")) == "motivation"
    assert fp.claim_role(c("existing detectors degrade as the dose decreases", "")) == "motivation"
    assert fp.claim_role(c("ours degrades slowly as noise increases", "rel:x:ours:b")) == "analysis"
    assert fp.claim_role(c("qualitative examples show routing maps follow the lesion", "", exp="")) == "qualitative"
    assert fp.claim_role(c("we release the code", "", exp="")) == ""


def test_plan_maps_claims_to_roles_and_always_has_the_method_row(planned):
    write(planned / "paper" / "claims.csv", read(planned / "paper" / "claims.csv") + 'C5,"ours reaches 0.202 N RMSE on E1",E1,contact-window,results/summary.csv,mean:rmse_E1_mean:ours,0.202±0.002,Table 1,,yes\n')
    r = plan(planned)
    assert r.returncode == 0 and not r.crashed, r.out
    rows = plan_rows(planned)
    assert set(by(rows, role="main_result", kind="table")[0]["claim_ids"].split(";")) == {"C1", "C5"}
    assert set(by(rows, role="ablation", kind="table")[0]["claim_ids"].split(";")) == {"C2", "C3", "C4"}
    assert by(rows, role="motivation")[0]["claim_ids"] == "C0" and by(rows, role="method")[0]["claim_ids"] == ""
    assert [r["item"] for r in rows if r["kind"] == "figure"] == ["Fig 1", "Fig 2", "Fig 3", "Fig 4"]               # motivation, method, main, ablation in reading order
    assert (planned / "paper" / "figure_plan.md").exists()


def test_method_row_exists_without_any_claims(planned):
    write(planned / "paper" / "claims.csv", "claim_id,statement,dataset,metric_convention,evidence_file,evidence_key,expected,table_or_figure,scope_words,verified\n")
    plan(planned)
    rows = plan_rows(planned)
    assert [r["role"] for r in rows if r["role"] != "motivation"] == ["method"] and by(rows, role="motivation")[0]["claim_ids"] == ""   # the prereg §0 phenomenon alone still earns a motivation row
    assert "没有对应 claims 行" in by(rows, role="motivation")[0]["note"]


def test_form_rule_table_vs_figure_and_generators(planned):
    plan(planned)
    rows = plan_rows(planned)
    tab = by(rows, role="main_result", kind="table")[0]
    assert "make_comparison.py sota --csv results/main.csv" in tab["generator"] and "rmse_E1,rmse_E2" in tab["generator"] and "3 个方法 × 2 个指标" in tab["form_reason"]
    fig = by(rows, role="main_result", kind="figure")[0]
    assert "make_figure.py main --project ." in fig["generator"] and "范文" in fig["form_reason"]                  # >= half of the exemplars have a main-result figure
    assert by(rows, role="ablation", kind="table")[0]["generator"].startswith("make_comparison.py ablation --csv results/ablation.csv")
    assert by(rows, role="ablation", kind="figure")[0]["generator"].startswith("make_figure.py ablation")             # the fixture has seeds
    assert "make_architecture.py trace" in by(rows, role="method")[0]["generator"] and "make_motivation.py" in by(rows, role="motivation")[0]["generator"]
    # two methods only -> not worth a table: a figure
    main = planned / "results" / "main.csv"
    write(main, "".join(l for l in read(main).splitlines(True) if "baseB" not in l))
    plan(planned, "--force")
    rows = plan_rows(planned)
    assert not by(rows, role="main_result", kind="table") and "数字太少" in by(rows, role="main_result", kind="figure")[0]["form_reason"]


def test_no_main_result_figure_when_fewer_than_half_the_exemplars_have_one(planned):
    p = exdir(planned) / "exemplar_figures.csv"
    rows = csvrows(p)
    for r in rows:
        if r["kind"] == "fig" and r["role"] == "main_result": r["role"] = "analysis"
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    plan(planned)
    assert not by(plan_rows(planned), role="main_result", kind="figure")


def test_exemplar_reference_is_the_same_role_figure(planned):
    plan(planned)
    rows = plan_rows(planned)
    m = by(rows, role="method")[0]
    assert "Fig 2" in m["exemplar"] and "single" in m["exemplar"] and "3 面板" in m["exemplar"] and m["exemplar"].startswith("仿 ") and m["exemplar_caption"].startswith("Overview of the proposed framework")
    assert "Fig 1" in by(rows, role="motivation")[0]["exemplar"] and "Fig 4" in by(rows, role="main_result", kind="figure")[0]["exemplar"]
    assert "Table 1" in by(rows, role="main_result", kind="table")[0]["exemplar"]
    assert (planned / m["thumb"]).exists() and m["width"] == "single" and m["panels"] == "3"


def test_plan_refuses_to_overwrite_without_force(planned):
    assert plan(planned).returncode == 0
    write(planned / "paper" / "figure_plan.csv", read(planned / "paper" / "figure_plan.csv").replace("planned", "dropped", 1))
    r = plan(planned)
    assert r.fails == 1 and "--force" in r.out and "dropped" in read(planned / "paper" / "figure_plan.csv")
    assert plan(planned, "--force").returncode == 0 and "dropped" not in read(planned / "paper" / "figure_plan.csv")


def test_exemplar_only_role_is_reported_not_planned(planned):
    r = plan(planned)
    assert "范文 4/4 有 qualitative，本文没有对应主张" in r.out and "不要为了像而画" in r.out, r.out
    rows = plan_rows(planned)
    assert not by(rows, role="qualitative") and not by(rows, role="analysis")
    assert "[INFO] figure_plan: 范文" in read(planned / "paper" / "figure_plan.md") or "不要为了像而画" in read(planned / "paper" / "figure_plan.md")


def test_plan_counts_are_compared_with_the_exemplars_and_the_venue(planned):
    r = plan(planned)
    line = [l for l in r.out.splitlines() if "计划 4 图 2 表" in l][0]
    assert "范文中位 4 图 1 表" in line and ("[INFO]" in line or "[WARN]" in line)
    assert "family cs_journal" in line, line                                                                      # the fixture venue is not in the norms table: the family is


def test_plan_marks_figures_that_figures_csv_already_has_as_done(planned):
    plan(planned)
    rows = plan_rows(planned)
    assert by(rows, role="main_result", kind="figure")[0]["status"] == "done" and by(rows, role="ablation", kind="figure")[0]["status"] == "done"   # fig_main.*, fig_abl_a / fig_abl_b panels
    assert by(rows, role="method")[0]["status"] == "planned"


# ------------------------------------------------------------------ check
def chk(project): return run("figure_plan.py", "check", "--project", ".", cwd=project)


def draw_everything(project):
    """register the two figures the plan still waits for, so the untouched fixture plan is consistent"""
    for n in ("fig_motivation", "fig_arch"): shutil.copy(project / "figures" / "fig_main.pdf", project / "figures" / f"{n}.pdf")
    write(project / "figures.csv", read(project / "figures.csv") + "figures/fig_motivation.pdf,89,results/summary.csv,yes,\nfigures/fig_arch.pdf,89,results/summary.csv,yes,\n")


def test_check_without_a_plan_is_a_warning_not_a_failure(research):
    r = chk(research)
    assert r.returncode == 0 and "[WARN] figure_plan: 没有图表计划" in r.out, r.out


def test_check_passes_on_a_consistent_plan(planned):
    plan(planned); draw_everything(planned)
    r = chk(planned)
    assert r.returncode == 0 and "[PASS] figure_plan:" in r.out and "[WARN]" not in r.out, r.out


def test_check_warns_below_three_exemplars(planned):
    plan(planned); draw_everything(planned)
    p = exdir(planned) / "exemplars.csv"
    rows = csvrows(p)[:2]
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    r = chk(planned)
    assert r.returncode == 0 and "只有 2 篇范文" in r.out, r.out


def test_check_fails_on_a_planned_figure_that_is_not_drawn(planned):
    plan(planned)
    r = chk(planned)
    assert r.fails == 2 and "计划里的 Fig 1 还没画" in r.out and "计划里的 Fig 2 还没画" in r.out and "fig_main" not in r.out.split("还没画")[1], r.out


def test_check_fails_on_dropped_without_a_note_and_accepts_one_with_a_note(planned):
    plan(planned); draw_everything(planned)
    p = planned / "paper" / "figure_plan.csv"
    rows = csvrows(p)
    by(rows, role="ablation", kind="figure")[0].update(status="dropped", note="")
    def save():
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    save()
    r = chk(planned)
    assert r.fails == 1 and "标了 dropped 但 note 为空" in r.out, r.out
    by(rows, role="ablation", kind="figure")[0]["note"] = "表已够，Δ 图和 Table 里重复"; save()
    r = chk(planned)
    assert r.fails == 0 and "未计划的图" in r.out, r.out                                                         # its panels fig_abl_a / _b are now figures nobody plans


def test_check_warns_on_a_figure_no_row_covers(planned):
    plan(planned); draw_everything(planned)
    write(planned / "figures.csv", read(planned / "figures.csv") + "figures/fig_extra.pdf,89,results/summary.csv,yes,\n")
    r = chk(planned)
    assert r.returncode == 0 and "[WARN] figure_plan: 未计划的图 figures/fig_extra" in r.out and "它支撑哪条主张" in r.out, r.out


def test_plan_item_column_in_figures_csv_also_matches(planned):
    plan(planned)
    write(planned / "figures.csv", "file,print_width_mm,source_data,inspected,issues,plan_item\n" + "".join(l.rstrip("\n") + ",\n" for l in read(planned / "figures.csv").splitlines(True)[1:])
          + "figures/whatever_name.pdf,89,results/summary.csv,yes,,Fig 1\nfigures/other_name.pdf,89,results/summary.csv,yes,,Fig 2\n")
    r = chk(planned)
    assert r.fails == 0 and "未计划的图" not in r.out, r.out


def test_check_warns_on_a_numeric_claim_no_row_carries(planned):
    plan(planned); draw_everything(planned)
    p = planned / "paper" / "figure_plan.csv"
    rows = csvrows(p)
    for r in rows: r["claim_ids"] = ";".join(c for c in r["claim_ids"].split(";") if c != "C1")
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    r = chk(planned)
    assert "[WARN] figure_plan: 主张 C1 带数字但没有任何计划行承载" not in r.out                                    # C1 still sits in claims.table_or_figure = Table 1 -> the plan's Table 1
    edit(planned / "paper" / "claims.csv", "results/main.csv,rel:rmse_E1:ours:baseA,-19.2±0.15,Table 1", "results/main.csv,rel:rmse_E1:ours:baseA,-19.2±0.15,Table 9")
    r = chk(planned)
    assert r.returncode == 0 and "[WARN] figure_plan: 主张 C1 带数字但没有任何计划行承载" in r.out, r.out
    assert "主张 C0" not in r.out and "主张 C4" not in r.out                                                      # no key, no digits: nothing numeric to carry


def test_check_fails_when_a_row_names_a_claim_that_no_longer_exists(planned):
    plan(planned); draw_everything(planned)
    write(planned / "paper" / "claims.csv", "".join(l for l in read(planned / "paper" / "claims.csv").splitlines(True) if not l.startswith("C3,")))
    r = chk(planned)
    assert r.fails == 2 and r.out.count("引用了不存在的主张 C3") == 2, r.out                                        # the ablation table and the ablation figure both carry it


# ------------------------------------------------------------------ G5
def g5_line(project):
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=project)
    return [l for l in r.out.splitlines() if "G5" in l][0], r


def test_g5_line_carries_the_plan_counts_and_fails_on_an_undrawn_figure(planned):
    line, _ = g5_line(planned)
    assert "plan 0 FAIL / 1 WARN" in line and "没图表计划" not in line, line                                       # old project: no plan -> one WARN, no FAIL
    plan(planned)
    line, r = g5_line(planned)
    assert line.startswith("[FAIL] G5") and "plan 2 FAIL" in line, line
    draw_everything(planned)
    line, _ = g5_line(planned)
    assert "G5" in line and "plan 0 FAIL" in line and not line.startswith("[FAIL]"), line
