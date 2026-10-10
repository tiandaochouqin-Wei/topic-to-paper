# -*- coding: utf-8 -*-
"""Figure-type norms of published papers, per venue / family / topic group — the data behind references/figure-norms.md.

  sample  python figure_norms.py sample --papers Z:/LDCT/papers --per-venue 40 --since 2023 --seed 20261010 --out references/figure-norms-per-paper.csv
  report  python figure_norms.py report --per-paper references/figure-norms-per-paper.csv --out references/figure-norms.md
  reclassify  python figure_norms.py reclassify   re-apply the rules to the saved captions after editing FIGURE_TYPES (no PDF reading)

sample: stratified random sample of PDFs per venue (conference dirs <venue>/<year>/*.pdf, Nature family nature/<journal>/<year>/*.pdf),
        text layer only. For every figure caption ("Fig. N" / "Figure N" at line start, up to the next blank line) it records the
        figure types the caption names (multi-label keyword rules, FIGURE_TYPES below), whether the caption has lettered panels,
        whether it reports statistics (n =, error bars, ± s.d.); per paper: figures, tables, teaser on page 1, raster images and
        vector paths (how the figures were embedded). Topic group from the metadata keyword (matched_kw / field) plus the title.
        Writes <out> (one row per paper) and <out stem>-per-figure.csv (one row per caption, with the caption text).
report: per venue, per family and per topic group: share of papers that contain each figure type, median figures per paper,
        multi-panel share, statistics-in-caption share, all-vector share; plus the five most common types per family."""
import argparse, collections, csv, glob, io, os, random, re, statistics, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

FAMILY = {"CVPR": "cs_conf", "ICCV": "cs_conf", "ECCV": "cs_conf", "WACV": "cs_conf", "NeurIPS": "cs_conf", "ICML": "cs_conf", "AAAI": "cs_conf", "IJCAI": "cs_conf", "MM": "cs_conf", "MICCAI": "cs_conf",
          "TPAMI": "cs_journal", "TIP": "cs_journal", "IJCV": "cs_journal"}
# figure types: (name, regex on the caption text). Multi-label; order = report order.
FIGURE_TYPES = [
    ("overview",    r"\b(overview|architectures?|frameworks?|pipelines?|schematics?|workflows?|block diagrams?|illustration of (our|the proposed)|our (method|approach|model) consists|flow of|(training|inference|overall) (procedure|process|scheme)|module designs?|structure of (our|the)|the proposed [\w-]+ (module|block|layer|network))\b"),
    ("concept",     r"\b(motivation|conceptual|intuition|our (key )?idea|toy example|illustrative example|comparison between (the )?(conventional|existing|previous|standard)|we (present|propose|introduce)|given (a|an|the) [\w-]+,|problem (setting|formulation)|task (setting|definition)|unlike (previous|existing|prior))\b"),
    ("qualitative", r"\b(qualitative|visual comparison|visuali[sz](ation|e|ing)|examples? of|sample results|generated (images|samples|results)|reconstruct(ed|ion) results|segmentation results|detection results|predicted (masks|boxes|maps)|rendered|zoom(ed)?[- ]in|red box(es)?|close[- ]ups?|representative (examples|results|cases|images?))\b"),
    ("comparison",  r"\b(comparison (results|of|between|with|on)|compared (to|with|against)|success rates?|performance (of|on|comparison|across)|results? (of|on|for) (the )?[\w-]+ (benchmark|dataset|task)|accuracy (of|on)|error (of|on|across)|outperforms?)\b"),
    ("curves",      r"\b(curves?|plot of|versus|vs\.?|as a function of|with respect to|w\.r\.t\.|trade[- ]off|pareto|convergence|training (loss|curve|dynamics)|over (training )?(epochs|iterations|steps)|learning curve|evolution of|during (training|optimization))\b"),
    ("bars",        r"\b(bar (chart|plot|graph)s?|histograms?|distribution of)\b"),
    ("ablation",    r"\b(ablation|effect of|impact of|influence of|sensitivity|hyper-?parameters?|varying|different (numbers?|values|settings) of)\b"),
    ("embedding",   r"\b(t-?sne|umap|pca\b|feature (space|distribution|embedding)|embedding (space|visualization)|latent space)\b"),
    ("heatmap",     r"\b(attention maps?|heat ?maps?|saliency|grad-?cam|activation maps?|class activation|response maps?|feature maps?)\b"),
    ("confusion",   r"\bconfusion matri(x|ces)\b"),
    ("roc_pr",      r"\b(roc|receiver operating|precision[- ]recall|pr curves?|auc|auroc|calibration (curve|plot)|reliability diagram)\b"),
    ("scatter",     r"\b(scatter|correlation|bland[- ]altman|agreement|regression (line|plot)|pearson|spearman|r\s*=\s*0?\.\d)\b"),
    ("boxplot",     r"\b(box ?plots?|violin|whiskers?|boxes? (show|indicate|represent)|interquartile)\b"),
    ("failure",     r"\b(failure (cases?|modes?)|hard (cases|examples)|error cases|fails? to|limitations? of (our|the) (method|model|approach))\b"),
    ("dataset",     r"\b(examples? (from|of) (the |our )?(dataset|benchmark|data)|statistics of (the |our )?(dataset|data)|dataset (overview|statistics|examples|construction)|number of (images|samples|videos|subjects|patients) (per|in)|annotation (process|pipeline|examples|interface)|data (collection|acquisition) (setup|process|pipeline)|experimental (setup|settings?|design|protocol)|evaluation protocol|our (dataset|benchmark) (contains|consists|covers))\b"),
    ("flowchart",   r"\b(flow ?chart|flow diagram|prisma|consort|study design|cohort|inclusion|screening|enrol+ment|patient selection)\b"),
    ("clinical",    r"\b(kaplan|survival|forest plot|hazard ratio|odds ratio|cumulative incidence)\b"),
    ("micrograph",  r"\b(micrograph|microscop|immunofluorescence|staining|western blot|gel|histolog|h&e|representative images? of (cells|tissue|mice))\b"),
    ("wetlab",      r"\b(immunoprecipitation|immunoblot|blot|qpcr|rt-pcr|flow cytometry|facs|elisa|assays?|knock-?out|knock-?down|sirna|crispr|overexpress|transfect|incubat|treated with|wild-?type|mutant|cells were|mice were|in vivo|in vitro|sequencing|rna-seq|scrna|chip-seq|binding (assay|affinity)|bli\b)\b"),
    ("map",         r"\b(map of|spatial distribution|geograph|satellite|remote sensing|study area)\b"),
]
PANEL_RE = re.compile(r"\((?:a|b|A|B)\d?\)|(?:^|[.;:]\s*)[a-h](?:[–-][a-h])?[\s,]+[A-Z]|\b(?:panels?|left|right|top|bottom|first|second) (?:row|column|panel|block)s?\b|\b[Pp]anels?\b", re.M)   # (a)(b); Nature "a Outline…, b–e …"; top row / left panel
STAT_RE = re.compile(r"\bn\s*=\s*\d|error bars?|mean\s*±|±\s*s\.?d|s\.e\.m|standard deviation|confidence interval|95\s*%|p\s*[<=]\s*0\.\d|two-sided|wilcoxon|t-test", re.I)
CAP_RE = re.compile(r"(?m)^[ \t]*(?:Fig\.|Figure|FIGURE)\s*(\d{1,2})\s*(?:[.:|]\s*|(?=\s+[A-Z]))")   # "Fig. 1." / "Figure 1:" / Nature "Fig. 1 |" / Springer "Fig. 1 Caption"

TOPIC_RULES = [
    ("medical",      r"\b(medical|clinical|patient|tumou?r|lesion|mri|ct\b|ultrasound|histopath|radiolog|pathology|whole[- ]slide|wsi|cancer|disease|diagnos|hospital|surg|endoscop|x-ray|radiograph|retina|fundus|organ|brain|cardiac|placenta|covid|ecg|eeg)\b"),
    ("remote_sensing", r"\b(remote sensing|hyperspectral|satellite|aerial|sar\b|uav|land cover|change detection|optical remote)\b"),
    ("low_level",    r"\b(super-?resolution|denois|restoration|deblur|dehaz|derain|inpaint|enhancement|compression|image quality|low[- ]light|hdr|demosaic|artifact|light field|image fusion|tone mapping)\b"),
    ("generative",   r"\b(generat|diffusion|gan\b|synthesis|text-to-image|editing|style transfer|nerf|gaussian splatting|novel view|rendering|avatar|talking)\b"),
    ("perception3d", r"\b(3d|point cloud|depth|stereo|lidar|reconstruction|pose|slam|mesh|voxel|multi-?view|scene)\b"),
    ("vlm",          r"\b(vision-?language|multi-?modal|clip\b|prompt|caption|vqa|cross-?modal|zero-?shot|few-?shot|llm|language model|grounding|open-?vocabulary|embodied|robot)\b"),
    ("video",        r"\b(video|temporal|action|motion|tracking|optical flow|frame interpolation)\b"),
    ("perception2d", r"\b(detection|segmentation|recognition|classification|re-?identification|face|person|keypoint|landmark|ocr|counting|crowd)\b"),
    ("ml_methods",   r"\b(adversarial|robust|uncertainty|calibrat|domain adaptation|generali[sz]ation|self-?supervised|contrastive|representation|distillation|unsupervised|semi-?supervised|continual|federated|pruning|quantization|optimization|bayesian|causal|fairness|explain|interpretab|graph neural|reinforcement)\b"),
]
NATURE_FIELD = {"Medicine": "medical", "Health Professions": "medical", "Nursing": "medical", "Computer Science": "cs_in_nature", "Engineering": "cs_in_nature", "Mathematics": "cs_in_nature",
                "Physics and Astronomy": "physical", "Chemistry": "physical", "Materials Science": "physical", "Earth and Planetary Sciences": "physical", "Environmental Science": "physical", "Energy": "physical"}


def topic_group(venue, kw, title, field):
    if venue == "MICCAI": return "medical"
    if field is not None:   # Nature family
        return NATURE_FIELD.get(field, "life_sciences" if field else "unknown")
    text = (kw or "") + " " + (title or "")
    for name, rx in TOPIC_RULES:
        if re.search(rx, text, re.I): return name
    return "other"


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:60]


def load_metadata(papers_root):
    """filename-stem -> (matched_kw, title) for conferences/journals; normalised title -> field for Nature."""
    kw_by_stem = {}; title_by_norm = {}; field_by_norm = {}
    p = os.path.join(papers_root, "metadata", "index.csv")
    if os.path.exists(p):
        for r in csv.DictReader(io.open(p, encoding="utf-8-sig", errors="replace")):
            lp = (r.get("local_path") or "").replace("\\", "/"); stem = os.path.splitext(os.path.basename(lp))[0] if lp else ""
            if stem: kw_by_stem[stem] = (r.get("matched_kw") or "", r.get("title") or "")
            title_by_norm[norm_title(r.get("title"))] = r.get("matched_kw") or ""
    for p in (os.path.join(papers_root, "metadata", "journals.csv"),):
        if os.path.exists(p):
            for r in csv.DictReader(io.open(p, encoding="utf-8-sig", errors="replace")):
                title_by_norm[norm_title(r.get("title"))] = r.get("matched_kw") or ""
    p = os.path.join(papers_root, "nature", "metadata", "journals.csv")
    if os.path.exists(p):   # Nature-family PDFs are named by OpenAlex work id (W…pdf): map that id to field and title
        for r in csv.DictReader(io.open(p, encoding="utf-8-sig", errors="replace")):
            oa = (r.get("openalex_id") or "").rsplit("/", 1)[-1].strip()
            if oa: field_by_norm[oa] = (r.get("field") or "", r.get("title") or "")
            lp = (r.get("local_path") or "").replace("\\", "/"); stem = os.path.splitext(os.path.basename(lp))[0] if lp else ""
            if stem and stem not in field_by_norm: field_by_norm[stem] = (r.get("field") or "", r.get("title") or "")
    return kw_by_stem, title_by_norm, field_by_norm


def captions_of(full, body_end):
    """[(fig_no, caption_text)] — caption = text from the marker to the next blank line (≤ 600 chars), first occurrence per number"""
    out = {}
    text = full[:body_end]
    for m in CAP_RE.finditer(text):
        n = int(m.group(1))
        if n in out or n > 40: continue
        rest = text[m.end():m.end() + 600]
        stop = re.search(r"\n\s*\n", rest)
        cap = rest[:stop.start()] if stop else rest
        cap = re.sub(r"\s*\n\s*", " ", cap).strip()
        if len(cap) < 15: continue
        out[n] = cap
    return sorted(out.items())


def analyze(pdf, venue, family, topic):
    import fitz
    try: d = fitz.open(pdf)
    except Exception: return None, []
    pages = [p.get_text() for p in d]; full = "\n".join(pages)
    if len(full) < 3000: return None, []
    rm = re.search(r"\n\s*(references|bibliography)\s*\n", full, re.I)
    body_end = rm.start() if rm and rm.start() > len(full) * 0.4 else len(full)
    caps = captions_of(full, body_end)
    n_img = sum(len(p.get_images(full=True)) for p in d)
    try: n_vec = sum(len(p.get_drawings()) for p in d)
    except Exception: n_vec = -1
    r = {"paper": os.path.splitext(os.path.basename(pdf))[0][:70], "venue": venue, "family": family, "topic": topic, "pages": len(d),
         "n_fig": len(caps), "n_tab": len(set(re.findall(r"(?m)^\s*(?:Table|TABLE)\s*(\d{1,2})\s*[.:|]", full[:body_end]))),
         "teaser_p1": int(bool(re.search(r"(Fig\.|Figure)\s*1\s*[.:|]", pages[0]))) if pages else 0,
         "raster_images": n_img, "vector_paths": n_vec, "all_vector": int(n_img == 0 and len(caps) > 0),
         "multi_panel": sum(1 for _, c in caps if PANEL_RE.search(c)), "stat_caption": sum(1 for _, c in caps if STAT_RE.search(c))}
    for name, _ in FIGURE_TYPES: r[name] = 0
    fig_rows = []
    for n, c in caps:
        types = [name for name, rx in FIGURE_TYPES if re.search(rx, c, re.I)]
        for t in types: r[t] += 1
        fig_rows.append({"venue": venue, "family": family, "topic": topic, "paper": r["paper"], "fig": n, "types": "|".join(types) or "unclassified",
                         "panels": int(bool(PANEL_RE.search(c))), "stats": int(bool(STAT_RE.search(c))), "caption": c})   # full caption (≤600 chars) so `reclassify` sees what `sample` saw
    r["unclassified"] = sum(1 for fr in fig_rows if fr["types"] == "unclassified")
    return r, fig_rows


def sample(a):
    random.seed(a.seed)
    kw_by_stem, title_by_norm, field_by_norm = load_metadata(a.papers)
    venues = [v.strip() for v in a.venues.split(",") if v.strip()]
    rows = []; figs = []
    for v in venues:
        root = os.path.join(a.papers, "nature", v) if os.path.isdir(os.path.join(a.papers, "nature", v)) else os.path.join(a.papers, v)
        pdfs = [p for y in sorted(os.listdir(root)) if y.isdigit() and int(y) >= a.since for p in glob.glob(os.path.join(root, y, "*.pdf"))] if os.path.isdir(root) else []
        if not pdfs: print(f"[WARN] {v}: no PDFs under {root}"); continue
        pick = random.sample(pdfs, min(a.per_venue, len(pdfs)))
        fam = FAMILY.get(v, "nature"); done = 0
        for pdf in pick:
            stem = os.path.splitext(os.path.basename(pdf))[0]
            title_guess = re.sub(r"[_\-]+", " ", re.sub(r"__.*$|_(CVPR|ICCV|ECCV|WACV|NeurIPS|ICML|AAAI|IJCAI|MICCAI)_\d{4}.*$", "", stem))
            kw, title = kw_by_stem.get(stem, ("", title_guess)); kw = kw or title_by_norm.get(norm_title(title_guess), "")
            field = None
            if fam == "nature":
                field, nt = field_by_norm.get(stem, ("", "")); title = nt or title
            r, fr = analyze(pdf, v, fam, topic_group(v, kw, title or title_guess, field))
            if r is None: continue
            r["year"] = os.path.basename(os.path.dirname(pdf)); r["title"] = (title or title_guess)[:120]; rows.append(r); figs += fr; done += 1
        print(f"{v:14s} {done:3d} papers, {sum(r['n_fig'] for r in rows if r['venue'] == v):4d} figure captions")
    cols = ["paper", "title", "venue", "family", "topic", "year", "pages", "n_fig", "n_tab", "teaser_p1", "raster_images", "vector_paths", "all_vector", "multi_panel", "stat_caption", "unclassified"] + [n for n, _ in FIGURE_TYPES]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    fp = per_figure_path(a.out)
    with io.open(fp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["venue", "family", "topic", "paper", "fig", "types", "panels", "stats", "caption"]); w.writeheader(); w.writerows(figs)
    print(f"-> {a.out} ({len(rows)} papers), {fp} ({len(figs)} captions)")


def per_figure_path(per_paper):
    """figure-norms-per-paper.csv -> figure-norms-per-figure.csv (any other stem gets -per-figure appended)"""
    stem = re.sub(r"-per-paper$", "", os.path.splitext(per_paper)[0])
    return stem + "-per-figure.csv"


def reclassify(a):
    """re-apply FIGURE_TYPES / PANEL_RE / STAT_RE to the saved captions and refresh the per-paper type counts (no PDF reading)"""
    fp = per_figure_path(a.per_paper)
    figs = list(csv.DictReader(io.open(fp, encoding="utf-8-sig"))); papers = list(csv.DictReader(io.open(a.per_paper, encoding="utf-8-sig")))
    counts = collections.defaultdict(lambda: collections.Counter())
    for fr in figs:
        types = [name for name, rx in FIGURE_TYPES if re.search(rx, fr["caption"], re.I)]
        fr["types"] = "|".join(types) or "unclassified"; fr["panels"] = int(bool(PANEL_RE.search(fr["caption"]))); fr["stats"] = int(bool(STAT_RE.search(fr["caption"])))
        c = counts[(fr["venue"], fr["paper"])]
        for t in types: c[t] += 1
        c["unclassified"] += int(not types); c["multi_panel"] += fr["panels"]; c["stat_caption"] += fr["stats"]
    names = [n for n, _ in FIGURE_TYPES] + ["unclassified", "multi_panel", "stat_caption"]
    for p in papers:
        c = counts.get((p["venue"], p["paper"]), collections.Counter())
        for n in names: p[n] = c.get(n, 0)
    cols = list(papers[0].keys()) if papers else []
    for n in names:
        if n not in cols: cols.append(n)
    with io.open(a.per_paper, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(papers)
    with io.open(fp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["venue", "family", "topic", "paper", "fig", "types", "panels", "stats", "caption"]); w.writeheader(); w.writerows(figs)
    print(f"reclassified {len(figs)} captions in {len(papers)} papers; unclassified {sum(1 for x in figs if x['types'] == 'unclassified')}")


def report(a):
    rows = list(csv.DictReader(io.open(a.per_paper, encoding="utf-8-sig")))
    types = [n for n, _ in FIGURE_TYPES]
    def pct(xs, k): return f"{100 * sum(1 for x in xs if int(float(x[k] or 0)) > 0) / len(xs):.0f}%" if xs else "-"
    def med(xs, k): return f"{statistics.median(int(float(x[k] or 0)) for x in xs):.0f}" if xs else "-"
    def share(xs, num, den):
        n = sum(int(float(x[num] or 0)) for x in xs); d = sum(int(float(x[den] or 0)) for x in xs); return f"{100 * n / d:.0f}%" if d else "-"
    def block(title, key):
        groups = collections.OrderedDict()
        for r in rows: groups.setdefault(r[key], []).append(r)
        L = [f"## {title}", "", "| 组 | n | 图/篇 | 表/篇 | 首页 teaser | 多面板图占比 | 题注含统计 | 全矢量篇占比 | " + " | ".join(types) + " |", "|---|" + "---|" * (8 + len(types))]
        for g, xs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            L.append(f"| {g} | {len(xs)} | {med(xs, 'n_fig')} | {med(xs, 'n_tab')} | {pct(xs, 'teaser_p1')} | {share(xs, 'multi_panel', 'n_fig')} | {share(xs, 'stat_caption', 'n_fig')} | {pct(xs, 'all_vector')} | " + " | ".join(pct(xs, t) for t in types) + " |")
        return L + [""]
    L = ["# 已发表论文的图类型规范（`scripts/figure_norms.py`，题注关键词归类，多标签）", "",
         f"样本 {len(rows)} 篇，按 venue 分层随机抽样；每格 = 该组里至少有一张此类图的论文占比。类型由题注关键词判定，一张图可属多类；`unclassified` 是没命中任何规则的图。逐篇原始值 `figure-norms-per-paper.csv`，逐图题注 `figure-norms-per-figure.csv`。", "",
         "图类型说明：overview 架构/流程总览；concept 动机/概念对比；qualitative 定性结果/视觉对比/示例；comparison 定量对比（柱/线未指明）；curves 曲线（随参数/epoch/阈值变化、trade-off）；bars 柱状/直方；ablation 消融/敏感性；embedding t-SNE/特征空间；heatmap 注意力/显著性/特征图；confusion 混淆矩阵；roc_pr ROC/PR/校准曲线；scatter 散点/相关/Bland–Altman；boxplot 箱线/小提琴；failure 失败案例；dataset 数据集示例/统计/实验设置；flowchart 流程图/PRISMA/队列；clinical 生存/森林图；micrograph 显微/染色/凝胶；wetlab 湿实验（免疫沉淀、qPCR、流式、敲除…）；map 地理/遥感。「全矢量篇占比」按 PDF 内无任何栅格图像估算，照片与出版社栅格化会把它压到接近 0，只作参考。", ""]
    L += block("按 venue", "venue") + block("按家族", "family") + block("按主题组", "topic")
    # top-5 per family
    L += ["## 每个家族最常见的五种图（含该类图的论文占比）", ""]
    fams = collections.OrderedDict()
    for r in rows: fams.setdefault(r["family"], []).append(r)
    for fam, xs in fams.items():
        ranked = sorted(types, key=lambda t: -sum(1 for x in xs if int(float(x[t] or 0)) > 0))[:5]
        L.append(f"- **{fam}**（n={len(xs)}）：" + "、".join(f"{t} {pct(xs, t)}" for t in ranked) + f"；图/篇中位 {med(xs, 'n_fig')}，多面板 {share(xs, 'multi_panel', 'n_fig')}，题注含统计 {share(xs, 'stat_caption', 'n_fig')}")
    L.append("")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    io.open(a.out, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print("\n".join(L[:12])); print(f"... -> {a.out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample"); s.add_argument("--papers", required=True); s.add_argument("--per-venue", type=int, default=40); s.add_argument("--since", type=int, default=2023); s.add_argument("--seed", type=int, default=20261010)
    s.add_argument("--venues", default="CVPR,ICCV,NeurIPS,ICML,AAAI,MICCAI,TPAMI,TIP,IJCV,Nature,NatCommun,NatMedicine,NatBiomedEng,NatMachIntell,NatMethods"); s.add_argument("--out", default="references/figure-norms-per-paper.csv")
    r = sub.add_parser("report"); r.add_argument("--per-paper", default="references/figure-norms-per-paper.csv"); r.add_argument("--out", default="references/figure-norms.md")
    c = sub.add_parser("reclassify"); c.add_argument("--per-paper", default="references/figure-norms-per-paper.csv")
    a = ap.parse_args()
    {"sample": sample, "report": report, "reclassify": reclassify}[a.cmd](a)
