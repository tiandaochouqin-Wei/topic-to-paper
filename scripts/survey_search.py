# -*- coding: utf-8 -*-
"""S1/S3 — survey literature chain, generic version of the per-project lit/*.py scripts. Run by Claude.

  search    python survey_search.py search --query "<q>" [--sources pubmed,arxiv,openalex] [--since 2015] [--until 2026] [--max 2000]
                   [--pubmed-query Q] [--arxiv-query Q] [--openalex-query Q] [--abstracts] [--out literature/candidates.csv]
                   [--log literature/search_log.json] [--no-net] [--from-dir <dir of saved responses>]
            -> one row per deduplicated candidate (doi > pmid > arxiv_id > openalex_id > normalised title), merged into an existing
               candidates.csv; search_log.json gets one entry per source {source, query, date, count, fetched} (G-S1 reads it).
               PubMed is sliced by year when a query returns more than 9 000 hits (E-utilities stop at retstart 10 000).
  snowball  python survey_search.py snowball (--dois 10.x,10.y | --seeds literature/seeds.csv) [--direction both|references|citations]
                   [--out ...] [--log ...] [--no-net] [--from-dir ...]
            -> Semantic Scholar Graph API, one hop; rows get source s2:references / s2:citations.
  triage    python survey_search.py triage [--candidates literature/candidates.csv] [--out coding/screening_sheet.csv]
                   [--include-any "a,b"] [--include-all "c"] [--exclude "d,e"] [--since 2015] [--prisma literature/prisma_flow.json]
            -> rule pre-screen on title (+abstract): exclude with a reason when a rule fires, else `maybe` for Claude's title/abstract
               screening; decisions already made by Claude are never overwritten; PRISMA counts updated.
  fix-dois  python survey_search.py fix-dois [--candidates ...] [--no-net] [--from-dir ...]
            -> rows with a PMID and no DOI get the DOI from PubMed efetch, read ONLY from PubmedData/ArticleIdList (the reference list
               of the article carries other papers' DOIs under the same tag — that was the InfoFusion incident).

Politeness: NCBI 3 req/s (10 with NCBI_API_KEY), arXiv one page per 3 s, OpenAlex polite pool via T2P_CONTACT_EMAIL, Semantic Scholar
1 req/s (S2_API_KEY raises it). --from-dir reads pubmed_esearch.xml / pubmed_efetch.xml / arxiv.xml / openalex.json /
s2_references.json / s2_citations.json instead of the network, so the parsers are testable offline."""
import argparse, csv, datetime, io, json, os, re, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

EMAIL = os.environ.get("T2P_CONTACT_EMAIL", "topic-to-paper@example.org")
UA = {"User-Agent": f"topic-to-paper/2.6 (mailto:{EMAIL})"}
COLS = ["source", "doi", "pmid", "arxiv_id", "openalex_id", "s2_id", "title", "year", "venue", "abstract", "first_seen"]
ID_FIELDS = ("doi", "pmid", "arxiv_id", "openalex_id", "s2_id")
PREFIX = {"doi": "doi", "pmid": "pmid", "arxiv_id": "arxiv", "openalex_id": "oa", "s2_id": "s2"}
TODAY = datetime.date.today().isoformat()


def say(st, msg): print(f"[{st}] search: {msg}")


def http(url, tries=3, sleep=1.0, headers=None):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})})
            return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        except Exception as ex:
            if i == tries - 1: say("WARN", f"net fail {url[:90]}… {ex}"); return ""
            time.sleep(30 if "429" in str(ex) else sleep * (i + 2))


# ------------------------------------------------------------------ normalisation / merge
def norm_doi(d):
    d = (d or "").strip().lower(); d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d); return d.strip("/ ")


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:80]


def id_key(field, value):
    v = str(value).strip()
    if field == "doi": v = norm_doi(v)
    if field == "arxiv_id": v = re.sub(r"v\d+$", "", v)
    return f"{PREFIX[field]}:{v}"


def id_keys(r):
    return [id_key(f, r[f]) for f in ID_FIELDS if (r.get(f) or "").strip()]


def key_of(r):
    ks = id_keys(r)
    return ks[0] if ks else "title:" + norm_title(r.get("title"))


def read_rows(p):
    if not os.path.exists(p): return []
    return list(csv.DictReader(io.open(p, encoding="utf-8-sig")))


def write_rows(p, rows, cols=COLS):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow({c: r.get(c, "") for c in cols})


def merge(existing, new):
    """merge by identifier; a known row gains missing ids / abstract and the new source name; returns (rows, n_added)"""
    by = {}; order = []
    for r in existing:
        k = key_of(r); by[k] = r; order.append(k)
        for kk in id_keys(r) + ["title:" + norm_title(r.get("title"))]: by.setdefault(kk, r)
    added = 0; dropped = 0
    for r in new:
        r["doi"] = norm_doi(r.get("doi"))
        if not id_keys(r):                 # a reference S2 could not resolve, or a record without any id: cannot be deduplicated or verified (G-S1)
            dropped += 1; continue
        keys = [key_of(r)] + id_keys(r) + ["title:" + norm_title(r.get("title"))]
        hit = next((by[k] for k in keys if k in by and by[k] is not None), None)
        if hit is None:
            r.setdefault("first_seen", TODAY); k = key_of(r); by[k] = r; order.append(k); added += 1
            for kk in keys: by.setdefault(kk, r)
        else:
            for c in ID_FIELDS + ("abstract", "venue", "year", "title"):
                if not hit.get(c) and r.get(c): hit[c] = r[c]
            srcs = set(filter(None, (hit.get("source") or "").split("|"))) | set(filter(None, (r.get("source") or "").split("|")))
            hit["source"] = "|".join(sorted(srcs))
    seen = set(); out = []
    for k in order:
        r = by[k]
        if id(r) in seen: continue
        seen.add(id(r)); out.append(r)
    if dropped: say("INFO", f"{dropped} 条没有任何标识符（DOI/PMID/arXiv/OpenAlex/S2 id）的记录未入库：无法去重与核实，通常是 S2 未解析的参考文献条目")
    return out, added


def log_source(log_path, entry):
    log = {"sources": []}
    if os.path.exists(log_path):
        try: log = json.load(io.open(log_path, encoding="utf-8"))
        except Exception: pass
        if isinstance(log, list): log = {"sources": log}
        log.setdefault("sources", [])
    log["sources"].append(entry)
    return log


def save_log(log_path, log, total):
    log["dedup_total"] = total
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    io.open(log_path, "w", encoding="utf-8").write(json.dumps(log, ensure_ascii=False, indent=1) + "\n")


# ------------------------------------------------------------------ PubMed
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def ncbi_params(extra):
    p = dict(extra); p["tool"] = "topic-to-paper"; p["email"] = EMAIL
    if os.environ.get("NCBI_API_KEY"): p["api_key"] = os.environ["NCBI_API_KEY"]
    return urllib.parse.urlencode(p)


def pubmed_count(term):
    x = http(EUTILS + "esearch.fcgi?" + ncbi_params({"db": "pubmed", "term": term, "retmax": 0}))
    m = re.search(r"<Count>(\d+)</Count>", x or ""); return int(m.group(1)) if m else -1


def pubmed_ids(term, retmax):
    ids = []; start = 0
    while start < retmax:
        n = min(500, retmax - start)
        x = http(EUTILS + "esearch.fcgi?" + ncbi_params({"db": "pubmed", "term": term, "retstart": start, "retmax": n, "sort": "pub_date"}))
        got = re.findall(r"<Id>(\d+)</Id>", x or "")
        ids += got; time.sleep(0.34 if not os.environ.get("NCBI_API_KEY") else 0.11)
        if len(got) < n: break
        start += n
    return ids


def parse_pubmed_xml(xml_text, want_abstract=False):
    """PubmedArticleSet -> rows. DOI only from PubmedData/ArticleIdList — never from the article's own reference list."""
    rows = []
    try: root = ET.fromstring(xml_text)
    except ET.ParseError as ex: say("WARN", f"PubMed XML 不可解析: {ex}"); return rows
    for art in root.iter("PubmedArticle"):
        mc = art.find("MedlineCitation"); pd = art.find("PubmedData")
        pmid = (mc.findtext("PMID") if mc is not None else "") or ""
        a = mc.find("Article") if mc is not None else None
        title = "".join((a.find("ArticleTitle").itertext())).strip() if a is not None and a.find("ArticleTitle") is not None else ""
        venue = a.findtext("Journal/Title", "") if a is not None else ""
        year = ""
        if a is not None:
            y = a.findtext("Journal/JournalIssue/PubDate/Year") or a.findtext("Journal/JournalIssue/PubDate/MedlineDate") or ""
            m = re.search(r"\d{4}", y); year = m.group(0) if m else ""
        doi = ""
        if pd is not None:
            for aid in pd.findall("ArticleIdList/ArticleId"):           # direct child list only: ReferenceList/.../ArticleId is other papers
                if aid.get("IdType") == "doi": doi = (aid.text or "").strip()
        abstract = " ".join(" ".join(t.itertext()).strip() for t in a.findall("Abstract/AbstractText")) if (want_abstract and a is not None) else ""
        rows.append({"source": "pubmed", "doi": doi, "pmid": pmid, "title": title, "year": year, "venue": venue, "abstract": abstract})
    return rows


def pubmed_search(term, since, until, max_n, abstracts, from_dir):
    if from_dir:
        xml_e = io.open(os.path.join(from_dir, "pubmed_esearch.xml"), encoding="utf-8").read()
        m = re.search(r"<Count>(\d+)</Count>", xml_e); count = int(m.group(1)) if m else 0
        rows = parse_pubmed_xml(io.open(os.path.join(from_dir, "pubmed_efetch.xml"), encoding="utf-8").read(), abstracts)
        return rows, count
    base = f"({term}) AND {since}:{until}[dp]" if since or until else term
    count = pubmed_count(base)
    if count < 0: return [], -1
    slices = [base]
    if count > 9000:   # E-utilities cannot page past retstart 10 000: slice by year
        slices = [f"({term}) AND {y}[dp]" for y in range(int(since or 1900), int(until or datetime.date.today().year) + 1)]
        say("INFO", f"PubMed {count} 条 > 9000，按年切成 {len(slices)} 片")
    ids = []
    for s in slices:
        c = pubmed_count(s) if len(slices) > 1 else count
        if c <= 0: continue
        ids += pubmed_ids(s, min(c, max_n - len(ids)))
        if len(ids) >= max_n: break
    rows = []
    for i in range(0, len(ids), 200):
        x = http(EUTILS + "efetch.fcgi?" + ncbi_params({"db": "pubmed", "id": ",".join(ids[i:i + 200]), "retmode": "xml"}))
        rows += parse_pubmed_xml(x or "", abstracts); time.sleep(0.34)
    return rows, count


# ------------------------------------------------------------------ arXiv
ARXIV_NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom", "os": "http://a9.com/-/spec/opensearch/1.1/"}


def parse_arxiv_xml(xml_text):
    rows = []; total = None
    try: root = ET.fromstring(xml_text)
    except ET.ParseError as ex: say("WARN", f"arXiv XML 不可解析: {ex}"); return rows, 0
    t = root.findtext("os:totalResults", None, ARXIV_NS); total = int(t) if t and t.isdigit() else None
    for e in root.findall("a:entry", ARXIV_NS):
        aid = (e.findtext("a:id", "", ARXIV_NS) or "").rsplit("/abs/", 1)[-1]
        rows.append({"source": "arxiv", "doi": e.findtext("x:doi", "", ARXIV_NS) or "", "arxiv_id": re.sub(r"v\d+$", "", aid),
                     "title": re.sub(r"\s+", " ", e.findtext("a:title", "", ARXIV_NS) or "").strip(), "year": (e.findtext("a:published", "", ARXIV_NS) or "")[:4],
                     "venue": (e.findtext("x:journal_ref", "", ARXIV_NS) or "arXiv").strip(), "abstract": re.sub(r"\s+", " ", e.findtext("a:summary", "", ARXIV_NS) or "").strip()})
    return rows, (total if total is not None else len(rows))


def arxiv_query_from(q):
    """plain words -> all:word AND …; keep the user's own field syntax when present"""
    if re.search(r"\b(all|ti|abs|au|cat):", q): return q
    phrases = [p.strip().strip('"') for p in re.split(r"\s+(?:AND|OR)\s+", q) if p.strip()]
    ops = re.findall(r"\s+(AND|OR)\s+", q)
    out = []
    for i, p in enumerate(phrases):
        out.append(f'all:"{p}"' if " " in p else f"all:{p}")
        if i < len(ops): out.append(ops[i])
    return " ".join(out)


def arxiv_search(q, since, until, max_n, from_dir):
    if from_dir: return parse_arxiv_xml(io.open(os.path.join(from_dir, "arxiv.xml"), encoding="utf-8").read())
    rows = []; total = 0; start = 0
    while start < max_n:
        n = min(200, max_n - start)
        x = http("https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": q, "start": start, "max_results": n, "sortBy": "submittedDate", "sortOrder": "descending"}))
        got, total = parse_arxiv_xml(x or "")
        got = [r for r in got if (not since or (r["year"] and int(r["year"]) >= int(since))) and (not until or (r["year"] and int(r["year"]) <= int(until)))]
        rows += got
        if len(got) < n or (total and start + n >= total): break
        start += n; time.sleep(3)
    return rows, total


# ------------------------------------------------------------------ OpenAlex
def inverted_to_text(inv):
    if not isinstance(inv, dict): return ""
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in pos)


def parse_openalex_json(js, abstracts=False):
    rows = []
    try: d = json.loads(js) if isinstance(js, str) else js
    except Exception as ex: say("WARN", f"OpenAlex JSON 不可解析: {ex}"); return rows, 0, None
    for w in d.get("results", []):
        ids = w.get("ids") or {}
        pmid = re.sub(r"\D", "", ids.get("pmid", "") or "")
        rows.append({"source": "openalex", "doi": norm_doi(w.get("doi") or ""), "pmid": pmid, "openalex_id": (w.get("id") or "").rsplit("/", 1)[-1],
                     "title": w.get("title") or w.get("display_name") or "", "year": str(w.get("publication_year") or ""),
                     "venue": (((w.get("primary_location") or {}).get("source") or {}).get("display_name")) or "",
                     "abstract": inverted_to_text(w.get("abstract_inverted_index")) if abstracts else ""})
    meta = d.get("meta") or {}
    return rows, int(meta.get("count") or len(rows)), meta.get("next_cursor")


def openalex_search(q, since, until, max_n, abstracts, from_dir):
    if from_dir:
        rows, count, _ = parse_openalex_json(io.open(os.path.join(from_dir, "openalex.json"), encoding="utf-8").read(), abstracts); return rows, count
    q = re.sub(r"\b(AND|OR|NOT)\b|[\"()\[\]]", " ", q); q = re.sub(r"\s+", " ", q).strip()
    filt = "type:article" + (f",publication_year:{since or 1900}-{until or datetime.date.today().year}")
    rows = []; cursor = "*"; count = 0
    while cursor and len(rows) < max_n:
        x = http("https://api.openalex.org/works?" + urllib.parse.urlencode({"search": q, "filter": filt, "per-page": min(200, max_n - len(rows)), "cursor": cursor, "mailto": EMAIL}))
        got, count, cursor = parse_openalex_json(x or "{}", abstracts); rows += got
        if not got: break
        time.sleep(0.5)
    return rows, count


# ------------------------------------------------------------------ Semantic Scholar snowball
S2 = "https://api.semanticscholar.org/graph/v1/paper/"


def s2_headers():
    return {"x-api-key": os.environ["S2_API_KEY"]} if os.environ.get("S2_API_KEY") else {}


def parse_s2_json(js, direction):
    rows = []
    try: d = json.loads(js) if isinstance(js, str) else js
    except Exception as ex: say("WARN", f"S2 JSON 不可解析: {ex}"); return rows
    key = "citedPaper" if direction == "references" else "citingPaper"
    for it in (d.get("data") or []):          # S2 answers "data": null for papers whose reference list it does not hold
        p = it.get(key) or {}; ex = p.get("externalIds") or {}
        rows.append({"source": f"s2:{direction}", "doi": norm_doi(ex.get("DOI") or ""), "pmid": str(ex.get("PubMed") or ""), "arxiv_id": ex.get("ArXiv") or "",
                     "s2_id": p.get("paperId") or "",       # papers S2 holds without any external id still get a resolvable identifier
                     "title": p.get("title") or "", "year": str(p.get("year") or ""), "venue": p.get("venue") or ""})
    return rows


def s2_id(seed):
    """Semantic Scholar paper id from a bare DOI / arXiv id / PMID / S2 paperId or an already-prefixed id (DOI:, ARXIV:, PMID:, CorpusId:, …)."""
    s = seed.strip()
    if re.match(r"(?i)^(doi|arxiv|pmid|pmcid|corpusid|mag|acl|dblp|url):", s):
        pre, rest = s.split(":", 1); return pre.upper().replace("CORPUSID", "CorpusId") + ":" + rest.strip()
    if re.match(r"^10\.\d{4,}/", s): return "DOI:" + s
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", s): return "ARXIV:" + re.sub(r"v\d+$", "", s)
    if s.isdigit(): return "PMID:" + s
    return s


def snowball(seeds, direction, from_dir):
    rows = []
    for d in (("references", "citations") if direction == "both" else (direction,)):
        if from_dir:
            p = os.path.join(from_dir, f"s2_{d}.json")
            if os.path.exists(p): rows += parse_s2_json(io.open(p, encoding="utf-8").read(), d)
            continue
        for s in seeds:
            x = http(S2 + f"{urllib.parse.quote(s2_id(s), safe=':/')}/{d}?" + urllib.parse.urlencode({"fields": "title,year,venue,externalIds", "limit": 500}), headers=s2_headers())
            if x: rows += parse_s2_json(x, d)
            else: say("WARN", f"{s2_id(s)}: Semantic Scholar 无此记录或限流 —— 换 ARXIV:/PMID: 形式的 id 再试，或把种子换成 S2 收录的那篇")
            time.sleep(1.2 if not os.environ.get("S2_API_KEY") else 0.2)
    return rows


# ------------------------------------------------------------------ commands
def cmd_search(a):
    srcs = [s.strip().lower() for s in a.sources.split(",") if s.strip()]
    existing = read_rows(a.out); log = {"sources": []}
    if os.path.exists(a.log):
        try: log = json.load(io.open(a.log, encoding="utf-8")); log = {"sources": log} if isinstance(log, list) else log; log.setdefault("sources", [])
        except Exception: pass
    all_new = []
    if a.no_net and not a.from_dir: say("INFO", "--no-net 且无 --from-dir：不检索，只重写现有文件"); srcs = []
    for s in srcs:
        q = {"pubmed": a.pubmed_query, "arxiv": a.arxiv_query or (arxiv_query_from(a.query) if a.query else ""), "openalex": a.openalex_query}.get(s) or a.query
        if not q: say("FAIL", f"{s}: 没有检索式（--query 或 --{s}-query）"); continue
        if s == "pubmed": rows, count = pubmed_search(q, a.since, a.until, a.max, a.abstracts, a.from_dir)
        elif s == "arxiv": rows, count = arxiv_search(q, a.since, a.until, a.max, a.from_dir)
        elif s == "openalex": rows, count = openalex_search(q, a.since, a.until, a.max, a.abstracts, a.from_dir)
        else: say("WARN", f"未知来源 {s}"); continue
        log["sources"].append({"source": s, "query": q, "date": TODAY, "count": count, "fetched": len(rows), "since": a.since, "until": a.until})
        say("INFO", f"{s}: {count} 命中，取回 {len(rows)} 条（{q[:70]}）"); all_new += rows
    merged, added = merge(existing, all_new)
    write_rows(a.out, merged); save_log(a.log, log, len(merged))
    say("PASS", f"candidates.csv {len(merged)} 行（新增 {added}，去重后）→ {a.out}；search_log.json {len(log['sources'])} 条检索记录 → {a.log}")


def cmd_snowball(a):
    seeds = [s.strip() for s in (a.dois or "").split(",") if s.strip()]
    if a.seeds and os.path.exists(a.seeds): seeds += [norm_doi(r.get("doi")) for r in read_rows(a.seeds) if r.get("doi")]
    if not seeds and not a.from_dir: say("FAIL", "没有种子 DOI（--dois 或 --seeds）"); sys.exit(1)
    rows = snowball(seeds, a.direction, a.from_dir)
    existing = read_rows(a.out); merged, added = merge(existing, rows)
    write_rows(a.out, merged)
    log = log_source(a.log, {"source": f"semantic_scholar:{a.direction}", "query": f"snowball from {len(seeds)} seed DOIs, one hop", "date": TODAY, "count": len(rows), "fetched": len(rows), "seeds": seeds[:20]})
    save_log(a.log, log, len(merged))
    say("PASS", f"snowball {a.direction}: {len(rows)} 条，新增 {added} → {a.out}")


def cmd_triage(a):
    rows = read_rows(a.candidates)
    if not rows: say("FAIL", f"{a.candidates} 为空或不存在"); sys.exit(1)
    inc_any = [t.strip().lower() for t in a.include_any.split(",") if t.strip()]
    inc_all = [t.strip().lower() for t in a.include_all.split(",") if t.strip()]
    exc = [t.strip().lower() for t in a.exclude.split(",") if t.strip()]
    old = {key_of(r): r for r in read_rows(a.out)}
    out = []; n_rule = 0
    for r in rows:
        text = ((r.get("title") or "") + " " + (r.get("abstract") or "")).lower()
        prev = old.get(key_of(r))
        row = {"doi": r.get("doi", ""), "pmid": r.get("pmid", ""), "arxiv_id": r.get("arxiv_id", ""), "title": r.get("title", ""), "year": r.get("year", ""), "decision": "", "reason": "", "screen_pass": "title-rule"}
        if prev and (prev.get("decision") or "").strip() and not (prev.get("reason") or "").startswith("rule:"):
            row.update({"decision": prev["decision"], "reason": prev["reason"], "screen_pass": prev.get("screen_pass") or "abstract"}); out.append(row); continue
        reason = ""
        try: yr = int(r.get("year") or 0)
        except ValueError: yr = 0
        if a.since and yr and yr < int(a.since): reason = f"rule: year {yr} < {a.since}"
        elif exc and any(t in text for t in exc): reason = "rule: exclude term " + next(t for t in exc if t in text)
        elif inc_any and not any(t in text for t in inc_any): reason = "rule: no include-any term"
        elif inc_all and not all(t in text for t in inc_all): reason = "rule: missing include-all term " + next(t for t in inc_all if t not in text)
        if reason: row.update({"decision": "exclude", "reason": reason}); n_rule += 1
        else: row.update({"decision": "maybe", "reason": "rule pre-screen passed; title/abstract screening pending"})
        out.append(row)
    write_rows(a.out, out, ["doi", "pmid", "arxiv_id", "title", "year", "decision", "reason", "screen_pass"])
    dec = {}
    for r in out: dec[r["decision"]] = dec.get(r["decision"], 0) + 1
    # PRISMA: identified = sum of per-source counts in search_log (fallback: candidates), deduplicated = candidates, screened_title = all,
    # screened_abstract = those that survived the rules, included = Claude's include decisions
    prisma = {}
    if os.path.exists(a.prisma):
        try: prisma = json.load(io.open(a.prisma, encoding="utf-8"))
        except Exception: prisma = {}
    identified = len(rows)
    if os.path.exists(a.log):
        try:
            lg = json.load(io.open(a.log, encoding="utf-8")); srcs = lg.get("sources", lg if isinstance(lg, list) else [])
            tot = sum(int(s.get("fetched") or s.get("count") or 0) for s in srcs); identified = max(tot, len(rows))
        except Exception: pass
    prisma.update({"identified": identified, "deduplicated": len(rows), "screened_title": len(rows), "screened_abstract": dec.get("maybe", 0) + dec.get("include", 0), "included": dec.get("include", 0)})
    os.makedirs(os.path.dirname(a.prisma) or ".", exist_ok=True)
    io.open(a.prisma, "w", encoding="utf-8").write(json.dumps(prisma, ensure_ascii=False, indent=1) + "\n")
    say("PASS", f"screening_sheet.csv {len(out)} 行：规则排除 {n_rule}，待人工 maybe {dec.get('maybe', 0)}，已决 include {dec.get('include', 0)} / exclude {dec.get('exclude', 0) - n_rule}；PRISMA → {a.prisma}")


def cmd_fix_dois(a):
    rows = read_rows(a.candidates)
    need = [r for r in rows if (r.get("pmid") or "").strip() and not (r.get("doi") or "").strip()]
    if not need: say("PASS", "没有缺 DOI 的 PubMed 行"); return
    found = {}
    if a.from_dir:
        for r in parse_pubmed_xml(io.open(os.path.join(a.from_dir, "pubmed_efetch.xml"), encoding="utf-8").read()): found[r["pmid"]] = r["doi"]
    elif not a.no_net:
        ids = [r["pmid"].strip() for r in need]
        for i in range(0, len(ids), 200):
            x = http(EUTILS + "efetch.fcgi?" + ncbi_params({"db": "pubmed", "id": ",".join(ids[i:i + 200]), "retmode": "xml"}))
            for r in parse_pubmed_xml(x or ""): found[r["pmid"]] = r["doi"]
            time.sleep(0.34)
    n = 0
    for r in need:
        d = found.get(r["pmid"].strip())
        if d: r["doi"] = norm_doi(d); n += 1
    write_rows(a.candidates, rows)
    say("PASS", f"{n}/{len(need)} 行补上 DOI（只取 PubmedData/ArticleIdList，不取参考文献表）→ {a.candidates}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("--query", default=""); s.add_argument("--sources", default="pubmed,arxiv,openalex"); s.add_argument("--since", default=""); s.add_argument("--until", default="")
    s.add_argument("--max", type=int, default=2000); s.add_argument("--pubmed-query", default=""); s.add_argument("--arxiv-query", default=""); s.add_argument("--openalex-query", default="")
    s.add_argument("--abstracts", action="store_true", help="also store abstracts (bigger csv; lets triage use them)")
    b = sub.add_parser("snowball"); b.add_argument("--dois", "--ids", dest="dois", default="", help="seed ids, comma-separated: bare DOI, arXiv id, PMID, or prefixed DOI:/ARXIV:/PMID:/CorpusId:"); b.add_argument("--seeds", default="", help="csv with a doi column"); b.add_argument("--direction", choices=["both", "references", "citations"], default="both")
    t = sub.add_parser("triage"); t.add_argument("--candidates", default="literature/candidates.csv"); t.add_argument("--out", default="coding/screening_sheet.csv")
    t.add_argument("--include-any", default=""); t.add_argument("--include-all", default=""); t.add_argument("--exclude", default=""); t.add_argument("--since", default=""); t.add_argument("--prisma", default="literature/prisma_flow.json"); t.add_argument("--log", default="literature/search_log.json")
    f = sub.add_parser("fix-dois"); f.add_argument("--candidates", default="literature/candidates.csv")
    for p in (s, b):
        p.add_argument("--out", default="literature/candidates.csv"); p.add_argument("--log", default="literature/search_log.json")
    for p in (s, b, f):
        p.add_argument("--no-net", action="store_true"); p.add_argument("--from-dir", default="", help="read saved API responses from this folder instead of the network")
    a = ap.parse_args()
    {"search": cmd_search, "snowball": cmd_snowball, "triage": cmd_triage, "fix-dois": cmd_fix_dois}[a.cmd](a)


if __name__ == "__main__":
    main()
