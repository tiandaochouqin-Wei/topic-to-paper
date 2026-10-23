# -*- coding: utf-8 -*-
"""
gate_check.py — topic-to-paper 的机械关口。

用法:
  python gate_check.py all --project .
  python gate_check.py refs|floats|acronyms|scope|numbers|dpi|submission|limits|markers --project .
  (limits also runs markers: TODO/FIXME/XXX/[待补充]/[TBD]/??/\\todo and reference lines that are only a bib key; submission runs it on title_page/cover_letter/highlights/blind)

约定（可用参数覆盖）:
  --manuscript paper/manuscript.md
  --bib        paper/refs.bib
  --results    results/            (csv/json 全部纳入数字集合)
  --figures    figures.csv         (file,print_width_mm,...)
  --state      research-state.yaml (读 target 硬规则)
  --submission submission/         (title_page.md cover_letter.md highlights.md blind.md)

输出 gate_report.md；任一 FAIL 返回 1。只用标准库；dpi 需 Pillow，refs 需联网。
"""
import argparse, sys, csv, json, os, re, sys, time, urllib.request, urllib.parse, urllib.error, difflib
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

REPORT = []
FAILS = 0

def say(status, gate, msg):
    global FAILS
    if status == "FAIL":
        FAILS += 1
    line = f"[{status}] {gate}: {msg}"
    REPORT.append(line)
    print(line)

def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()

# ----------------------------------------------------------------- helpers
REF_HEAD = re.compile(r"^(#+\s*(References|Bibliography|参考文献)|\[1\]\s)", re.M | re.I)

def body_only(text):
    """截掉参考文献表。"""
    m = REF_HEAD.search(text)
    return text[: m.start()] if m else text

def strip_code_math(text):
    # 状态块 / 内部批注（以 > 开头的行）与 HTML 标签不属于正文
    text = "\n".join("" if l.lstrip().startswith(">") else l for l in text.splitlines())
    text = re.sub(r"<[^>\n]{1,200}>", " ", text)
    text = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"\$\$.*?\$\$", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"\$[^$\n]+\$", " ", text)
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return text

# ----------------------------------------------------------------- refs
def parse_bib(bibtext):
    """逐条切分；字段值支持嵌套花括号 {AI}，最后一个字段可无尾逗号。"""
    entries = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@|\Z)", bibtext, re.S):
        key, body = m.group(2).strip(), m.group(3)
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*", body):
            name, i = fm.group(1).lower(), fm.end()
            if i < len(body) and body[i] == "{":
                depth, j = 0, i
                while j < len(body):
                    depth += body[j] == "{"; depth -= body[j] == "}"
                    j += 1
                    if depth == 0: break
                val = body[i + 1:j - 1]
            elif i < len(body) and body[i] == '"':
                j = body.find('"', i + 1); val = body[i + 1:j]
            else:
                vm = re.match(r"[^,\n}]+", body[i:]); val = vm.group(0) if vm else ""
            fields.setdefault(name, re.sub(r"\s+", " ", val.replace("{", "").replace("}", "")).strip())
        blob = " ".join(fields.get(k, "") for k in ("note", "url", "howpublished", "journal", "eprint", "arxivid"))
        am = re.search(r"(?:arXiv:|arxiv\.org/(?:abs|pdf)/)\s*(\d{4}\.\d{4,5})", blob, re.I) \
            or re.fullmatch(r"\s*(\d{4}\.\d{4,5})(?:v\d+)?\s*", fields.get("eprint", "") or fields.get("arxivid", ""))
        dm = re.search(r"(10\.\d{4,}/[^\s,}\"]+)", fields.get("doi", "") or fields.get("url", ""))
        vm = VENUE_HOSTS.search(fields.get("url", ""))
        entries.append({"key": key, "title": fields.get("title", ""), "doi": dm.group(1) if dm else "",
                        "pmid": fields.get("pmid", ""), "arxiv": am.group(1) if am else "",
                        "venue_url": fields.get("url", "").strip() if vm else ""})
    return entries

UA_MAIL = os.environ.get("T2P_CONTACT_EMAIL", "gate@example.org")
# official proceedings hosts: an entry with no DOI / PMID / arXiv may cite one of these URLs as its identifier
VENUE_HOSTS = re.compile(r"https?://(?:www\.)?(?:proceedings\.neurips\.cc|papers\.nips\.cc|proceedings\.mlr\.press|"
                         r"openreview\.net/(?:forum|pdf)|aclanthology\.org|ojs\.aaai\.org|(?:www\.)?ijcai\.org/proceedings|"
                         r"openaccess\.thecvf\.com|jmlr\.org/papers|www\.jmlr\.org/papers|ecva\.net/papers)", re.I)

def _get_text(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": f"gate_check/1.1 (mailto:{UA_MAIL})"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", ""); body = r.read(400000)
    return ctype, body

def _html_title(body):
    t = body.decode("utf-8", "replace")
    m = re.search(r'<meta\s+name="citation_title"\s+content="([^"]*)"', t, re.I) or re.search(r"<title>([^<]*)</title>", t, re.I | re.S)
    import html as _h
    return _h.unescape(m.group(1)).strip() if m else ""

def arxiv_title(aid):
    """title from the arXiv abs page (the export API rate-limits hard); strips the '[id] ' prefix of <title>."""
    _, body = _get_text("https://arxiv.org/abs/" + aid)
    return re.sub(r"^\[[^\]]+\]\s*", "", _html_title(body))

def venue_title(url):
    """-> (reachable, title or '' when the target is a PDF / has no title)"""
    ctype, body = _get_text(url)
    if "pdf" in ctype.lower() or body[:5] == b"%PDF-": return True, ""
    return True, _html_title(body)

def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": f"gate_check/1.1 (mailto:{UA_MAIL})"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def strip_markup(s):
    """Registered titles carry publisher markup: D<sup>2</sup>FT-Net, <i>in vivo</i>, &amp;. Left in place those tags
    become spurious tokens in norm() and drag the similarity ratio below the threshold (false FAIL on a correct DOI)."""
    s = re.sub(r"(?is)</?(mml:|xmlns:)?\w+(\s+[^<>]*)?/?>", " ", s)
    s = re.sub(r"&[a-zA-Z]{2,8};|&#x?[0-9A-Fa-f]{2,5};", " ", s)
    return s

def crossref_title(doi):
    """Registered title for a DOI: CrossRef first, DataCite for DOIs CrossRef does not hold (KITopen, Zenodo, Figshare, …)."""
    try:
        d = _get_json("https://api.crossref.org/works/" + urllib.parse.quote(doi))
        t = d["message"].get("title") or [""]
        if t and t[0].strip():
            return t[0]
    except urllib.error.HTTPError as ex:
        if ex.code != 404:
            raise
    d = _get_json("https://api.datacite.org/dois/" + urllib.parse.quote(doi))
    titles = ((d.get("data") or {}).get("attributes") or {}).get("titles") or [{}]
    return titles[0].get("title", "")

def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", strip_markup(s).lower())).strip()

def gate_refs(a):
    if not os.path.exists(a.bib):
        say("FAIL", "refs", f"{a.bib} 不存在"); return
    entries = parse_bib(read(a.bib))
    if not entries:
        say("FAIL", "refs", "bib 解析到 0 条"); return
    keys = [e["key"] for e in entries]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        say("FAIL", "refs", f"重复 key: {sorted(dup)}")
    ids = {}
    for e in entries:
        ident = e["doi"] or e["pmid"] or e["arxiv"] or e.get("venue_url", "")
        if not ident:
            say("FAIL", "refs", f"{e['key']} 无 DOI/PMID/arXiv，也无官方会议论文集 URL（proceedings.neurips.cc / PMLR / ACL Anthology / CVF / OpenReview 等）"); continue
        if ident in ids and ids[ident] != e["key"]:
            say("FAIL", "refs", f"同一标识符两条记录: {ids[ident]} / {e['key']} -> {ident}")
        ids[ident] = e["key"]
    bad = 0
    for e in entries:
        if not e["doi"]:
            continue
        try:
            t = crossref_title(e["doi"]); time.sleep(0.15)
        except Exception as ex:
            say("WARN", "refs", f"{e['key']} DOI 解析失败: {ex}"); continue
        ratio = difflib.SequenceMatcher(None, norm(t), norm(e["title"])).ratio()
        if ratio < 0.85:
            bad += 1
            say("FAIL", "refs", f"{e['key']} 标题不匹配 ({ratio:.2f})\n      bib: {e['title'][:90]}\n      doi: {t[:90]}")
    # arXiv ids: a wrong id is as bad as a wrong DOI (round 20c: 1811.04001 stood in for a NeurIPS paper)
    for e in entries:
        if e["doi"] or not e["arxiv"]:
            continue
        try:
            t = arxiv_title(e["arxiv"]); time.sleep(1.0)
        except Exception as ex:
            say("WARN", "refs", f"{e['key']} arXiv {e['arxiv']} 无法核验（{ex}）——稍后重跑"); continue
        if not t:
            say("WARN", "refs", f"{e['key']} arXiv {e['arxiv']} 页面无标题"); continue
        ratio = difflib.SequenceMatcher(None, norm(t), norm(e["title"])).ratio()
        if ratio < 0.85:
            bad += 1
            say("FAIL", "refs", f"{e['key']} arXiv 标题不匹配 ({ratio:.2f})\n      bib:   {e['title'][:90]}\n      arXiv: {t[:90]}")
    # proceedings URL as identifier: must resolve; title-match when the page is HTML
    for e in entries:
        if e["doi"] or e["pmid"] or e["arxiv"] or not e.get("venue_url"):
            continue
        try:
            ok, t = venue_title(e["venue_url"]); time.sleep(0.3)
        except Exception as ex:
            say("WARN", "refs", f"{e['key']} 论文集 URL 无法访问（{ex}）"); continue
        if t:
            ratio = difflib.SequenceMatcher(None, norm(t), norm(e["title"])).ratio()
            if ratio < 0.85 and norm(e["title"]) not in norm(t):
                bad += 1
                say("FAIL", "refs", f"{e['key']} 论文集页面标题不匹配 ({ratio:.2f})\n      bib:  {e['title'][:90]}\n      page: {t[:90]}")
    say("PASS" if bad == 0 else "FAIL", "refs", f"{len(entries)} 条，{bad} 条标识符标题不符（DOI / arXiv / 论文集 URL）")

# ----------------------------------------------------------------- floats
CAP = re.compile(r"^\**\s*(Fig\.|Figure|Table)\s*(S?\d+)[a-z]?[\.\:\*]", re.M | re.I)
CITE = re.compile(r"\b(Figs?\.|Figures?|Tabs?\.|Tables?)\s*((?:S?\d+[a-z]?)(?:\s*(?:,|and|&|–|-|to)\s*S?\d+[a-z]?)*)", re.I)

def _lab(pre, num):
    return f"{pre.upper()}{int(num)}"

def expand(span):
    """'4–7' -> {4,5,6,7}; 'S1 to S3' -> {S1,S2,S3}; letter suffixes (9a) fold into the parent (9)."""
    labs = set()
    for part in re.split(r",|and|&", span):
        part = part.strip()
        rng = re.match(r"(S?)(\d+)[a-z]?\s*(?:–|-|to)\s*(S?)(\d+)[a-z]?", part, re.I)
        if rng:
            pre = rng.group(1) or rng.group(3)
            for n in range(int(rng.group(2)), int(rng.group(4)) + 1):
                labs.add(_lab(pre, n))
        else:
            m = re.match(r"(S?)(\d+)", part, re.I)
            if m: labs.add(_lab(m.group(1), m.group(2)))
    return labs

def _sortkey(l):
    return (l.startswith("S"), int(re.sub(r"\D", "", l)))

def gate_floats(a):
    text = body_only(strip_code_math(read(a.manuscript)))
    supp = ""
    for sp in (a.supplement or []):
        if os.path.exists(sp):
            supp += "\n" + body_only(strip_code_math(read(sp)))
    exist = {"fig": set(), "table": set()}
    cap_spans = []          # (start, end) of the caption LABEL only; the rest of the caption line may legitimately cite other floats
    for src in (text, supp):
        for m in CAP.finditer(src):
            rest = src[m.end():src.find("\n", m.end()) if src.find("\n", m.end()) > 0 else len(src)].strip()
            if len(rest) < 12 and not src[m.end():m.end() + 3].startswith("**"):
                continue   # "Fig. 3." alone on a line is a wrapped citation from a PDF text layer, not a caption
            kind = "table" if m.group(1).lower().startswith("t") else "fig"
            exist[kind].add(_lab(m.group(2)[0] if m.group(2)[0] in "Ss" else "", re.sub(r"\D", "", m.group(2))))
            if src is text:
                cap_spans.append((m.start(), m.end()))
    def in_caption_label(pos):
        return any(s <= pos < e for s, e in cap_spans)
    cited = {"fig": set(), "table": set()}
    supp_cited = {"fig": set(), "table": set()}      # "Tab. 7 of the supplementary": lives in another document
    for m in CITE.finditer(text):
        if in_caption_label(m.start()):
            continue  # 题注自身的标签不算引用；题注正文里引用别的图表算
        kind = "table" if m.group(1).lower().startswith("t") else "fig"
        word = m.group(1).lower()
        ctx = (text[max(0, m.start() - 40):m.start()] + " " + text[m.end():m.end() + 45]).lower()
        target = supp_cited if re.search(r"supplement|appendix|supp\.", ctx) else cited
        if word in ("fig.", "figure", "table", "tab."):      # 单数形式只取第一个编号："Table 3, 27 %" 不是列表
            first = re.match(r"(S?)(\d+)", m.group(2).strip(), re.I)
            if first: target[kind].add(_lab(first.group(1), first.group(2)))
        else:
            target[kind].update(expand(m.group(2)))
    ok = True
    for kind in ("fig", "table"):
        cited[kind] |= supp_cited[kind] & exist[kind]        # cited "in the appendix" and the caption is here: fine
        orphan = exist[kind] - cited[kind]
        dangling = cited[kind] - exist[kind]
        dang_supp = {l for l in dangling if l.startswith("S")} | (supp_cited[kind] - exist[kind])
        dangling -= dang_supp
        if orphan:
            ok = False; say("FAIL", "floats", f"{kind} 无人引用: {sorted(orphan, key=_sortkey)}")
        if dangling:
            ok = False; say("FAIL", "floats", f"{kind} 引用了不存在的编号: {sorted(dangling, key=_sortkey)}")
        if dang_supp:
            say("WARN", "floats", f"{kind} 引用了补充材料编号 {sorted(dang_supp, key=_sortkey)}，正文/--supplement 里没有题注（补充材料另有文件时可忽略）")
    if ok:
        say("PASS", "floats", f"figs {sorted(exist['fig'], key=_sortkey)} tables {sorted(exist['table'], key=_sortkey)} 全部被引用且存在")

# ----------------------------------------------------------------- acronyms
ACR = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]{1,9})(?![A-Za-z0-9])")
VENUES = {"IEEE", "ACM", "AAAI", "CVPR", "ICCV", "ECCV", "NIPS", "ICML", "ICLR", "TPAMI", "TMI", "MICCAI",
          "TRO", "RSS", "IROS", "ICRA", "PNAS", "NEJM", "JAMA", "BMJ", "ISBN", "ISSN", "DOI", "URL", "HTTP", "HTTPS",
          "USA", "UK", "EU", "PDF", "CSV", "JSON", "GPU", "CPU", "RAM", "GB", "MB", "KB", "TB", "FIG", "TABLE", "II", "III", "IV", "VI", "VII",
          "NA", "N/A", "TBD", "OK"}

def load_state(a):
    try:
        import yaml
        return yaml.safe_load(read(a.state)) or {}
    except Exception:
        return {}

def gate_acronyms(a):
    text = body_only(strip_code_math(read(a.manuscript)))
    st = load_state(a)
    ok_set = set(VENUES) | set(st.get("acronym_ok", []) or [])
    # 领域规范表（references/acronym-norms.csv，275 篇校准）：同领域 ≥70% 的已发表论文从不展开的词，视为"DNA 级"通用缩略语
    field = (st.get("target", {}) or {}).get("field", "")
    norms = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "acronym-norms.csv")
    if field and os.path.exists(norms):
        for r in csv.DictReader(open(norms, encoding="utf-8")):
            if r["field"] == field: ok_set.add(r["token"])
    first = {}
    text = re.sub(r"https?://\S+|www\.\S+|github\.com/\S+", " ", text)   # URLs carry uppercase path tokens that are not acronyms
    for m in ACR.finditer(text):
        s = m.group(1)
        if re.search(r"\d", s) and not re.search(r"[A-Z]{2}", s):
            continue
        if s in ok_set or len(s) < 2:
            continue
        first.setdefault(s, m.start())
    bad = []
    for s, pos in sorted(first.items(), key=lambda x: x[1]):
        # 展开形式 A: "Long Name (ACR)"  形式 B: "ACR (Long Name)"
        letters = "".join(c for c in s if c.isalpha())
        patA = r"((?:[A-Za-z][\w\-]*\s+){0,%d}[A-Za-z][\w\-]*)\s*\(\s*%s\s*\)" % (len(letters) + 3, re.escape(s))
        patB = r"\b%s\s*\(([^)]{3,80})\)" % re.escape(s)
        pos_def = None
        for pat in (patA, patB):
            md = re.search(pat, text)
            if md:
                pos_def = md.start()
                break
        if pos_def is None or pos_def > pos + 2:  # 展开必须在首现处或之前（同一处允许）
            line = text.count("\n", 0, pos) + 1
            bad.append((s, line, "未展开" if pos_def is None else f"展开在第 {text.count(chr(10), 0, pos_def)+1} 行，晚于首现"))
    for s, line, why in bad:
        say("FAIL", "acronyms", f"{s} 首现第 {line} 行，{why}")
    # 摘要内未展开的缩略语单独点名：Elsevier/Springer Guide 把它列为 desk-reject 条件
    ab = re.search(r"##\s*Abstract\s*\n(.*?)(?=\n##\s|\Z)", text, re.S | re.I)
    if ab:
        in_abs = sorted({s for s, _, _ in bad if re.search(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])", ab.group(1))})
        if in_abs:
            say("FAIL", "acronyms", f"摘要内未定义即使用: {in_abs}（Guide for Authors 硬规则）")
    if not bad:
        say("PASS", "acronyms", f"{len(first)} 个缩略语均在首现前展开")

# ----------------------------------------------------------------- scope
SCOPE_WORDS = r"\b(best|first|novel|all|always|never|consistently|outperforms?|state[- ]of[- ]the[- ]art|SOTA|significantly|robust|general(?:ly|izes)?|universal|any)\b"
# 强主张：275 篇已发表论文校准（references/validation-published-papers.md）——词表命中中 >90% 是 "first stage"、"all datasets" 这类叙述，
# 真正需要回表的只有下面这些搭配。强主张单独列 CLAIM 行；其余只计数不逐行打印，--verbose 才全列。
SCOPE_STRONG = re.compile(
    r"\b(the first (?:to|work|method|model|approach|attempt|study|time|holistic|end-to-end|unified|large-scale|systematic)"
    r"|first (?:\w+[- ]){0,3}(?:survey|review|benchmark|dataset|framework|system|attempt|demonstration|evidence|study|work)\b"
    r"|first to \w+"
    r"|(?:new|a new|achieves?|achieving|sets?|setting|establish(?:es|ing)?) (?:the )?(?:new )?state[- ]of[- ]the[- ]art"
    r"|outperforms? (?:all|every|each|any) "
    r"|(?:all|every) (?:existing|prior|previous|published|known|current) "
    r"|no (?:existing|prior|previous|published|other) (?:work|method|model|study|approach)"
    r"|(?:surpass(?:es|ing)?|exceed(?:s|ing)?|beat(?:s|ing)?) (?:all|every|human|expert)"
    r"|consistently outperforms?"
    r"|significantly outperforms?"
    r"|universal(?:ly)? (?:applicable|effective)"
    r"|generali[sz]es? to (?:all|any|arbitrary)"
    r"|under (?:any|all|every|arbitrary) (?:\w+[- ]){0,2}(?:loss|failure|condition|shift|setting|scenario|input|modality|channel)s?"
    r"|(?:for|on|across) (?:any|all|every|arbitrary) (?:\w+[- ]){0,2}(?:dataset|domain|platform|sensor|task|subject|patient|modality)s?"
    r"|robust to (?:any|all|every|arbitrary))\b", re.I)

# Impossibility wording ("no procedure can ...", "is impossible", "cannot be improved"): a proposition's job, not a claims-table row, so it is NOT part of
# SCOPE_STRONG (claims_check demands a claims row for those); the scope gate only lists it so the review seats trace each sentence to a proof.
SCOPE_IMPOSSIBLE = re.compile(
    r"\b(no (?:valid |such |known |distribution-free |possible )*(?:procedure|bound|method|algorithm|estimator|guarantee|test) (?:can|could|will|is able to)"
    r"|(?:is|are|proves? to be|remains?) (?:provably )?(?:impossible|unattainable|unachievable)"
    r"|impossibility (?:result|theorem|of)"
    r"|cannot (?:ever )?be (?:improved|avoided|attained|achieved|beaten))\b", re.I)

def gate_scope(a):
    text = body_only(read(a.manuscript))
    strong, weak = [], []
    for i, line in enumerate(text.splitlines(), 1):
        if SCOPE_STRONG.search(line) or SCOPE_IMPOSSIBLE.search(line):
            strong.append((i, line.strip()[:140]))
        elif re.search(SCOPE_WORDS, line, re.I):
            weak.append((i, line.strip()[:110]))
    for i, l in strong:
        say("WARN", "scope", f"CLAIM L{i}: {l}")
    if getattr(a, "verbose", False):
        for i, l in weak:
            say("INFO", "scope", f"L{i} {l}")
    say("PASS", "scope", f"强主张 {len(strong)} 句（必须逐句回表并写入 research-state.yaml scope_audit）；其余作用域词 {len(weak)} 行仅计数，--verbose 查看")

# ----------------------------------------------------------------- numbers
NUM = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?=\s*(?:%|±|\\pm|\b))")

def results_numbers(root, include_json=False):
    """默认只收 CSV：论文表格应由 results/*.csv 直接生成。原始 json 转储值太密，会让关口失去区分度。"""
    vals = set()
    for dp, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(dp, f)
            if f.endswith(".json") and not include_json:
                continue
            try:
                if f.endswith(".csv"):
                    for row in csv.reader(open(p, encoding="utf-8", errors="replace")):
                        for c in row:
                            for m in NUM.finditer(c): vals.add(float(m.group(0)))
                elif f.endswith(".json"):
                    def walk(o):
                        if isinstance(o, dict): [walk(v) for v in o.values()]
                        elif isinstance(o, list): [walk(v) for v in o]
                        elif isinstance(o, (int, float)) and not isinstance(o, bool): vals.add(float(o))
                        elif isinstance(o, str):
                            for m in NUM.finditer(o): vals.add(float(m.group(0)))
                    walk(json.load(open(p, encoding="utf-8")))
            except Exception:
                pass
    return vals

def matches(x, pool, text_repr, allow_pct=False):
    """正文数字 x 在结果池中有一个值四舍五入到相同小数位后完全相等。
    不用容差：容差 + 密集池 = 什么都能匹配。百分比换算后小数位同步移动（39.7% -> 0.397 要按 3 位比）。"""
    dec = len(text_repr.split(".")[1]) if "." in text_repr else 0
    cands = [(x, dec)] + ([(x / 100.0, dec + 2), (x * 100.0, max(dec - 2, 0))] if allow_pct else [])
    for cand, d in cands:
        if d in pool and round(cand, d) in pool[d]:
            return True
    return False

def bucket(pool_vals, max_dec=6):
    """按小数位预先四舍五入，避免 O(n) 扫描。"""
    b = {}
    for d in range(max_dec + 1):
        b[d] = {round(v, d) for v in pool_vals}
    return b

def _lookup(file, key):
    """file 为 csv: key = 'row_index,col_name' 或 'col_name=val,col_name'；json: key = 点路径 a.b.c"""
    if file.endswith(".json"):
        o = json.load(open(file, encoding="utf-8"))
        for part in key.split("."):
            o = o[int(part)] if isinstance(o, list) else o[part]
        return float(o)
    rows = list(csv.DictReader(open(file, encoding="utf-8")))
    if "=" in key:
        sel, col = key.rsplit(",", 1)
        conds = [kv.split("=", 1) for kv in sel.split("|")]          # "method=ours|cond=E1,mean": several selectors joined by |
        hit = [r for r in rows if all(r.get(k) == v for k, v in conds)]
        if len(hit) != 1:
            raise KeyError(f"{sel} 命中 {len(hit)} 行")
        return float(hit[0][col])
    i, col = key.split(",", 1)
    return float(rows[int(i)][col])

def gate_numbers(a):
    """溯源模式：paper/numbers.csv 每行 value,file,key；逐条取值并四舍五入到正文小数位后比对。
    不存在 numbers.csv 时退化为筛查模式，只给 WARN，永不 PASS（集合查询在真实结果池上无区分度）。"""
    nmap = os.path.join(os.path.dirname(a.manuscript), "numbers.csv")
    text = body_only(strip_code_math(read(a.manuscript)))
    if os.path.exists(nmap):
        rows = list(csv.DictReader(open(nmap, encoding="utf-8")))
        bad = 0
        for r in rows:
            v = r["value"].strip(); dec = len(v.split(".")[1]) if "." in v else 0
            try:
                got = _lookup(r["file"], r["key"])
            except Exception as ex:
                bad += 1; say("FAIL", "numbers", f"{v} <- {r['file']}#{r['key']} 取不到: {ex}"); continue
            if r.get("transform", "").strip() == "pct":
                got = got * 100.0
            if round(got, dec) != float(v):
                bad += 1; say("FAIL", "numbers", f"{v} != {round(got, dec)} ({r['file']}#{r['key']})")
            if v not in text:
                bad += 1; say("FAIL", "numbers", f"{v} 在 numbers.csv 里但正文没有（已删或改过）")
        # 覆盖率：正文表格里每个带小数的数都应在 numbers.csv
        mapped = {r["value"].strip() for r in rows}
        unmapped = []
        for l in text.splitlines():
            if not l.strip().startswith("|"): continue
            for m in NUM.finditer(l):
                sv = m.group(0)
                if "." in sv and sv not in mapped and not sv.startswith("+"):
                    unmapped.append(sv)
        # which tables hold the unregistered numbers? name them so the fix is actionable
        by_tab = {}
        cur = None
        for l in text.splitlines():
            cm = re.match(r"^\**\s*(Table)\s*(S?\d+)[a-z]?[\.\:\*]", l, re.I)
            if cm: cur = f"Table {cm.group(2)}"; continue
            if l.strip().startswith("|") and cur:
                for m in NUM.finditer(l):
                    sv = m.group(0)
                    if "." in sv and sv not in mapped and not sv.startswith("+"): by_tab.setdefault(cur, set()).add(sv)
        if unmapped:
            say("FAIL", "numbers", f"表格中 {len(set(unmapped))} 个数字未登记来源，按表: " + "; ".join(f"{t} ×{len(v)}" for t, v in sorted(by_tab.items())) + f"；样例 {sorted(set(unmapped))[:6]}")
        total_bad = bad + (1 if unmapped else 0)
        say("PASS" if total_bad == 0 else "FAIL", "numbers", f"溯源模式 {len(rows)} 条映射，{bad} 处值不符，{len(set(unmapped))} 个表格数字未登记")
        return
    if not os.path.isdir(a.results):
        say("FAIL", "numbers", f"{nmap} 与 {a.results} 都不存在"); return
    raw = results_numbers(a.results, include_json=a.include_json)
    pool = bucket(raw)
    cand_lines = [l for l in text.splitlines() if l.strip().startswith("|") or "%" in l or "±" in l]
    unmatched = []
    for l in cand_lines:
        pct = "%" in l
        for m in NUM.finditer(l):
            sv = m.group(0); x = float(sv)
            if sv.startswith("+") or re.fullmatch(r"(19|20)\d\d", sv) or ("." not in sv and abs(x) < 10):
                continue
            if not matches(x, pool, sv, allow_pct=pct):
                unmatched.append((sv, l.strip()[:100]))
    for sv, l in unmatched[:40]:
        say("WARN", "numbers", f"{sv} 不在 results/ 中 | {l}")
    say("WARN", "numbers", f"筛查模式（无 {nmap}）：{len(unmatched)} 处不在结果池。此模式只能抓明显错误，不能当通过；建 numbers.csv 后才会 PASS")

# ----------------------------------------------------------------- dpi
def gate_dpi(a):
    try:
        from PIL import Image
    except ImportError:
        say("WARN", "dpi", "未安装 Pillow，跳过"); return
    if not os.path.exists(a.figures):
        say("FAIL", "dpi", f"{a.figures} 不存在"); return
    min_dpi = 300
    try:
        import yaml  # optional
        st = yaml.safe_load(read(a.state)); min_dpi = int(st["target"].get("min_dpi") or 300)
    except Exception:
        pass
    bad = 0; n = 0; band = 0; tiny = 0
    for row in csv.DictReader(open(a.figures, encoding="utf-8")):
        f = row["file"]; n += 1
        if not os.path.exists(f):
            bad += 1; say("FAIL", "dpi", f"{f} 不存在"); continue
        if f.lower().endswith((".pdf", ".svg", ".eps")):
            say("PASS", "dpi", f"{f} 矢量"); continue
        w_mm = float(row["print_width_mm"])
        px, py = Image.open(f).size
        h_mm = py / px * w_mm if px else 0
        dpi = px / (w_mm / 25.4)
        # 校准依据（275 篇已发表论文）：Nature 系印刷版 90/130 张栅格落在 295–300 dpi，是 PDF 布局缩放的舍入，不是作者问题；
        # 宽 <40 mm 或高 <15 mm 的小栅格是图标、公式、logo，Elsevier/IEEE 制作不查。两类都降 WARN。
        if dpi < min_dpi * 0.985:
            if w_mm < 40 or h_mm < 15:
                tiny += 1; say("WARN", "dpi", f"{f} {px}px @ {w_mm}mm = {dpi:.0f} dpi，但尺寸 {w_mm:.0f}×{h_mm:.0f} mm 属图标/公式级小图")
            else:
                bad += 1; say("FAIL", "dpi", f"{f} {px}px @ {w_mm}mm = {dpi:.0f} dpi < {min_dpi}")
        elif dpi < min_dpi:
            band += 1; say("WARN", "dpi", f"{f} {dpi:.1f} dpi，在 {min_dpi} 的 1.5% 容差带内（布局缩放舍入）")
        if not row.get("source_data"):
            bad += 1; say("FAIL", "dpi", f"{f} 无 source_data")
        if row.get("inspected", "no").lower() != "yes":
            bad += 1; say("FAIL", "dpi", f"{f} 未裁图目测 (inspected != yes)")
    if bad == 0:
        say("PASS", "dpi", f"{n} 张图全部 ≥{min_dpi} dpi 且有来源、已目测（容差带 {band}，小图豁免 {tiny}）")
    _dpi_print_fonts(a)
    _dpi_fonts_embedded(a)
    _dpi_grayscale(a)
    _dpi_coverage(a)
    _dpi_count(a)

def _norm_floor(venue, family, col):
    """25th percentile of <col> (n_fig | n_tab) among published papers at this venue; falls back to the family
    when the venue is not in references/figure-norms-per-paper.csv. Returns (floor, group_label, n) or None."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "figure-norms-per-paper.csv")
    if not os.path.exists(path): return None
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    for key, label in ((venue, "venue"), (family, "family")):
        if not key: continue
        vals = sorted(int(r[col]) for r in rows if (r.get(label) or "").lower() == key.lower() and r.get(col, "").isdigit())
        if len(vals) >= 10:
            return vals[int(0.25 * (len(vals) - 1))], f"{label} {key}", len(vals)
    return None

def _dpi_count(a):
    """figure / table counts below the 25th percentile of the target venue's published papers -> WARN
    (figure-norms-per-paper.csv, 590-paper sample). Waive with target.figure_count_waiver: '<why>'."""
    venue = family = waiver = ""
    try:
        import yaml
        t = (yaml.safe_load(read(a.state)) or {}).get("target") or {}
        venue, family, waiver = t.get("venue") or "", t.get("family") or "", t.get("figure_count_waiver") or ""
    except Exception:
        pass
    if not os.path.exists(a.manuscript): return
    text = read(a.manuscript)
    n_fig = len({m.group(2) for m in CAP.finditer(text) if m.group(1).lower().startswith("fig") and not m.group(2).upper().startswith("S")})
    n_tab = len({m.group(2) for m in CAP.finditer(text) if m.group(1).lower() == "table" and not m.group(2).upper().startswith("S")})
    short = []; checked = 0
    for col, n, what in (("n_fig", n_fig, "图"), ("n_tab", n_tab, "表")):
        fl = _norm_floor(venue, family, col)
        if fl is None: continue
        checked += 1; floor, label, m = fl
        if n < floor: short.append(f"{what} {n} 张 < {label} 四分之三的论文有的 {floor} 张（{m} 篇样本）")
    if not checked: return   # no venue/family in the norms table: nothing to compare against
    if short and waiver:
        say("INFO", "dpi", f"图表数量低于目标刊常态但已豁免（{waiver}）：" + "；".join(short))
    elif short:
        say("WARN", "dpi", "；".join(short) + "。补图表，或在 state.target.figure_count_waiver 写明为什么不需要（references/figure-norms.md）")
    else:
        say("PASS", "dpi", f"正文 {n_fig} 图 {n_tab} 表，不低于 {venue or family} 已发表论文的下四分位")

FAMILY_MUST_TYPES = {"cs_journal": ["overview", "qualitative", "comparison", "ablation"], "cs_conf": ["overview", "qualitative", "comparison"], "nature": []}
# types that >= 70% of published papers in the family carry (references/figure-norms.md, "按家族" table, 590-paper sample); nature families
# are too heterogeneous for a must-list, so none is enforced there.

def _dpi_print_fonts(a):
    """printed font size of every vector figure = span size x (print_width_mm / native width); smallest below min_font_pt -> FAIL, below +1 -> WARN"""
    try:
        import fitz
    except ImportError:
        say("WARN", "dpi", "未安装 PyMuPDF（pip install pymupdf），跳过印刷字号检查"); return
    min_pt = 5.0
    try:
        import yaml
        st = yaml.safe_load(read(a.state)); min_pt = float(st["target"].get("min_font_pt") or 5.0)
    except Exception:
        pass
    bad = 0; checked = 0
    for row in csv.DictReader(open(a.figures, encoding="utf-8-sig")):
        f = row["file"]
        if not f.lower().endswith(".pdf") or not os.path.exists(f): continue
        try:
            doc = fitz.open(f); pg = doc[0]
            spans = [dict(sp, dir=l.get("dir", (1, 0))) for b in pg.get_text("dict")["blocks"] for l in b.get("lines", []) for sp in l["spans"] if sp["text"].strip()]   # rotation is a line property
            native_mm = pg.rect.width / 72 * 25.4; w_mm = float(row["print_width_mm"] or native_mm)
        except Exception as ex:
            say("WARN", "dpi", f"{f} 读不了文本层: {ex}"); continue
        checked += 1
        if not spans:
            say("INFO", "dpi", f"{f} 无文本层（栅格或已转曲线）：字号只能目测"); continue
        scale = w_mm / native_mm if native_mm else 1.0
        sizes = sorted(sp["size"] * scale for sp in spans); lo, med = sizes[0], sizes[len(sizes) // 2]
        smallest = min(spans, key=lambda sp: sp["size"])["text"].strip()[:30]
        if lo < min_pt:
            bad += 1; say("FAIL", "dpi", f"{f} 印刷最小字号 {lo:.1f} pt < {min_pt:g} pt（{native_mm:.0f} mm 原图排到 {w_mm:.0f} mm；最小的是 \"{smallest}\"）：按印刷宽度重画，不要缩放整图")
        elif lo < min_pt + 1:
            say("WARN", "dpi", f"{f} 印刷最小字号 {lo:.1f} pt（中位 {med:.1f}）：接近下限，确认是角标/刻度而不是正文标签")
        else:
            say("PASS", "dpi", f"{f} 印刷字号 {lo:.1f}–{med:.1f} pt @ {w_mm:.0f} mm")
        # dual axis: y-axis labels (rotated text) on both the left and the right edge of the page
        rot = [sp for sp in spans if abs(sp.get("dir", (1, 0))[0]) < 0.3 and len(sp["text"].strip()) > 3]
        if rot:
            xs = [sp["bbox"][0] for sp in rot]; W = pg.rect.width
            if any(x < 0.15 * W for x in xs) and any(x > 0.85 * W for x in xs):
                say("WARN", "dpi", f"{f} 左右两侧都有纵向轴标签：双纵轴图。两种量纲各画一个面板，或归一到同一底（dataviz 规则）")
    if checked and bad == 0: say("PASS", "dpi", f"{checked} 张矢量图的印刷字号全部 ≥ {min_pt:g} pt")

def _dpi_fonts_embedded(a):
    """Type 3 or unembedded fonts in a registered PDF -> FAIL (IEEE / Elsevier production reject them; matplotlib's default
    pdf.fonttype=3 produces exactly this). After scipilot-figure-skill check_figure. Needs pypdf; INFO if absent."""
    try:
        from pypdf import PdfReader
    except ImportError:
        say("INFO", "dpi", "未安装 pypdf（pip install pypdf），跳过字体嵌入检查"); return
    bad = 0; checked = 0
    for row in csv.DictReader(open(a.figures, encoding="utf-8-sig")):
        f = row["file"]
        if not f.lower().endswith(".pdf") or not os.path.exists(f): continue
        checked += 1; t3 = set(); noemb = set()
        try:
            for pg in PdfReader(f).pages:
                fonts = (pg.get("/Resources") or {}).get("/Font") or {}
                for _, fo in fonts.items():
                    fo = fo.get_object(); sub = str(fo.get("/Subtype", "")); base = str(fo.get("/BaseFont", "?"))
                    # fonttype 42 emits a Type0 composite font: the embedded program sits on the descendant's descriptor
                    cands = [fo] + [c.get_object() for c in (fo.get("/DescendantFonts") or [])]
                    emb = False
                    for c in cands:
                        d = c.get("/FontDescriptor"); d = d.get_object() if d else None
                        if d and any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3")): emb = True; break
                    if "Type3" in sub: t3.add(base)
                    elif not emb and "Type1" not in sub: noemb.add(base)
        except Exception as ex:
            say("WARN", "dpi", f"{f} 读不了字体表: {ex}"); continue
        if t3:
            bad += 1; say("FAIL", "dpi", f"{f} 含 Type 3 字体 {sorted(t3)[:3]}：IEEE / Elsevier 制作拒收；matplotlib 设 rcParams['pdf.fonttype']=42 重出（make_figure.py 已默认）")
        elif noemb:
            say("WARN", "dpi", f"{f} 字体可能未嵌入 {sorted(noemb)[:3]}：别人机器上会变替代字体")
    if checked and bad == 0: say("PASS", "dpi", f"{checked} 张 PDF 字体全部嵌入且无 Type 3")

def _dpi_grayscale(a):
    """a _gray.png next to each raster figure means the B&W / colour-vision check was possible; missing -> INFO"""
    miss = []
    for row in csv.DictReader(open(a.figures, encoding="utf-8-sig")):
        f = row["file"]; base = os.path.splitext(f)[0]
        if os.path.exists(f) and not os.path.exists(base + "_gray.png") and not os.path.exists(base + ".png"): continue
        if os.path.exists(f) and not os.path.exists(base + "_gray.png"): miss.append(f)
    if miss: say("INFO", "dpi", f"{len(miss)} 张图没有灰度预览 (_gray.png)：make_figure.py 自动出；手画的图用 PIL convert('L') 看一眼黑白能否分辨")

def _dpi_coverage(a):
    """figure types the venue family expects (>= 70% of published papers) must match a caption or be waived in figures.csv issues ('no <type>: <why>')"""
    fam = ""
    try:
        import yaml
        st = yaml.safe_load(read(a.state)); fam = (st.get("target") or {}).get("family") or ""
    except Exception:
        pass
    must = FAMILY_MUST_TYPES.get(fam)
    if not must: return
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import figure_norms as fn
    except Exception as ex:
        say("WARN", "dpi", f"figure_norms 不可用（{ex}），跳过图类型覆盖"); return
    if not os.path.exists(a.manuscript): return
    caps = [l for l in read(a.manuscript).splitlines() if re.match(r"^\*\*(Fig\.|Figure)\s*S?\d+", l)]
    found = {name for name, rx in fn.FIGURE_TYPES if any(re.search(rx, c, re.I) for c in caps)}
    waived = " ".join((r.get("issues") or "") for r in csv.DictReader(open(a.figures, encoding="utf-8-sig")))
    missing = [t for t in must if t not in found and not re.search(r"\bno\s+" + t + r"\s*:", waived, re.I)]
    if missing:
        say("WARN", "dpi", f"{fam} 论文 ≥70% 含的图类型本文题注没有命中: {missing}（references/figure-norms.md）。补图，或在 figures.csv 的 issues 列写 'no {missing[0]}: <为什么不需要>'")
    else:
        say("PASS", "dpi", f"{fam} 的常见图类型 {must} 均有题注命中或已写明豁免（题注共 {len(caps)} 条）")

# ----------------------------------------------------------------- leftover markers
MARKERS = [(r"\\(?:todo|TODO|fixme|FIXME|hl)(?![A-Za-z])", "LaTeX 批注命令"), (r"\b(?:TODO|FIXME|XXX)\b", "TODO/FIXME/XXX"), (r"\[(?:待补充|TBD|tbd)\]", "[待补充]/[TBD]"),
           (r"\?\?", "?? （PDF/LaTeX 未解析的引用）"), (r"\(bib key not found", "tex_to_md: bib 键找不到")]
RAWKEY_REF = re.compile(r"^\[\d+\]\s+(\S+)\s+\(bibkey\s+(\S+)\)\s*$", re.M)

def scan_markers(path, label):
    """FAIL on unfinished-text markers and on reference lines that are only the bib key ("[1] llvip21 (bibkey llvip21)"); returns the hit count."""
    txt = re.sub(r"`[^`\n]*`", " ", strip_code_math(read(path))); hits = []
    for pat, name in MARKERS:
        for m in re.finditer(pat, txt): hits.append((m.start(), name, m.group(0)))
    for m in RAWKEY_REF.finditer(txt):
        if m.group(1) == m.group(2): hits.append((m.start(), "参考文献条目只有键", m.group(0).strip()))
    hits.sort()
    for pos, name, tok in hits[:8]: say("FAIL", "markers", f"{label} L{txt.count(chr(10), 0, pos) + 1}: {name} {tok!r}")
    if len(hits) > 8: say("FAIL", "markers", f"{label}: 另有 {len(hits) - 8} 处")
    return len(hits)

def gate_markers(a):
    if scan_markers(a.manuscript, os.path.basename(a.manuscript)) == 0: say("PASS", "markers", "正文无 TODO/FIXME/[待补充]/?? 与裸 bibkey 参考文献条目")

# ----------------------------------------------------------------- limits
def gate_limits(a):
    gate_markers(a)      # hard rules of the manuscript: unfinished text and raw bibkeys are as disqualifying as a word limit
    try:
        import yaml
        st = yaml.safe_load(read(a.state))
    except Exception as ex:
        say("WARN", "limits", f"读不到 state ({ex})，跳过"); return
    t = st.get("target", {})
    text = read(a.manuscript)
    body = body_only(strip_code_math(text))
    words = len(re.findall(r"\b\w+\b", body))
    nrefs = len(parse_bib(read(a.bib))) if os.path.exists(a.bib) else None
    kw = re.search(r"^\**Keywords?\.?\**[:：.]?\s*(.+)$", text, re.M | re.I)
    nkw = len(re.split(r"[;,；，]", kw.group(1))) if kw else None
    checks = [("word_limit", words), ("ref_max", nrefs), ("keyword_max", nkw)]
    ok = True
    for k, v in checks:
        lim = t.get(k)
        if lim and v is not None and v > lim:
            ok = False; say("FAIL", "limits", f"{k}: {v} > {lim}")
        else:
            say("INFO", "limits", f"{k}: {v} (limit {lim})")
    if ok: say("PASS", "limits", "硬规则内")

# ----------------------------------------------------------------- submission
BLIND_PATTERNS = [r"our previous", r"we previously", r"our prior", r"@\w+\.(edu|org|se|com)", r"grant\s*(no|number)", r"funded by"]

def gate_submission(a):
    if not os.path.isdir(a.submission):
        say("FAIL", "submission", f"{a.submission} 不存在"); return
    body = body_only(strip_code_math(read(a.manuscript)))
    body_nums = {m.group(0) for m in NUM.finditer(body)}
    ok = True
    for name in ("title_page.md", "cover_letter.md", "highlights.md"):
        p = os.path.join(a.submission, name)
        if not os.path.exists(p):
            say("WARN", "submission", f"{name} 缺失"); continue
        txt = read(p)
        for m in NUM.finditer(txt):
            s = m.group(0)
            if re.fullmatch(r"(19|20)\d\d", s): continue
            if s not in body_nums and not matches(float(s), bucket({float(x) for x in body_nums}), s, allow_pct=True):
                ok = False; say("FAIL", "submission", f"{name} 中的数字 {s} 未在正文出现")
    blind = os.path.join(a.submission, "blind.md")
    for name in ("title_page.md", "cover_letter.md", "highlights.md", "blind.md"):
        p = os.path.join(a.submission, name)
        if os.path.exists(p) and scan_markers(p, "submission/" + name): ok = False
    if os.path.exists(blind):
        txt = body_only(read(blind))     # cited authors in the reference list are not an anonymity leak
        names = []
        try:
            import yaml
            st = yaml.safe_load(read(a.state)); names = st.get("blind_terms", []) or []
        except Exception:
            pass
        for pat in BLIND_PATTERNS + [re.escape(n) for n in names]:
            for m in re.finditer(pat, txt, re.I):
                ok = False
                line = txt.count("\n", 0, m.start()) + 1
                say("FAIL", "submission", f"盲稿 L{line} 命中 /{pat}/")
    if ok: say("PASS", "submission", "投稿文件数字与正文一致，盲稿干净")

# ----------------------------------------------------------------- main
GATES = {"refs": gate_refs, "floats": gate_floats, "acronyms": gate_acronyms, "scope": gate_scope,
         "numbers": gate_numbers, "dpi": gate_dpi, "limits": gate_limits, "submission": gate_submission, "markers": gate_markers}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gate", choices=list(GATES) + ["all"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--manuscript", default="paper/manuscript.md")
    ap.add_argument("--bib", default="paper/refs.bib")
    ap.add_argument("--results", default="results")
    ap.add_argument("--figures", default="figures.csv")
    ap.add_argument("--state", default="research-state.yaml")
    ap.add_argument("--submission", default="submission")
    ap.add_argument("--supplement", nargs="*", default=[], help="floats: 补充材料 md，用于登记 S 编号题注")
    ap.add_argument("--verbose", action="store_true", help="scope: 连非强主张的作用域词也逐行列出")
    ap.add_argument("--no-net", action="store_true", help="跳过联网的 refs")
    ap.add_argument("--include-json", action="store_true", help="numbers: 结果池也收 results/ 下的 json（默认只收 csv）")
    a = ap.parse_args()
    os.chdir(a.project)
    if not os.path.exists(a.manuscript) and a.gate != "refs":
        print(f"[FAIL] {a.manuscript} 不存在"); sys.exit(1)
    order = ["refs", "floats", "acronyms", "scope", "numbers", "dpi", "limits", "submission"] if a.gate == "all" else [a.gate]
    for g in order:
        if g == "refs" and a.no_net: continue
        print(f"\n== {g} ==")
        try:
            GATES[g](a)
        except Exception as ex:
            say("FAIL", g, f"脚本异常: {ex!r}")
    with open("gate_report.md", "w", encoding="utf-8") as f:
        f.write(f"# gate_report  {time.strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("\n".join(REPORT) + "\n")
        f.write(f"\n**{'ALL PASS' if FAILS == 0 else str(FAILS) + ' FAIL'}**\n")
    print(f"\n{'ALL PASS' if FAILS == 0 else str(FAILS) + ' FAIL'} -> gate_report.md")
    sys.exit(0 if FAILS == 0 else 1)

if __name__ == "__main__":
    main()
