# -*- coding: utf-8 -*-
"""Per-venue experimental & structural norms from published PDFs.
   python venue_norms.py <corpus_dir> <out_csv>       corpus_dir/<venue>/*.pdf
Per paper: pages, abstract words, #figures, #tables, #display equations, #references,
           largest-table rows (proxy for #baselines), #datasets named (proxy), has ablation / limitations / broader-impact section,
           reports seeds / std / CI, #contribution bullets, ref recency (share of refs ≤3 y old), code link.
Aggregates by venue -> markdown table, written next to the csv."""
import sys, os, re, glob, csv, io, statistics, collections
import fitz
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

DATASETS = r"\b(ImageNet|COCO|CIFAR(?:-?10|-?100)?|KITTI|nuScenes|Waymo|ADE20K|Cityscapes|PASCAL|VOC|LVIS|Kinetics|UCF101|HMDB|MNIST|SVHN|CelebA|FFHQ|LSUN|ShapeNet|ScanNet|NYU|SUN RGB-D|MS-?MARCO|SQuAD|GLUE|WikiText|LibriSpeech|AudioSet|TCGA|UK Biobank|MIMIC|CheXpert|ChestX-?ray|ADNI|BraTS|LIDC|KiTS|AMOS|TotalSegmentator|Mayo|ISIC|HAM10000|CAMELYON|PANDA|GEO|GTEx|PDB|UniProt|ENCODE|TCIA|PhysioNet|eICU|OASIS|HCP|ABIDE|OpenImages|Objects365|YouTube-?VIS|DAVIS|Sintel|FlyingThings|Middlebury|ETH3D|DTU|Tanks and Temples|ScanNet\+\+|Replica|Matterport|Habitat|Gibson|RoboNet|Open X-Embodiment|ERA5|WeatherBench|CMIP|Landsat|Sentinel)\b"

def analyze(pdf):
    try:
        d = fitz.open(pdf)
    except Exception:
        return None
    if d.page_count < 4:
        return None
    text = "\n".join(p.get_text() for p in d)
    flat = re.sub(r"\s+", " ", text)
    r = {"paper": os.path.splitext(os.path.basename(pdf))[0][:50], "pages": d.page_count}
    # abstract
    m = re.search(r"Abstract[\s.—:-]*(.{200,3000}?)(?=\n\s*(?:1\.?\s+)?Introduction|\n\s*Keywords|\n\s*Index Terms)", text, re.S | re.I)
    r["abstract_words"] = len(m.group(1).split()) if m else ""
    # floats
    figs = {int(x) for x in re.findall(r"(?:^|\n)\s*(?:Figure|Fig\.)\s*(\d+)\s*[:.]", text)}
    tabs = {int(x) for x in re.findall(r"(?:^|\n)\s*(?:Table|TABLE)\s*(\d+)\s*[:.]", text)}
    r["figures"] = max(figs) if figs else 0
    r["tables"] = max(tabs) if tabs else 0
    r["equations"] = len(set(re.findall(r"\((\d{1,3})\)\s*\n", text)))
    # references
    mref = re.search(r"\n\s*(References|REFERENCES)\s*\n", text)
    refs = text[mref.end():] if mref else ""
    body = text[:mref.start()] if mref else text
    nref = len(re.findall(r"^\[\d+\]\s", refs, re.M)) or len(re.findall(r"^\d{1,3}\.?\s*[\t\xa0 ]+[A-Z]", refs, re.M)) or len(re.findall(r"\n[A-Z][A-Za-z'’\-]+,\s+[A-Z]\.", refs))
    r["references"] = nref
    years = [int(y) for y in re.findall(r"\b(19[89]\d|20[0-2]\d)\b", refs)]
    pub = max([int(y) for y in re.findall(r"\b(20[12]\d)\b", text[:3000])] or [0])
    r["pub_year"] = pub or ""
    if years and pub:
        r["refs_recent_share"] = round(sum(1 for y in years if pub - y <= 3) / len(years), 2)
    else:
        r["refs_recent_share"] = ""
    # sections
    bl = body.lower()
    r["has_ablation"] = int(bool(re.search(r"\n\s*(?:\d+(?:\.\d+)*\s+)?ablation", bl)) or "ablation stud" in bl)
    r["has_limitations"] = int(bool(re.search(r"\n\s*(?:\d+(?:\.\d+)*\s+)?limitation", bl)))
    r["has_broader_impact"] = int("broader impact" in bl or "societal impact" in bl or "ethic" in bl[:len(bl)])
    r["has_related_work"] = int(bool(re.search(r"\n\s*(?:\d+\s+)?related work", bl)))
    # statistics reporting
    r["reports_std"] = int(bool(re.search(r"±|\\pm|standard deviation|std\.?\b|\bs\.d\.", body)))
    r["reports_seeds"] = int(bool(re.search(r"\b(\d+|three|five|ten)\s+(random\s+)?seeds?\b|\bseeds?\s*(=|:)", body, re.I)))
    r["reports_ci"] = int(bool(re.search(r"confidence interval|\b95\s*%\s*CI\b|\bCI\s*[:=]", body)))
    r["reports_pvalue"] = int(bool(re.search(r"\bp\s*[<=]\s*0?\.\d+|p-value", body, re.I)))
    r["code_link"] = int(bool(re.search(r"github\.com/|gitlab\.com/|code (?:is|will be) (?:publicly )?available", body, re.I)))
    # contributions
    cm = re.search(r"(?:our|the|main)\s+contributions?\s+(?:of this (?:paper|work)\s+)?(?:are|can be|is)\s+(?:summarized|summarised|listed|as follows|three|four|two|threefold|fourfold|twofold)[^\n]{0,80}\n(.{0,2500}?)(?=\n\s*\d+\.?\s+[A-Z][a-z]|\n\s*2\s)", body, re.S | re.I)
    if cm:
        r["contrib_bullets"] = len(re.findall(r"(?:^|\n)\s*(?:•|–|-|\*|\(\d\)|\d\)|\(?[ivx]+\)|\d\.)\s", cm.group(1)))
    else:
        r["contrib_bullets"] = ""
    # datasets & baselines proxies
    r["datasets_named"] = len(set(x.lower() for x in re.findall(DATASETS, body)))
    # largest table: count rows between a Table caption and the next blank-ish line, approximated by lines with ≥3 numeric cells
    best = 0
    for block in re.split(r"\n\s*(?:Table|TABLE)\s*\d+", body)[1:]:
        seg = block[:6000]
        rows = [l for l in seg.splitlines() if len(re.findall(r"\d+\.\d+", l)) >= 3]
        best = max(best, len(rows))
    r["largest_table_rows"] = best
    r["sota_claim"] = int(bool(re.search(r"state[- ]of[- ]the[- ]art", bl)))
    return r

def main(corpus, out_csv):
    rows = []
    for pdf in sorted(glob.glob(os.path.join(corpus, "*", "*.pdf"))):
        r = analyze(pdf)
        if r:
            r["venue"] = os.path.basename(os.path.dirname(pdf)); rows.append(r)
            print(f"{r['venue']:10s} {r['paper'][:36]:36s} p{r['pages']:3d} fig{r['figures']:2d} tab{r['tables']:2d} ref{r['references']:3d} abl{r['has_ablation']} std{r['reports_std']} seed{r['reports_seeds']} ci{r['reports_ci']} ds{r['datasets_named']:2d} rows{r['largest_table_rows']:2d}")
    keys = ["venue", "paper", "pub_year", "pages", "abstract_words", "figures", "tables", "equations", "references", "refs_recent_share", "has_related_work", "has_ablation", "has_limitations", "has_broader_impact", "reports_std", "reports_seeds", "reports_ci", "reports_pvalue", "code_link", "contrib_bullets", "datasets_named", "largest_table_rows", "sota_claim"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in keys})
    # aggregate
    by = collections.defaultdict(list)
    for r in rows: by[r["venue"]].append(r)
    def med(v, k):
        xs = [float(r[k]) for r in v if r.get(k) not in ("", None)]
        return f"{statistics.median(xs):.0f}" if xs else "-"
    def pct(v, k):
        xs = [r[k] for r in v if r.get(k) not in ("", None)]
        return f"{100*sum(xs)/len(xs):.0f}%" if xs else "-"
    lines = ["| venue | n | 页 | 摘要词 | 图 | 表 | 公式 | 参考文献 | 近3年文献占比 | 命名数据集 | 最大表行数 | 消融节 | 局限节 | 报告 std | 报告 seed | 报告 CI | p 值 | 开源链接 | SOTA 用词 |", "|---|" + "---|" * 18]
    for v in sorted(by):
        x = by[v]
        lines.append(f"| {v} | {len(x)} | {med(x,'pages')} | {med(x,'abstract_words')} | {med(x,'figures')} | {med(x,'tables')} | {med(x,'equations')} | {med(x,'references')} | {med(x,'refs_recent_share') if False else (lambda xs: f'{statistics.median(xs):.0%}' if xs else '-')([float(r['refs_recent_share']) for r in x if r['refs_recent_share']!=''])} | {med(x,'datasets_named')} | {med(x,'largest_table_rows')} | {pct(x,'has_ablation')} | {pct(x,'has_limitations')} | {pct(x,'reports_std')} | {pct(x,'reports_seeds')} | {pct(x,'reports_ci')} | {pct(x,'reports_pvalue')} | {pct(x,'code_link')} | {pct(x,'sota_claim')} |")
    io.open(os.path.splitext(out_csv)[0] + ".md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Per-venue structural/experimental norms from corpus_dir/<venue>/*.pdf -> out_csv (+ .md)")
    ap.add_argument("corpus_dir"); ap.add_argument("out_csv")
    a = ap.parse_args(); main(a.corpus_dir, a.out_csv)
