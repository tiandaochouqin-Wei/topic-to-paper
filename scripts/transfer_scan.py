# -*- coding: utf-8 -*-
"""P1 — method-transfer scan. Finds recent methods OUTSIDE the target field whose *problem structure* matches, then tests
whether moving them in is non-trivial. Companion to gap_map.md (inside-field gaps). Run by Claude.

  recent  python transfer_scan.py recent --query "<problem-structure words, NO domain words>" [--db literature/lit_index.sqlite]
                 [--years 2025-2026] [--venues NeurIPS,ICML,ICLR,CVPR,ICCV,ECCV,TPAMI,Nature,Science] [--arxiv cs.LG,cs.CV,stat.ML]
                 [--months 18] [--out literature/transfer_hits.csv] [--no-net]
          -> three sources: local FTS index (top venues, last 2 years), arXiv API (last N months, listed as NOT peer-reviewed),
             OpenAlex (last 2 years). One CSV, column 'source' says where it came from and 'reviewed' says accepted or not.
  count   python transfer_scan.py count --scan literature/transfer_scan.md --domain "<target-domain words>" [--db ...] [--years 2024-2026]
          -> for every candidate row fills the 'domain_count' column: OpenAlex hits for "<method> AND <domain words>" + local index hits.
             This is the mechanical test 1: the method has (almost) never been applied to the target domain.
  check   python transfer_scan.py check [--scan literature/transfer_scan.md] [--gap literature/gap_map.md] [--state research-state.yaml]
          -> G1 half: transfer_scan.md has >= 5 candidates with all 7 columns; >= 1 candidate passes the three tests
             (domain_count <= 2, correspondence written, failure point written) unless gap_map verdict is no-go;
             gap_map.md has sections 评测盲区 / 邻域默认假设 / 判定 (verdict go|no-go, claim_source, reason).

Why three tests (see references/gates.md G1): test 1 is mechanical; tests 2 and 3 are written by Claude after reading the paper.
"X applied to Y" with no failure point is what reviewers call incremental — the failure point IS the claim.
"""
import argparse, csv, io, os, re, sys, json, datetime, sqlite3, urllib.parse, urllib.request, time, xml.etree.ElementTree as ET
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
UA = {"User-Agent": "topic-to-paper/2.5 (mailto:" + os.environ.get("T2P_CONTACT_EMAIL", "topic-to-paper@example.org") + ")"}   # set T2P_CONTACT_EMAIL for the OpenAlex/CrossRef polite pool
FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {msg}")

def http(url, tries=3):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf-8", "replace")
        except Exception as ex:
            if i == tries - 1: print(f"  net fail {url[:80]}… {ex}"); return ""
            time.sleep(30 if "429" in str(ex) else 2 + 3 * i)

# ------------------------------------------------------------------ recent
def local_recent(db, query, years, venues):
    import lit_scout
    con = sqlite3.connect(db); cur = con.cursor()
    fq = " OR ".join("(" + lit_scout.fts_query(sub.strip()).replace(" OR ", " AND ") + ")" for sub in query.split(",") if sub.strip())   # each phrase = AND of its words; phrases OR-ed
    rows = cur.execute("SELECT venue, year, title, abstract, doi, local_path FROM papers WHERE papers MATCH ? ORDER BY bm25(papers) LIMIT 5000", (fq,)).fetchall()
    out = []
    for v, y, t, ab, doi, p in rows:
        try: yi = int(y)
        except Exception: continue
        if yi < years[0] or yi > years[1]: continue
        if venues and v not in venues: continue
        if not any(lit_scout.strict_match(sub.strip(), t, ab) for sub in query.split(",") if sub.strip()): continue
        out.append({"source": "local", "venue": v, "year": yi, "title": t, "id": doi or "", "reviewed": "yes", "local_path": p or ""})
    return out

def arxiv_recent(query, cats, months, max_results=200):
    phrases = [p.strip() for p in query.split(",") if p.strip()]
    q = "(" + " OR ".join(f'all:"{p}"' if " " in p else f"all:{p}" for p in phrases) + ")"
    if cats: q += " AND (" + " OR ".join(f"cat:{c}" for c in cats) + ")"
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": q, "sortBy": "submittedDate", "sortOrder": "descending", "max_results": max_results})
    x = http(url)
    if not x: return []
    ns = {"a": "http://www.w3.org/2005/Atom"}; cutoff = datetime.date.today() - datetime.timedelta(days=30 * months)
    out = []
    for e in ET.fromstring(x).findall("a:entry", ns):
        pub = e.findtext("a:published", "", ns)[:10]
        try: d = datetime.date.fromisoformat(pub)
        except Exception: continue
        if d < cutoff: continue
        aid = e.findtext("a:id", "", ns).rsplit("/", 1)[-1]; comment = e.findtext("{http://arxiv.org/schemas/atom}comment", "") or ""
        acc = re.search(r"\b(accepted|to appear|published|camera[- ]ready)\b.*?\b(NeurIPS|ICML|ICLR|CVPR|ICCV|ECCV|AAAI|TPAMI|Nature|Science|TGRS|MICCAI|KDD|ACL|EMNLP)\b", comment, re.I)
        out.append({"source": "arxiv", "venue": acc.group(2) if acc else "arXiv", "year": d.year, "title": re.sub(r"\s+", " ", e.findtext("a:title", "", ns)).strip(), "id": aid, "reviewed": "yes" if acc else "NO (preprint)", "local_path": ""})
    return out

def openalex_recent(query, years, per_page=50):
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode({"search": query.replace(",", " "), "filter": f"publication_year:{years[0]}-{years[1]},type:article", "per-page": per_page, "sort": "cited_by_count:desc", "mailto": os.environ.get("T2P_CONTACT_EMAIL", "topic-to-paper@example.org")})
    x = http(url)
    if not x: return []
    out = []
    for w in json.loads(x).get("results", []):
        src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        out.append({"source": "openalex", "venue": src[:60], "year": w.get("publication_year"), "title": w.get("title") or "", "id": (w.get("doi") or w.get("id") or "").replace("https://doi.org/", ""), "reviewed": "yes" if src and "arxiv" not in src.lower() else "NO (preprint)", "local_path": ""})
    return out

def recent(a):
    years = tuple(int(x) for x in a.years.split("-")); venues = set(a.venues.split(",")) if a.venues else None
    hits = []
    if a.db and os.path.exists(a.db):
        h = local_recent(a.db, a.query, years, venues); print(f"local index: {len(h)} strict hits in {years} at {sorted(venues) if venues else 'all venues'}"); hits += h
    if not a.no_net:
        h = arxiv_recent(a.query, a.arxiv.split(",") if a.arxiv else [], a.months); print(f"arXiv ({a.arxiv}, last {a.months} months): {len(h)}  [{sum(1 for r in h if r['reviewed']=='yes')} with accepted-to comment]"); hits += h
        h = openalex_recent(a.query, years); print(f"OpenAlex {years}: {len(h)}"); hits += h
    seen = set(); uniq = []
    for r in hits:
        k = re.sub(r"[^a-z0-9]", "", r["title"].lower())[:70]
        if k in seen: continue
        seen.add(k); uniq.append(r)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source", "venue", "year", "reviewed", "title", "id", "local_path"]); w.writeheader(); w.writerows(uniq)
    print(f"{len(uniq)} unique -> {a.out}")
    for r in uniq[:40]: print(f"  {r['source']:8s} {str(r['venue'])[:14]:14s} {r['year']}  {'rev' if r['reviewed']=='yes' else 'PRE'}  {r['title'][:95]}")
    if len(uniq) > 40: print(f"  … {len(uniq)-40} more in the CSV")

# ------------------------------------------------------------------ transfer_scan.md parsing
COLS = ["方法", "来源", "问题结构", "对应物", "域内计数", "失效点", "判定"]
def parse_scan(md):
    """-> list of dict rows from the first markdown table whose header contains 方法 and 失效点"""
    lines = md.splitlines(); rows = []; hdr = None; done = False
    for ln in lines:
        if done: break
        if not ln.strip().startswith("|"):
            if hdr and rows: done = True
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if hdr is None:
            if "方法" in "".join(cells) and "失效点" in "".join(cells): hdr = cells
            continue
        if set(ln.replace("|", "").strip()) <= set("-: "): continue
        if len(cells) < len(hdr): cells += [""] * (len(hdr) - len(cells))
        rows.append(dict(zip(hdr, cells)))
    return hdr or [], rows

def col(r, name):
    for k, v in r.items():
        if name in k: return v
    return ""

EMPTY = re.compile(r"^\s*(|—|-|–|n/?a|none|未知|无|tbd|\?)\s*$", re.I)

def count(a):
    md = io.open(a.scan, encoding="utf-8").read(); hdr, rows = parse_scan(md)
    if not rows: say("FAIL", f"{a.scan} 没有候选表"); sys.exit(1)
    years = tuple(int(x) for x in a.years.split("-"))
    import lit_scout
    con = sqlite3.connect(a.db).cursor() if a.db and os.path.exists(a.db) else None
    new = {}
    for r in rows:
        m = col(r, "方法");
        if not m: continue
        q = re.sub(r"\s*[\(（][^\)）]*[\)）]", "", m).strip() + " " + a.domain   # drop "(2403.15356)"-style IDs from the query
        time.sleep(1.5)
        # source chain: OpenAlex -> Semantic Scholar bulk -> arXiv; first one that answers wins (OpenAlex free credits run out daily: Retry-After ~4 h)
        n_oa = -1; src = "?"
        if not a.no_net:
            url = "https://api.openalex.org/works?" + urllib.parse.urlencode({"filter": f"title_and_abstract.search:{q},publication_year:{years[0]}-{years[1]}", "per-page": 1, "mailto": os.environ.get("T2P_CONTACT_EMAIL", "topic-to-paper@example.org")})
            x = http(url, tries=1)
            try: n_oa = int(json.loads(x).get("meta", {}).get("count")) if x else -1
            except Exception: n_oa = -1
            src = "oa" if n_oa >= 0 else src
            if n_oa < 0:
                time.sleep(3)
                x = http("https://api.semanticscholar.org/graph/v1/paper/search/bulk?" + urllib.parse.urlencode({"query": q, "year": f"{years[0]}-{years[1]}", "fields": "title", "limit": 1}), tries=2)
                try: n_oa = int(json.loads(x)["total"]); src = "s2"
                except Exception: n_oa = -1
            if n_oa < 0:
                time.sleep(3)
                words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", q)]
                x = http("https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": " AND ".join(f"all:{w}" for w in words), "max_results": 0}), tries=2)
                mm = re.search(r"totalResults[^>]*>(\d+)<", x or "")   # not `m`: that is the method name
                if mm: n_oa = int(mm.group(1)); src = "arxiv"
        n_oa = n_oa if isinstance(n_oa, int) else -1          # any source may hand back null
        n_loc = 0
        if con is not None:
            try:
                hits = con.execute("SELECT year, title, abstract FROM papers WHERE papers MATCH ? LIMIT 2000", (lit_scout.fts_query(q),)).fetchall()
                n_loc = sum(1 for y, t, ab in hits if str(y).isdigit() and years[0] <= int(y) <= years[1] and lit_scout.strict_match(q, t, ab))
            except Exception: pass
        new[m] = f"{src}:{n_oa if n_oa >= 0 else '?'}+local:{n_loc}"
        print(f"  {m:28s} {src} {n_oa:>4}  local {n_loc:>3}   ({q})")
    # rewrite the 域内计数 cells in place
    out = []; ci = next((i for i, h in enumerate(hdr) if "计数" in h), None)
    for ln in md.splitlines():
        if ln.strip().startswith("|") and ci is not None:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            m = next((cells[i] for i, h in enumerate(hdr) if "方法" in h and i < len(cells)), "")
            if m in new and len(cells) > ci: cells[ci] = new[m]; ln = "| " + " | ".join(cells) + " |"
        out.append(ln)
    io.open(a.scan, "w", encoding="utf-8").write("\n".join(out) + ("\n" if md.endswith("\n") else ""))
    print(f"{len(new)} rows updated in {a.scan} (format: <source>:N+local:N, both {years[0]}–{years[1]}; source = oa | s2 | arxiv, ? = all unreachable)")

def first_int(s):
    m = re.search(r"\d+", s or ""); return int(m.group()) if m else None

def passes(r):
    c = col(r, "计数"); n2 = [int(x) for x in re.findall(r"\d+", c)]
    if "?" in c or not n2: return False                      # OpenAlex not reached -> mechanical test not done
    if re.search(r"淘汰", col(r, "判定")): return False        # author already ruled it out
    return sum(n2) <= 2 and not EMPTY.match(col(r, "对应物")) and not EMPTY.match(col(r, "失效点"))

def section(md, name):
    m = re.search(r"^(#{1,4})\s*\d*\.?\s*" + re.escape(name) + r"\b.*?$", md, re.M | re.I)
    if not m: return None
    depth = len(m.group(1)); rest = md[m.end():]
    nxt = re.search(r"^#{1,%d}\s" % depth, rest, re.M)
    return rest[:nxt.start()] if nxt else rest

def check(a):
    ok = True
    gap = io.open(a.gap, encoding="utf-8").read() if os.path.exists(a.gap) else ""
    if not gap: say("FAIL", f"{a.gap} 不存在");
    verdict = ""; src = ""
    if gap:
        for s in ("评测盲区", "邻域默认假设"):
            t = section(gap, s)
            if t is None: say("FAIL", f"gap_map 缺 `## {s}` 小节（答不出就写\"未知：试过什么\"，但小节必须在）")
            elif len(t.strip()) < 10: say("FAIL", f"gap_map `## {s}` 为空")
            else: say("PASS", f"gap_map `{s}` 已答（{len(t.strip())} 字）")
        t = section(gap, "判定") or ""
        mv = re.search(r"verdict\s*[:：]\s*(go|no-go|nogo|no_go)", t, re.I); ms = re.search(r"claim_source\s*[:：]\s*(gap#\w+|transfer#T?\d+)", t, re.I); mr = re.search(r"reason\s*[:：]\s*(\S.{10,})", t, re.I)
        if not mv: say("FAIL", "gap_map `## 判定` 缺 verdict: go | no-go —— P1 允许判定\"不做\"，但必须写出来")
        else:
            verdict = "no-go" if mv.group(1).lower() != "go" else "go"
            if not mr: say("FAIL", "gap_map `## 判定` 缺 reason:（≥10 字）")
            if verdict == "go" and not ms: say("FAIL", "verdict go 但缺 claim_source: gap#X 或 transfer#Tn —— 主张来自哪条空白必须可追溯")
            if ms: src = ms.group(1)
            if verdict == "no-go": say("PASS", f"P1 判定 no-go：{(mr.group(1) if mr else '')[:80]} —— 这是合法出口，不进 P2")
            elif ms and mr: say("PASS", f"P1 判定 go，主张来源 {src}")
            if verdict == "go":
                worth = {k: (re.search(k + r"\s*[:：]\s*(\S.*)", t) or [None, ""])[1].strip() for k in ("重要性", "新颖性", "可验证性", "可解释性", "可推广性")}
                miss = [k for k, v in worth.items() if not v or v.startswith("<")]
                weak = [k for k, v in worth.items() if re.match(r"弱", v)]
                if miss: say("FAIL", f"gap_map `## 判定` 缺值不值得做的五行: {miss}（答不出写\"弱\"）")
                elif len(weak) >= 3: say("FAIL", f"五项里 {len(weak)} 项为弱 {weak}：按规则应判 no-go 或降为辅助改进")
                else: say("PASS", f"值不值得做五项已答" + (f"，弱项 {weak}" if weak else ""))
    pt = os.path.join(os.path.dirname(a.gap) or ".", "problem_table.csv")
    if not os.path.exists(pt): say("FAIL", f"{pt} 不存在 —— 问题导向文献表是 P1 第一产物（模板 templates/problem_table.csv，`problem_table.py check`）")
    else:
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(HERE, "problem_table.py"), "check", "--table", pt], capture_output=True, text=True, encoding="utf-8")
        for ln in r.stdout.splitlines():
            if ln.startswith("[FAIL]"): say("FAIL", "problem_table: " + ln[7:])
            elif ln.startswith("[PASS]") and "共享" in ln: say("PASS", "problem_table: " + ln[7:])
        if r.returncode == 0 and not any(l.startswith("[FAIL]") for l in r.stdout.splitlines()): say("PASS", "problem_table check 全绿")
    scan = io.open(a.scan, encoding="utf-8").read() if os.path.exists(a.scan) else ""
    if not scan: say("FAIL", f"{a.scan} 不存在 —— 领域外方法扫描是 P1 的第二个必产物");
    if scan:
        hdr, rows = parse_scan(scan)
        missing = [c for c in COLS if not any(c in h for h in hdr)]
        if missing: say("FAIL", f"transfer_scan 表缺列 {missing}（需要 {COLS}）")
        rows = [r for r in rows if col(r, "方法")]
        if len(rows) < 5: say("FAIL", f"transfer_scan 只有 {len(rows)} 个候选，至少 5 个（扫过并淘汰的也算，淘汰理由写在失效点或判定列）")
        else: say("PASS", f"transfer_scan {len(rows)} 个候选")
        nocount = [col(r, "方法") for r in rows if first_int(col(r, "计数")) is None]
        if nocount: say("FAIL", f"域内计数未填（跑 `transfer_scan.py count`）: {nocount[:5]}")
        unk = [col(r, "方法") for r in rows if "?" in col(r, "计数")]
        if unk: say("FAIL", f"域内计数的 OpenAlex 部分未取到（429/断网），重跑 `count`: {unk[:5]}")
        pre = [col(r, "方法") for r in rows if re.search(r"arxiv|preprint|未录用", col(r, "来源"), re.I) and not re.search(r"NeurIPS|ICML|ICLR|CVPR|ICCV|ECCV|AAAI|TPAMI|Nature|Science|TGRS|MICCAI|accepted", col(r, "来源"), re.I)]
        if pre: say("INFO", f"{len(pre)} 个候选仅为预印本（未同行评审）: {pre[:5]} —— 进 prereg 时在 §5 注明")
        good = [col(r, "方法") for r in rows if passes(r)]
        if good: say("PASS", f"{len(good)} 个候选过三道判定（域内计数≤2 + 对应物 + 失效点）: {good}")
        elif verdict == "no-go": say("INFO", "无候选过三道判定，与 no-go 判定一致")
        else: say("FAIL", "没有候选过三道判定：要么补读论文写出对应物/失效点，要么 gap_map 判定改 no-go")
        if verdict == "go" and src.lower().startswith("transfer#"):
            tid = src.split("#", 1)[1].upper(); tid = tid if tid.startswith("T") else "T" + tid
            hit = [r for r in rows if col(r, "#").upper() == tid or col(r, "方法").upper() == tid]
            if not hit: say("FAIL", f"claim_source {src} 在 transfer_scan 表里找不到行 #{tid}")
            elif not passes(hit[0]): say("FAIL", f"claim_source {src}（{col(hit[0], '方法')}）没有过三道判定，不能作为主张来源")
            else: say("PASS", f"主张来源 {src} = {col(hit[0], '方法')}，三道判定通过")
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recent"); r.add_argument("--query", required=True, help="problem-structure phrases, comma-separated, NO domain words"); r.add_argument("--db", default="literature/lit_index.sqlite")
    r.add_argument("--years", default=f"{datetime.date.today().year-1}-{datetime.date.today().year}"); r.add_argument("--venues", default="NeurIPS,ICML,ICLR,CVPR,ICCV,ECCV,TPAMI,IJCV,TIP,Nature,Science")
    r.add_argument("--arxiv", default="cs.LG,cs.CV,stat.ML"); r.add_argument("--months", type=int, default=18); r.add_argument("--out", default="literature/transfer_hits.csv"); r.add_argument("--no-net", action="store_true")
    c = sub.add_parser("count"); c.add_argument("--scan", default="literature/transfer_scan.md"); c.add_argument("--domain", required=True); c.add_argument("--db", default="literature/lit_index.sqlite"); c.add_argument("--years", default=f"{datetime.date.today().year-2}-{datetime.date.today().year}"); c.add_argument("--no-net", action="store_true")
    k = sub.add_parser("check"); k.add_argument("--scan", default="literature/transfer_scan.md"); k.add_argument("--gap", default="literature/gap_map.md"); k.add_argument("--state", default="research-state.yaml")
    a = ap.parse_args()
    {"recent": recent, "count": count, "check": check}[a.cmd](a)

if __name__ == "__main__":
    main()
