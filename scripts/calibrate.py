# -*- coding: utf-8 -*-
"""Calibrate topic-to-paper gates on a corpus of published PDFs.
   python calibrate.py <corpus_dir> <out_dir>      corpus_dir/<venue>/*.pdf
Writes out_dir/calib.csv (one row per paper) and out_dir/calib_by_venue.md.
Each floats FAIL is re-verified against the raw PDF text (grouped references expanded), so
the report separates converter artefacts from genuine orphan floats."""
import sys, os, re, io, csv, json, subprocess, glob, collections
import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
PDF2MD = os.path.join(HERE, "pdf_to_md.py")
GATE = os.path.join(HERE, "gate_check.py")

def run(cmd, cwd=None, timeout=300):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return "TIMEOUT"

def raw_text(pdf):
    try:
        d = fitz.open(pdf)
        return re.sub(r"\s+", " ", "\n".join(p.get_text() for p in d)), len(d)
    except Exception:
        return "", 0

def verify_orphan(raw, kind, n):
    """True if the PDF text cites float n at least once outside its own caption (grouped refs expanded)."""
    if kind == "fig":
        pat = rf"(Fig(?:ure|s?\.)|Figures)\s*((?:S?\d+[a-z]?\s*(?:,|and|–|-|to)\s*)*)S?{n}(?![\d])"
        cap = rf"(Figure|Fig\.)\s*{n}\s*[:.]"
    else:
        pat = rf"(Tab(?:le|\.)|Tables)\s*((?:S?\d+[a-z]?\s*(?:,|and|–|-|to)\s*)*)S?{n}(?![\d])"
        cap = rf"(Table|TABLE)\s*{n}\s*[:.]"
    hits = list(re.finditer(pat, raw, re.I))
    cites = [m for m in hits if not re.match(cap, raw[m.start():m.start() + 14], re.I)]
    # ranges "Figs. 4–7"
    for m in re.finditer(r"(Fig(?:ure|s?\.)|Figures|Tab(?:le|\.)|Tables)\s*S?(\d+)\s*(?:–|-|to)\s*S?(\d+)", raw, re.I):
        k = "fig" if m.group(1).lower().startswith("f") else "table"
        if k == kind and int(m.group(2)) <= int(n) <= int(m.group(3)):
            cites.append(m)
    return len(cites) > 0

def main(corpus, out):
    os.makedirs(out, exist_ok=True)
    rows = []
    pdfs = sorted(glob.glob(os.path.join(corpus, "*", "*.pdf")))
    for i, pdf in enumerate(pdfs, 1):
        venue = os.path.basename(os.path.dirname(pdf))
        name = os.path.splitext(os.path.basename(pdf))[0][:60]
        wd = os.path.join(out, "work", venue, name)
        os.makedirs(wd, exist_ok=True)
        conv = run([sys.executable, PDF2MD, pdf, wd], timeout=180)
        row = {"venue": venue, "paper": name, "pages": 0, "converted": os.path.exists(os.path.join(wd, "paper", "manuscript.md"))}
        if not row["converted"]:
            row["error"] = conv.strip().splitlines()[-1][:120] if conv.strip() else "no output"
            rows.append(row); print(f"[{i}/{len(pdfs)}] {venue}/{name}: CONVERT FAIL"); continue
        io.open(os.path.join(wd, "research-state.yaml"), "w", encoding="utf-8").write("acronym_ok: []\nblind_terms: []\ntarget:\n  min_dpi: 300\n")
        m = re.search(r"pages (\d+), refs (\d+) \(doi (\d+), arxiv (\d+)\), raster figs (\d+)", conv)
        if m:
            row.update(pages=int(m.group(1)), refs=int(m.group(2)), refs_doi=int(m.group(3)), refs_arxiv=int(m.group(4)), rasters=int(m.group(5)))
        raw, _ = raw_text(pdf)
        # floats
        o = run([sys.executable, GATE, "floats"], cwd=wd)
        orphans, dangling = [], []
        for mm in re.finditer(r"\[FAIL\] floats: (fig|table) 无人引用: \[([^\]]*)\]", o):
            orphans += [(mm.group(1), x.strip("' ")) for x in mm.group(2).split(",") if x.strip()]
        for mm in re.finditer(r"\[FAIL\] floats: (fig|table) 引用了不存在的编号: \[([^\]]*)\]", o):
            dangling += [(mm.group(1), x.strip("' ")) for x in mm.group(2).split(",") if x.strip()]
        true_orphans = [(k, n) for k, n in orphans if not n.startswith("S") and not verify_orphan(raw, k, n)]
        row.update(floats_pass=("[PASS] floats" in o), orphans_reported=len(orphans), orphans_verified=len(true_orphans),
                   orphan_list=" ".join(f"{k}{n}" for k, n in true_orphans), dangling_reported=len(dangling))
        # acronyms
        o = run([sys.executable, GATE, "acronyms"], cwd=wd)
        acr = re.findall(r"\[FAIL\] acronyms: (\S+) 首现第 (\d+) 行，(未展开|展开在第 \d+ 行，晚于首现)", o)
        body = io.open(os.path.join(wd, "paper", "manuscript.md"), encoding="utf-8").read().split("\n## References")[0]
        acr5 = []
        for tok, line, why in acr:
            cnt = len(re.findall(r"(?<![A-Za-z0-9])" + re.escape(tok) + r"(?![A-Za-z0-9])", body))
            if cnt >= 5 and not re.search(r"\d", tok) and len(tok) >= 3:
                acr5.append(f"{tok}×{cnt}{'*' if '晚于' in why else ''}")
        row.update(acr_reported=len(acr), acr_ge5=len(acr5), acr_ge5_list=" ".join(acr5[:12]))
        # scope
        o = run([sys.executable, GATE, "scope"], cwd=wd)
        sc = re.findall(r"\[WARN\] scope: L\d+ \[(\w[\w\- ]*)\] (.*)", o)
        strong = [s for w, s in sc if re.search(r"\b(the first|first to|first (work|method|model|approach|attempt|study|time)|new state[- ]of[- ]the[- ]art|outperforms all|all (existing|prior|previous))\b", s, re.I)]
        row.update(scope_reported=len(sc), scope_strong=len(set(strong)))
        # dpi
        o = run([sys.executable, GATE, "dpi"], cwd=wd)
        low = re.findall(r"= (\d+) dpi < 300", o)
        row.update(dpi_low=len(low), dpi_min=min(map(int, low)) if low else "", dpi_pass=("[PASS] dpi" in o))
        rows.append(row)
        print(f"[{i}/{len(pdfs)}] {venue}/{name[:40]}: p{row.get('pages')} refs={row.get('refs')} floats={'ok' if row['floats_pass'] else 'FAIL'}({row['orphans_verified']}) acr5={row['acr_ge5']} scope*={row['scope_strong']} dpi<300={row['dpi_low']}/{row.get('rasters')}")
        # drop extracted rasters to save disk
        for f in glob.glob(os.path.join(wd, "figures", "*.png")):
            os.remove(f)
    keys = ["venue", "paper", "pages", "converted", "error", "refs", "refs_doi", "refs_arxiv", "rasters", "floats_pass", "orphans_reported", "orphans_verified", "orphan_list", "dangling_reported", "acr_reported", "acr_ge5", "acr_ge5_list", "scope_reported", "scope_strong", "dpi_low", "dpi_min", "dpi_pass"]
    with open(os.path.join(out, "calib.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in keys})
    # by venue
    by = collections.defaultdict(list)
    for r in rows:
        if r["converted"]: by[r["venue"]].append(r)
    lines = ["| venue | n | 转换失败 | 有标识符的参考文献占比 | 孤立图表 (报告→复核) | 篇均 ≥5 次缩略语 | 篇均强作用域句 | <300 dpi 图占比 | 有低 dpi 图的篇占比 |", "|---|---|---|---|---|---|---|---|---|"]
    for v in sorted(by):
        rs = by[v]; n = len(rs)
        fails = sum(1 for r in rows if r["venue"] == v and not r["converted"])
        refs = sum(r.get("refs", 0) for r in rs); ids = sum(r.get("refs_doi", 0) + r.get("refs_arxiv", 0) for r in rs)
        orp_rep = sum(r["orphans_reported"] for r in rs); orp_ver = sum(r["orphans_verified"] for r in rs)
        papers_orp = sum(1 for r in rs if r["orphans_verified"])
        acr = sum(r["acr_ge5"] for r in rs) / n; sc = sum(r["scope_strong"] for r in rs) / n
        rast = sum(r.get("rasters", 0) for r in rs); low = sum(r["dpi_low"] for r in rs); plow = sum(1 for r in rs if r["dpi_low"])
        lines.append(f"| {v} | {n} | {fails} | {ids}/{refs} ({100*ids/max(refs,1):.0f}%) | {orp_rep}→{orp_ver}（{papers_orp} 篇） | {acr:.1f} | {sc:.1f} | {low}/{rast} ({100*low/max(rast,1):.0f}%) | {plow}/{n} |")
    io.open(os.path.join(out, "calib_by_venue.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Calibrate gates on a corpus of published PDFs: corpus_dir/<venue>/*.pdf -> out_dir/calib.csv + calib_by_venue.md")
    ap.add_argument("corpus_dir"); ap.add_argument("out_dir")
    a = ap.parse_args(); main(a.corpus_dir, a.out_dir)
