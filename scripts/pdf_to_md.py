# -*- coding: utf-8 -*-
"""Published PDF (CVF / IEEE / NeurIPS two-column) -> topic-to-paper inputs.
   paper/manuscript.md : title, Abstract, body with **Figure N.**/**Table N.** captions, ## References with [n] lines
   paper/refs.bib      : r1..rN; DOI / arXiv pulled from each reference string (CVF/NeurIPS refs rarely carry DOIs)
   figures.csv         : one row per embedded raster image with its printed width in mm (from the PDF's own image bbox)
Numbered [n] citations are kept as-is; author-year citations are left as text.
"""
import sys, os, re, io, csv
import fitz

def extract(pdf, out):
    doc = fitz.open(pdf)
    os.makedirs(os.path.join(out, "paper"), exist_ok=True)
    os.makedirs(os.path.join(out, "figures"), exist_ok=True)
    # ---- text, two-column aware: sort blocks by column then y
    pages = []
    CAPRE = re.compile(r"^\s*(Figure|Fig\.|Table|TABLE)\s*(\d+)\s*[.:]", re.I)
    for p in doc:
        W, H = p.rect.width, p.rect.height
        blocks = [b for b in p.get_text("blocks") if b[6] == 0]
        # running headers / footers / page numbers: short blocks hugging the top or bottom edge
        HEAD = re.compile(r"^(IEEE TRANSACTIONS|Proceedings|Published as|Under review|Preprint|Page \d+ of \d+|\d{1,5}\s*$)", re.I)
        blocks = [b for b in blocks if not ((b[1] < 95 and b[3] - b[1] < 26 and (b[1] < 60 or HEAD.match(b[4].strip()))) or (b[3] > H - 36 and b[3] - b[1] < 20) or HEAD.match(b[4].strip()) and b[3] - b[1] < 14)]
        def col(b): return 0 if (b[0] + b[2]) / 2 < W / 2 else 1
        two_col = sum(1 for b in blocks if b[2] - b[0] < W * 0.55) > len(blocks) * 0.6
        if two_col:
            blocks.sort(key=lambda b: (0 if b[2] - b[0] > W * 0.6 and b[1] < 120 else 1, col(b), b[1]))
        else:
            blocks.sort(key=lambda b: b[1])
        texts = []
        prev_tail = "."; prev_text = ""
        MIDCAP = re.compile(r"(?<=[.!?]\s)(Figure|Fig\.|Table|TABLE)\s*(\d+)\s*:", re.I)   # NeurIPS-style "Table 7:" glued to the previous sentence
        for b in blocks:
            t = b[4]
            m = CAPRE.match(t)
            # a caption starts a block AND (the previous block ended a sentence, or the label uses ':', or the previous block ended in a URL,
            # or the block carries a full caption body after the label). "illustrated in\nFig. 3." never starts a block; a bare "Fig. 3.\n" block is a wrapped citation.
            after = t[m.end():].strip() if m else ""
            if m and (prev_tail in ".!?:)" or m.group(0).rstrip().endswith(":") or re.search(r"(https?://\S+|\.(com|org|io|vision)/?\S*)\s*$", prev_text)
                      or (len(after) >= 20 and not re.match(r"(shows|illustrates|presents|depicts|summari[sz]es|reports|compares|lists|gives|provides)\b", after))):
                kind = "Table" if m.group(1).lower().startswith("t") else "Fig."
                t = f"\n**{kind} {m.group(2)}.** " + t[m.end():].lstrip()
            t = MIDCAP.sub(lambda mm: f"\n**{'Table' if mm.group(1).lower().startswith('t') else 'Fig.'} {mm.group(2)}.** ", t)
            texts.append(t)
            stripped = t.rstrip()
            prev_tail = stripped[-1] if stripped else prev_tail
            prev_text = stripped[-80:]
        pages.append("\n".join(texts))
    raw = "\n".join(pages)
    raw = re.sub(r"-\n(?=[a-z])", "", raw)               # de-hyphenate
    raw = re.sub(r"(?<![.\n])\n(?=[a-z,;(])", " ", raw)  # join wrapped lines
    # ---- figures: printed width from image bbox
    fig_rows = []
    k = 0
    for pno, p in enumerate(doc):
        for img in p.get_images(full=True):
            xref = img[0]
            try:
                bbox = p.get_image_bbox(img)
            except Exception:
                continue
            if bbox.width < 60: continue
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4 or pix.colorspace is None or pix.colorspace.n not in (1, 3):
                    pix = fitz.Pixmap(fitz.csRGB, pix)       # CMYK / Lab / Indexed -> RGB; png writer only takes gray or rgb
                if pix.alpha:
                    pix = fitz.Pixmap(pix, 0)
            except Exception:
                continue
            k += 1
            fn = f"figures/img{k}_p{pno+1}.png"
            try:
                pix.save(os.path.join(out, fn))
            except Exception:
                continue
            fig_rows.append((fn, round(bbox.width / 72 * 25.4, 1), pix.width))
    # ---- split references
    m = re.search(r"\n\s*(References|REFERENCES)\s*\n", raw)
    body, refs = (raw[:m.start()], raw[m.end():]) if m else (raw, "")
    # NeurIPS/ICML put appendices AFTER the reference list: give them back to the body
    starts = [mm.start() for mm in re.finditer(r"\n\[\d+\]\s", "\n" + refs)]
    if starts:
        tail_from = starts[-1] + 40
        am = re.search(r"\n(?=(?:Appendix\b|NeurIPS Paper Checklist|Supplementary\b|[A-Z](?:\.\d+)*\s+[A-Z][a-z][^\n]{2,70}\n))", refs[tail_from:])
        if am:
            cut = tail_from + am.start()
            body = body + "\n\n## Appendix\n\n" + refs[cut:]
            refs = refs[:cut]
    # ---- captions were marked at block level; drop the heading-less duplicates the old line regex would have made
    # ---- abstract heading
    body = re.sub(r"\n\s*Abstract\s*\n", "\n\n## Abstract\n\n", body, count=1)
    # ---- reference entries: "[n] ..." one per entry
    # numbered "[n] ..." (CVF/IEEE/NeurIPS), "n. ..." (Springer/Nature), or author-year blocks (ICML/IJCV/APA): one entry each
    refs_s = refs.strip()
    if re.search(r"^\[\d+\]\s", refs_s, re.M):
        entries = re.split(r"\n(?=\[\d+\]\s)", "\n" + refs_s)
    elif re.search(r"^\d{1,3}\.?\s*[\t\xa0 ]+\S", refs_s, re.M):
        entries = [re.sub(r"^(\d{1,3})\.?\s*[\t\xa0 ]+", r"[\1] ", e) for e in re.split(r"\n(?=\d{1,3}\.?\s*[\t\xa0 ]+[A-Z])", "\n" + refs_s)]
    else:
        # author-year: a new entry starts with "Surname, I." at line start; number them in order
        chunks = re.split(r"\n(?=[A-Z][A-Za-z'’\-]+,\s+[A-Z]\.)", "\n" + refs_s)
        entries = [f"[{i}] {c.strip()}" for i, c in enumerate([c for c in chunks if c.strip()], 1)]
    bib, md_refs = [], []
    for e in entries:
        e = re.sub(r"\s+", " ", e).strip()
        mm = re.match(r"\[(\d+)\]\s*(.*)", e)
        if not mm: continue
        n, txt = mm.group(1), mm.group(2)
        doi = re.search(r"10\.\d{4,}/[^\s,;\"]+", txt)
        arx = re.search(r"(?:arXiv|abs/|arxiv\.org/)[^\d]{0,12}(\d{4}\.\d{4,5})", txt, re.I)
        # title = first sentence-segment that does not look like an author list (author lists are ≥75 % capitalised tokens)
        parts = [s.strip() for s in re.split(r"(?<=[a-z\)\]])\.\s+(?=[A-Za-z“\"])", txt) if s.strip()]
        def authorish(seg):
            w = [x for x in re.findall(r"[A-Za-z][\w\-’']*", seg) if len(x) > 1 and x.lower() not in ("and", "et", "al", "others")]
            return len(w) < 3 or sum(x[0].isupper() for x in w) / len(w) >= 0.75
        cands = [s for s in parts if not authorish(s)]
        title = cands[0] if cands else (parts[1] if len(parts) > 2 else (parts[0] if parts else txt))
        title = title.strip("“”\" ")
        md_refs.append(f"[{n}] {txt}")
        f = [f"  title = {{{title.replace('{','').replace('}','')}}}"]
        y = re.search(r"\b(19|20)\d\d\b", txt); f.append(f"  year = {{{y.group(0) if y else ''}}}")
        if doi: f.append(f"  doi = {{{doi.group(0).rstrip('.')}}}")
        if arx: f.append(f"  note = {{arXiv:{arx.group(1)}}}")
        bib.append(f"@misc{{r{n},\n" + ",\n".join(f) + "\n}")
    title_line = doc.metadata.get("title") or pages[0].strip().splitlines()[0]
    md = f"# {title_line}\n\n{body}\n\n## References\n\n" + "\n".join(md_refs) + "\n"
    md = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f�]", "", md)                       # fitz emits \x01 inside math
    md = re.sub(r"[ \t]*\*\*(Fig\.|Table) (\d+)\.\*\*", r"\n\n**\1 \2.**", md)       # every caption marker on its own line
    io.open(os.path.join(out, "paper", "manuscript.md"), "w", encoding="utf-8").write(md)
    io.open(os.path.join(out, "paper", "refs.bib"), "w", encoding="utf-8").write("\n\n".join(bib) + "\n")
    with open(os.path.join(out, "figures.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["file", "print_width_mm", "source_data", "inspected", "issues"])
        for fn, wmm, px in fig_rows: w.writerow([fn, wmm, "published", "yes", ""])
    print(f"{os.path.basename(pdf)}: pages {len(doc)}, refs {len(bib)} (doi {sum('doi' in b for b in bib)}, arxiv {sum('arXiv' in b for b in bib)}), raster figs {len(fig_rows)}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Published PDF -> topic-to-paper inputs (paper/manuscript.md, paper/refs.bib, figures.csv) in out_dir")
    ap.add_argument("pdf"); ap.add_argument("out_dir")
    a = ap.parse_args(); extract(a.pdf, a.out_dir)
