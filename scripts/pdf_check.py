# -*- coding: utf-8 -*-
"""G6d — the compiled submission PDFs, read from the PDF itself: what a venue rejects on sight and no source-level gate can see.
Ported from the tpami_medimg CVPR 2027 pre-submission check (code/pdf_check_cvpr.py, 2026-11-08), where an edit had pushed 18 lines of
the Limitations onto page 9 and a block-level heading search passed it.

  python pdf_check.py check [--project .] [--pdf <main.pdf>] [--supp <supp.pdf>] [--state research-state.yaml]

latex_check.py check runs the same checks inside G6d on <main>.pdf next to main.tex and on the supplementary PDF (state.target.supp_pdf,
else supp.pdf beside main.pdf). Standalone, --pdf checks any PDF (one exported from Word too). Checks:
  page limit (main PDF only): body <= state.target.page_limit pages, counted up to the first end-matter heading LINE (state.target.page_limit_end,
      '|'-separated, default References|Bibliography|LLM Usage Statement|参考文献; 'none' = every page counts); on page limit+1 the body lines
      before that heading are counted in reading order (left column first; the top / bottom 7 %, the review ruler and lines <= 15 characters
      are skipped): over = FAIL with the first offending line; no heading in a longer PDF = WARN; page_limit null = INFO
  page size: every page = state.target.page_size (letter | a4 | <w>x<h>mm), else the size the \\documentclass options declare
      (letterpaper / a4paper): another size = FAIL; pages of different sizes with nothing declared = WARN
  hidden text (prompt injection, a desk reject at CVPR 2027): invisible text (render mode 3, opacity 0), white text that sits on neither a
      raster image nor a coloured vector fill, text off the page = FAIL (state.target.hidden_text_waiver: "<why>" -> WARN); text under 4 pt = WARN
  fonts: Type 3 = FAIL; not embedded = WARN (the G5 rule for figure PDFs)
  attachments / JavaScript = FAIL
  blind review (state.target.blind true): a state.blind_terms word in the metadata or above the Abstract on page 1 (a final-mode build prints
      the authors) = FAIL; a metadata Author that is not anonymous = WARN; links other than doi.org / arXiv = WARN (they may name the
      authors or expand the content, both desk rejects at CVPR 2027)
  raster images below state.target.min_dpi at their placed size = WARN (G5 owns the FAIL for registered figures)
A PDF older than its .tex sources is not trusted (WARN, nothing else checked). Exit = number of FAIL lines."""
import argparse, io, os, re, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)

FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] pdf: {msg}")

END_MATTER = "References|Bibliography|LLM Usage Statement|参考文献"     # default state.target.page_limit_end
SIZES = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}
OPEN_LINK = re.compile(r"https?://(?:dx\.)?doi\.org/|https?://(?:www\.|export\.)?arxiv\.org/", re.I)
JS = re.compile(r"/S\s*/JavaScript|/JS\s*[(<\[]|/JS\s+\d+\s+\d+\s+R")    # not font subset tags such as /JSOCZY+CMMI9


def read(p): return io.open(p, encoding="utf-8", errors="replace").read()

def sources(tex):
    """tex plus every \\input / \\include / \\subfile it pulls in, recursively (missing ones skipped): the files a PDF built from it must be newer than"""
    out, todo = [], [os.path.abspath(tex)]
    while todo:
        p = todo.pop()
        if p in out or not os.path.isfile(p): continue
        out.append(p); base = os.path.dirname(p)
        for name in re.findall(r"\\(?:input|include|subfile)\s*\{([^}]+)\}", re.sub(r"(?<!\\)%.*", "", read(p))):
            todo += [os.path.abspath(os.path.join(base, name.strip())), os.path.abspath(os.path.join(base, name.strip() + ".tex"))]
    return out

def class_opts(tex):
    m = re.search(r"\\documentclass\s*\[([^\]]*)\]", re.sub(r"(?<!\\)%.*", "", read(tex))) if tex and os.path.isfile(tex) else None
    return m.group(1) if m else ""

def lines_of(page):
    """[(bbox, text)] for every text line of a page (lines, not blocks: PyMuPDF merges a heading into the block of the text around it)"""
    return [(l["bbox"], "".join(s["text"] for s in l["spans"])) for b in page.get_text("dict")["blocks"] if b.get("type") == 0 for l in b["lines"]]

def heading_rx(spec):
    """'References|LLM Usage Statement' -> a regex for one line with its spaces removed and lower-cased, so that IEEE small caps
    ('R EFERENCES') and numbered headings ('7. References', 'VII. REFERENCES') match too."""
    alts = [re.escape(re.sub(r"\s+", "", h).lower()) for h in str(spec).split("|") if h.strip()]
    return re.compile(r"(?:\d+\.?|[ivxl]+\.)?(?:" + "|".join(alts) + r")[.:]?")

def body_end(pdf, spec=END_MATTER):
    """Where the counted body of a compiled PDF ends -> {pages, end_page, heading, before, body_last}.
    end_page: the first page (1-based) holding a LINE that is one of the end-matter headings (None: no such line); before: the body lines that
    precede that heading on end_page in reading order (two columns: the left column first), skipping the top and bottom 7 % of the page
    (running header, page number), the review ruler's numbers and lines of <= 15 characters; body_last: the last page that holds body text."""
    import fitz
    rx = heading_rx(spec)
    with fitz.open(pdf) as doc:
        out = {"pages": doc.page_count, "end_page": None, "heading": "", "before": [], "body_last": doc.page_count}
        for i, p in enumerate(doc):
            lines = lines_of(p)
            heads = [(bb, t) for bb, t in lines if rx.fullmatch(re.sub(r"\s+", "", t).lower())]
            if not heads: continue
            mid, H = p.rect.width / 2, p.rect.height
            right = lambda bb: bb[0] >= mid
            hb, ht = min(heads, key=lambda h: (right(h[0]), h[0][1]))          # the first heading in reading order
            def before(bb): return (not right(bb) and right(hb)) or (right(bb) == right(hb) and bb[3] <= hb[1] + 1)
            body = [t.strip() for bb, t in lines if before(bb) and bb[1] > 0.07 * H and bb[3] < 0.93 * H
                    and len(t.strip()) > 15 and not re.fullmatch(r"[\d\s.,:;()\-–—]*", t.strip())]
            out.update(end_page=i + 1, heading=ht.strip(), before=body, body_last=i + 1 if body else i)
            break
    return out


# ------------------------------------------------------------------ the checks of one PDF
def page_limit(pdf, name, tgt):
    lim = tgt.get("page_limit")
    if not lim: say("INFO", f"state.target.page_limit 未填，没查 {name} 的页数"); return
    try: lim = int(lim)
    except (TypeError, ValueError): say("WARN", f"state.target.page_limit={lim!r} 不是整数页数，没查页数"); return
    spec = str(tgt.get("page_limit_end") or "").strip() or END_MATTER; every = spec.lower() == "none"
    if every:
        import fitz
        with fitz.open(pdf) as d: r = {"pages": d.page_count, "end_page": None, "heading": "", "before": [], "body_last": d.page_count}
    else: r = body_end(pdf, spec)
    if r["body_last"] <= lim:
        say("PASS", f"{name}: 正文止于第 {r['body_last']} 页，≤ page_limit {lim}" + (f"（{r['heading']!r} 从第 {r['end_page']} 页起不计页，共 {r['pages']} 页）" if r["end_page"] else f"（共 {r['pages']} 页）"))
    elif every: say("FAIL", f"{name}: 共 {r['pages']} 页 > page_limit {lim}（page_limit_end: none，每页都计）")
    elif r["end_page"] is None:
        say("WARN", f"{name}: 共 {r['pages']} 页 > page_limit {lim}，但找不到 {spec} 标题，判断不了正文止于哪一页：在 state.target.page_limit_end 写上这份稿子不计页部分的标题（| 分隔），或 none 表示每页都计")
    else:
        ex = f"；第 {r['end_page']} 页上 {r['heading']!r} 之前还有 {len(r['before'])} 行正文，如 {r['before'][0][:60]!r}" if r["before"] else ""
        say("FAIL", f"{name}: 正文超出 page_limit {lim} 页，止于第 {r['body_last']} 页{ex}（超页会被直接拒稿：删字，或挪到补充材料）")

def expected_size(tgt, opts=""):
    """-> ((w, h) in pt, label) from state.target.page_size (letter | a4 | <w>x<h>mm), else from letterpaper / a4paper in the \\documentclass options;
    (None, '') when nothing is declared; (None, '?<value>') for an unreadable page_size"""
    v = str(tgt.get("page_size") or "").strip().lower()
    if v in SIZES: return SIZES[v], v
    m = re.fullmatch(r"([\d.]+)\s*x\s*([\d.]+)\s*mm", v)
    if m: return (float(m.group(1)) / 25.4 * 72, float(m.group(2)) / 25.4 * 72), v
    if v: return None, "?" + v
    o = [x.strip() for x in opts.split(",")]
    for k, opt in (("letter", "letterpaper"), ("a4", "a4paper")):
        if opt in o: return SIZES[k], f"{k}（\\documentclass[{opt}]）"
    return None, ""

def page_size(doc, name, tgt, opts):
    want, label = expected_size(tgt, opts)
    if label.startswith("?"): say("WARN", f"state.target.page_size={label[1:]!r} 看不懂（letter | a4 | <宽>x<高>mm），没查页面尺寸"); return
    sizes = sorted({(round(p.rect.width, 1), round(p.rect.height, 1)) for p in doc})
    if want:
        bad = [i + 1 for i, p in enumerate(doc) if abs(p.rect.width - want[0]) > 2 or abs(p.rect.height - want[1]) > 2]
        if bad: say("FAIL", f"{name}: 第 {bad[:6]} 页不是 {label}（{want[0]:.0f}×{want[1]:.0f} pt；实际 {sizes}）：模板或 geometry 改了纸张，投稿系统按版式拒")
        else: say("PASS", f"{name}: {doc.page_count} 页都是 {label}")
    elif len(sizes) > 1: say("WARN", f"{name}: 页面尺寸不一 {sizes}：有页是从别的 PDF 拼进来的？在 state.target.page_size 写明要求的尺寸")

def _white(n, color):
    if not color: return False
    if n == 1: return color[0] >= 0.98
    if n == 3: return min(color) >= 0.98
    if n == 4: return max(color) <= 0.02
    return False

def hidden_text(doc, name, tgt):
    import fitz
    hidden, tiny = [], []
    for i, p in enumerate(doc):
        r = p.rect; backs = None
        for s in p.get_texttrace():
            txt = "".join(chr(c[0]) for c in s["chars"] if c[0] > 0).strip()
            if not txt: continue
            bb = fitz.Rect(s["bbox"]); where = f"第 {i + 1} 页"
            if s["type"] == 3 or s.get("opacity", 1) == 0: hidden.append(f"{where}不可见 {txt[:50]!r}")
            elif _white(s["colorspace"], s["color"]):
                if backs is None:                                                   # white is visible only on a photo or a coloured fill
                    backs = [rc for im in p.get_images(full=True) for rc in p.get_image_rects(im[0])]
                    backs += [fitz.Rect(d["rect"]) for d in p.get_drawings() if d.get("fill") and not _white(len(d["fill"]), d["fill"])]
                c = fitz.Point((bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2)
                if not any(rc.contains(c) for rc in backs): hidden.append(f"{where}白字无底色 {txt[:50]!r}")
            if bb.x1 < r.x0 or bb.x0 > r.x1 or bb.y1 < r.y0 or bb.y0 > r.y1: hidden.append(f"{where}在页面外 {txt[:50]!r}")
            if 0 < s["size"] < 4: tiny.append(f"{where} {s['size']:.1f} pt {txt[:30]!r}")
    waiver = str(tgt.get("hidden_text_waiver") or "").strip()
    if hidden:
        say("WARN" if waiver else "FAIL", f"{name}: {len(hidden)} 处隐藏文字（不可见 / 白字无底色 / 页面外），如 {hidden[:3]}"
            + (f"；已豁免：{waiver}" if waiver else "：审稿人看不见、工具读得到，CVPR 2027 把它当 prompt injection 直接拒稿；确属正常（无障碍文字层、扫描件 OCR 层）在 state.target.hidden_text_waiver 写明"))
    else: say("PASS", f"{name}: 没有隐藏文字（不可见、白字无底色、页面外）")
    if tiny: say("WARN", f"{name}: {len(tiny)} 段文字小于 4 pt（印出来看不清，也可能是藏起来的指令），如 {tiny[:3]}")

def fonts(doc, name):
    seen = {}
    for p in doc:
        for f in p.get_fonts(full=True): seen[f[3]] = (f[1], f[2])
    t3 = sorted(b for b, (ext, ft) in seen.items() if ft == "Type3")
    noemb = sorted(b for b, (ext, ft) in seen.items() if ext == "n/a" and ft != "Type3")
    if t3: say("FAIL", f"{name}: Type 3 字体 {t3[:4]}：IEEE / Elsevier 制作拒收；多半来自某张 matplotlib 图（pdf.fonttype=42 重出）或缺 cm-super 的位图字体")
    if noemb: say("WARN", f"{name}: 字体没有嵌入 {noemb[:4]}：别人机器上会换成替代字体；IEEE PDF eXpress 拒收")
    if not t3 and not noemb: say("PASS", f"{name}: {len(seen)} 种字体全部嵌入，没有 Type 3")

def active_content(doc, name):
    emb = doc.embfile_count(); js = False
    for x in range(1, doc.xref_length()):
        try:
            if JS.search(doc.xref_object(x) or ""): js = True; break
        except Exception: pass
    if emb or js: say("FAIL", f"{name}: " + "；".join(([f"嵌入了 {emb} 个附件"] if emb else []) + (["含 JavaScript"] if js else [])) + "：投稿 PDF 不许带附件或脚本")
    else: say("PASS", f"{name}: 没有附件、没有 JavaScript")

def blind(doc, name, tgt, st):
    if not tgt.get("blind"): return
    terms = [str(t).strip() for t in (st.get("blind_terms") or []) if str(t).strip()]
    hit = lambda text: [t for t in terms if re.search(r"(?<![^\W_])" + re.escape(t) + r"(?![^\W_])", text, re.I)]
    md = {k: str(v) for k, v in (doc.metadata or {}).items() if v and k in ("title", "author", "subject", "keywords", "creator")}
    bad_md = sorted({(k, t) for k, v in md.items() for t in hit(v)})
    if bad_md: say("FAIL", f"{name}: PDF 元数据含盲审禁词 {bad_md[:4]}：hyperref 设 pdfauthor={{}}、pdfsubject={{}}，重编译")
    elif md.get("author") and not re.search(r"anonym", md["author"], re.I): say("WARN", f"{name}: 盲审稿的元数据 Author = {md['author']!r}：清空（hyperref pdfauthor={{}}）")
    lines = lines_of(doc[0]); H = doc[0].rect.height
    ab = [bb[1] for bb, t in lines if re.fullmatch(r"(?:abstract|摘要)[.:]?", re.sub(r"\s+", "", t).lower())]
    top = " ".join(t for bb, t in lines if bb[3] <= (min(ab) + 1 if ab else 0.3 * H))
    head_hits = hit(top)
    if head_hits: say("FAIL", f"{name}: 第 1 页摘要以上（标题 / 作者栏）出现盲审禁词 {head_hits[:4]}：是不是用 final 而不是 review 模式编译的？")
    if not bad_md and not head_hits and terms: say("PASS", f"{name}: 元数据与第 1 页作者栏没有 blind_terms")
    uris = sorted({(i + 1, l["uri"]) for i, p in enumerate(doc) for l in p.get_links() if l.get("uri")})
    other = [(pg, u) for pg, u in uris if not OPEN_LINK.match(u)]
    if other:
        hosts = sorted({re.sub(r"^(?:https?://|mailto:)([^/?#]+).*$", r"\1", u, flags=re.I) for _, u in other})
        say("WARN", f"{name}: 盲审稿里 {len(other)} 个外链不是 doi.org / arXiv（主机 {hosts[:6]}）：逐个确认不暴露作者、不扩充正文内容（CVPR 2027 两条都是直接拒稿）")

def raster_dpi(doc, name, tgt):
    try: lim = float(tgt.get("min_dpi") or 300)
    except (TypeError, ValueError): lim = 300.0
    low = []
    for i, p in enumerate(doc):
        for im in p.get_images(full=True):
            for rc in p.get_image_rects(im[0]):
                if rc.width <= 1 or rc.height <= 1: continue
                dpi = min(im[2] / (rc.width / 72), im[3] / (rc.height / 72))
                if dpi < lim: low.append(f"第 {i + 1} 页 {im[2]}×{im[3]} px 印 {rc.width / 72 * 25.4:.0f} mm 宽 = {dpi:.0f} dpi")
    if low: say("WARN", f"{name}: {len(low)} 张栅格图按版面尺寸低于 {lim:g} dpi，如 {low[:3]}（G5 只查 figures.csv 登记的图）")

def check_pdf(pdf, srcs, tgt, st, opts="", main=True):
    """all checks of one compiled PDF; srcs: the .tex files it was built from (staleness), main: the paper itself (page limit)"""
    name = os.path.basename(pdf)
    if not os.path.exists(pdf):
        if main and tgt.get("page_limit"): say("WARN", f"没有 {name}：编译后才能按 page_limit {tgt.get('page_limit')} 查页数（以及隐藏文字、字体、页面尺寸）")
        elif main: say("INFO", f"没有 {name}：编译后的 PDF 检查（隐藏文字、字体、页面尺寸……）没跑")
        return
    srcs = [s for s in srcs if os.path.isfile(s)]
    if srcs and os.path.getmtime(pdf) + 1 < max(os.path.getmtime(s) for s in srcs):
        say("WARN", f"{name} 比 .tex 源旧，没有据此检查（页数、隐藏文字、字体……）：重编译一遍再 check"); return
    try:
        import fitz
        doc = fitz.open(pdf)
    except Exception as ex: say("WARN", f"读不了 {name}（{type(ex).__name__}: {ex}），没查"); return
    if doc.page_count == 0: doc.close(); say("WARN", f"读不了 {name}（0 页：PDF 坏了或没编译完），没查"); return
    with doc:
        steps = ([("页数", lambda: page_limit(pdf, name, tgt))] if main else []) + [
            ("页面尺寸", lambda: page_size(doc, name, tgt, opts)), ("隐藏文字", lambda: hidden_text(doc, name, tgt)), ("字体", lambda: fonts(doc, name)),
            ("附件 / JavaScript", lambda: active_content(doc, name)), ("盲审", lambda: blind(doc, name, tgt, st)), ("栅格图分辨率", lambda: raster_dpi(doc, name, tgt))]
        for label, step in steps:
            try: step()
            except Exception as ex: say("WARN", f"{name}: {label}检查没跑完（{type(ex).__name__}: {ex}）")

def run_checks(root, st, tex, files, opts=""):
    """G6d entry from latex_check.py check: <stem>.pdf next to main.tex, then the supplementary PDF (state.target.supp_pdf, else supp.pdf beside
    main.pdf). Returns the number of FAIL lines printed."""
    global FAILS
    FAILS = 0; tgt = st.get("target") or {}
    check_pdf(os.path.splitext(tex)[0] + ".pdf", files, tgt, st, opts, main=True)
    sp = str(tgt.get("supp_pdf") or "").strip()
    supp = os.path.join(root, sp) if sp else os.path.join(os.path.dirname(tex), "supp.pdf")
    if os.path.exists(supp):
        stex = os.path.splitext(supp)[0] + ".tex"
        check_pdf(supp, sources(stex) if os.path.isfile(stex) else [], tgt, st, class_opts(stex) or opts, main=False)
    elif sp: say("WARN", f"state.target.supp_pdf = {sp} 不存在")
    return FAILS


def main():
    ap = argparse.ArgumentParser(description="G6d: checks of the compiled submission PDFs (page limit, page size, hidden text, fonts, attachments / JavaScript, blind metadata / links, raster dpi)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="main.pdf next to main.tex (+ supp.pdf), or the PDFs given")
    c.add_argument("--project", default="."); c.add_argument("--state", default="research-state.yaml")
    c.add_argument("--pdf", help="the paper PDF (default: <target.latex_dir>/main.pdf)"); c.add_argument("--supp", help="a supplementary PDF (no page limit)")
    a = ap.parse_args()
    root = os.path.abspath(a.project); st = {}
    sp = os.path.join(root, a.state)
    if os.path.exists(sp):
        try:
            import yaml; st = yaml.safe_load(read(sp)) or {}
        except Exception as ex: say("WARN", f"state 读取失败 {ex}")
    tgt = st.get("target") or {}
    if a.pdf or a.supp:
        for pdf, is_main in ((a.pdf, True), (a.supp, False)):
            if not pdf: continue
            pdf = os.path.abspath(os.path.join(root, pdf)); tex = os.path.splitext(pdf)[0] + ".tex"
            check_pdf(pdf, sources(tex) if os.path.isfile(tex) else [], tgt, st, class_opts(tex), main=is_main)
    else:
        tex = os.path.join(root, tgt.get("latex_dir") or "paper/latex", "main.tex")
        if not os.path.isfile(tex): say("FAIL", f"{os.path.relpath(tex, root)} 不存在：给 --pdf"); sys.exit(1)
        run_checks(root, st, tex, sources(tex), class_opts(tex))
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(FAILS)


if __name__ == "__main__":
    main()
