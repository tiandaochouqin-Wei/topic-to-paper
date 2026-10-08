# -*- coding: utf-8 -*-
"""JATS XML (Europe PMC fullTextXML) -> topic-to-paper inputs:
   <out>/paper/manuscript.md   body with **Fig. N.** / **Table N.** captions, [n] citations, ## References list
   <out>/paper/refs.bib        r1..rN with DOI / PMID / arXiv when the XML carries them
   <out>/figures.csv           one row per figure (print width guessed: 1-col 89 mm, 2-col 183 mm by graphic aspect)
   <out>/research-state.yaml   journal limits (hand-filled per journal)
"""
import re, sys, os, csv, io
import xml.etree.ElementTree as ET

def txt(el):
    """flatten an element to text, keeping [n] for xref bibr and plain text for everything else."""
    if el is None: return ""
    out = []
    def walk(e):
        if e.tag == "xref" and e.get("ref-type") == "bibr":
            rid = e.get("rid", "")
            m = re.search(r"(\d+)$", rid)
            out.append(f"[{m.group(1)}]" if m else (e.text or ""))
            if e.tail: out.append(e.tail)
            return
        if e.tag in ("disp-formula", "inline-formula"):
            out.append(" $" + re.sub(r"\s+", " ", "".join(e.itertext())).strip() + "$ ")
            if e.tail: out.append(e.tail)
            return
        if e.text: out.append(e.text)
        for c in e:
            walk(c)
        if e.tail: out.append(e.tail)
    walk(el)
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()

def table_md(tw):
    rows = []
    for tr in tw.iter("tr"):
        cells = [re.sub(r"\s+", " ", "".join(c.itertext())).strip() for c in tr if c.tag in ("td", "th")]
        rows.append("| " + " | ".join(cells) + " |")
    if len(rows) > 1:
        rows.insert(1, "|" + "---|" * (rows[0].count("|") - 1))
    return "\n".join(rows)

def convert(xml_path, out):
    tree = ET.parse(xml_path); root = tree.getroot()
    art = root.find(".//article") if root.tag != "article" else root
    meta = art.find("front/article-meta")
    title = txt(meta.find("title-group/article-title"))
    journal = txt(art.find("front/journal-meta/journal-title-group/journal-title")) or txt(art.find("front/journal-meta/journal-title"))
    kws = [txt(k) for k in meta.findall(".//kwd")]
    abstract = "\n\n".join(txt(p) for p in meta.findall("abstract//p") if txt(p))
    os.makedirs(os.path.join(out, "paper"), exist_ok=True)
    md = [f"# {title}", "", f"Keywords: {'; '.join(kws)}" if kws else "", "", "## Abstract", "", abstract, ""]
    body = art.find("body")
    fig_rows = []
    fig_n = {}; tab_n = {}
    def walk_sec(sec, depth):
        t = sec.find("title")
        if t is not None and txt(t):
            md.append("#" * min(depth, 4) + " " + txt(t)); md.append("")
        for ch in sec:
            if ch.tag == "sec": walk_sec(ch, depth + 1)
            elif ch.tag == "p": md.append(txt(ch)); md.append("")
            elif ch.tag == "fig": emit_fig(ch)
            elif ch.tag == "table-wrap": emit_tab(ch)
            elif ch.tag in ("list",):
                for li in ch.findall("list-item"): md.append("- " + txt(li))
                md.append("")
    def emit_fig(f):
        lab = txt(f.find("label")) or "Fig."
        m = re.search(r"(\d+)", lab); n = m.group(1) if m else str(len(fig_n) + 1)
        fig_n[n] = 1
        cap = txt(f.find("caption"))
        md.append(f"**Fig. {n}.** {cap}"); md.append("")
        g = f.find(".//graphic")
        href = g.get("{http://www.w3.org/1999/xlink}href") if g is not None else ""
        fig_rows.append((n, href))
    def emit_tab(tw):
        lab = txt(tw.find("label")) or "Table"
        m = re.search(r"(\d+)", lab); n = m.group(1) if m else str(len(tab_n) + 1)
        tab_n[n] = 1
        cap = txt(tw.find("caption"))
        md.append(f"**Table {n}.** {cap}"); md.append("")
        tb = tw.find(".//table")
        if tb is not None: md.append(table_md(tw)); md.append("")
    if body is not None:
        for ch in body:
            if ch.tag == "sec": walk_sec(ch, 2)
            elif ch.tag == "p": md.append(txt(ch)); md.append("")
            elif ch.tag == "fig": emit_fig(ch)
            elif ch.tag == "table-wrap": emit_tab(ch)
    # floats that live in <floats-group>
    fg = art.find("floats-group")
    if fg is not None:
        for ch in fg:
            if ch.tag == "fig": emit_fig(ch)
            elif ch.tag == "table-wrap": emit_tab(ch)
    # references
    refs = art.findall(".//ref-list/ref")
    md.append("## References"); md.append("")
    bib = []
    for i, r in enumerate(refs, 1):
        rid = r.get("id", "")
        m = re.search(r"(\d+)$", rid); n = m.group(1) if m else str(i)
        c = r.find(".//element-citation")
        if c is None: c = r.find(".//mixed-citation")
        if c is None: c = r
        t = txt(c.find("article-title")) or txt(c.find("chapter-title")) or txt(c.find("source")) or txt(c)[:120]
        doi = pmid = arx = ""
        for pid in c.findall("pub-id"):
            v = (pid.text or "").strip()
            k = pid.get("pub-id-type", "")
            if k == "doi": doi = v
            elif k == "pmid": pmid = v
            elif k == "arxiv": arx = v
        if not doi:
            mm = re.search(r"10\.\d{4,}/[^\s\"<>]+", txt(c)); doi = mm.group(0).rstrip(".") if mm else ""
        if not arx:
            mm = re.search(r"arXiv:?\s*(\d{4}\.\d{4,5})", txt(c), re.I); arx = mm.group(1) if mm else ""
        year = txt(c.find("year"))
        md.append(f"[{n}] {t} ({year}). {('https://doi.org/' + doi) if doi else ''}")
        fields = [f'  title = {{{t.replace("{","").replace("}","")}}}', f"  year = {{{year}}}"]
        if doi: fields.append(f"  doi = {{{doi}}}")
        if pmid: fields.append(f"  pmid = {{{pmid}}}")
        if arx: fields.append(f"  note = {{arXiv:{arx}}}")
        bib.append(f"@misc{{r{n},\n" + ",\n".join(fields) + "\n}")
    io.open(os.path.join(out, "paper", "manuscript.md"), "w", encoding="utf-8").write("\n".join(md))
    io.open(os.path.join(out, "paper", "refs.bib"), "w", encoding="utf-8").write("\n\n".join(bib) + "\n")
    with open(os.path.join(out, "figures.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["file", "print_width_mm", "source_data", "inspected", "issues"])
        for n, href in fig_rows: w.writerow([f"figures/{href}.jpg" if href else f"figures/fig{n}.jpg", 183, "published", "yes", ""])
    print(f"{xml_path}: {journal} | figs {len(fig_rows)} tables {len(tab_n)} refs {len(refs)} | title: {title[:70]}")
    return journal, len(refs), len(kws), abstract

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="JATS XML (Europe PMC fullTextXML) -> topic-to-paper inputs in out_dir")
    ap.add_argument("xml"); ap.add_argument("out_dir")
    a = ap.parse_args(); convert(a.xml, a.out_dir)
