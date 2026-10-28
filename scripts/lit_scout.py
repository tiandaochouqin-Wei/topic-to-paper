# -*- coding: utf-8 -*-
"""Local literature scout over the user's paper corpus metadata (no network).

  build   python lit_scout.py build  <papers_root> <index.sqlite>
  scout   python lit_scout.py scout  <index.sqlite> "<claim or keywords>" [--years 2024-2026] [--venues CVPR,NeurIPS] [--top 40]
  trend   python lit_scout.py trend  <index.sqlite> "<keywords>"            per-year counts, by venue group

build merges metadata/index.csv (conferences: venue,year,title,local_path), metadata/journals.csv (TIP/TPAMI/IJCV with abstracts)
and nature/metadata/journals.csv (Nature/Science/PNAS family with abstracts) into one SQLite FTS5 table.
scout ranks by BM25 over title+abstract, prints per-year counts (saturation signal), top hits with local PDF path when present,
and the 18-month count that P1/G1 of topic-to-paper asks for."""
import sys, os, re, csv, sqlite3, argparse, collections, datetime
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

csv.field_size_limit(10**9)

def build(root, db, progress=0):
    """progress > 0: print a line every <progress> rows (the metadata sits on a network drive in practice and the build takes minutes)"""
    if os.path.exists(db): os.remove(db)
    con = sqlite3.connect(db); cur = con.cursor()
    cur.execute("CREATE VIRTUAL TABLE papers USING fts5(venue, year UNINDEXED, title, abstract, doi UNINDEXED, local_path UNINDEXED, cited_by UNINDEXED, tokenize='porter unicode61')")
    n = 0
    def add(venue, year, title, abstract, doi, path, cited):
        nonlocal n
        if not title: return
        cur.execute("INSERT INTO papers VALUES (?,?,?,?,?,?,?)", (venue, str(year or ""), title.strip().replace("-", " "), (abstract or "").strip().replace("-", " "), doi or "", path or "", str(cited or "")))
        n += 1
        if progress and n % progress == 0: print(f"  ... {n} rows indexed", flush=True)
    seen = set()
    f = os.path.join(root, "metadata", "index.csv")
    if os.path.exists(f):
        for r in csv.DictReader(open(f, encoding="utf-8", errors="replace")):
            key = (r.get("venue"), r.get("title", "").lower()[:80])
            if key in seen: continue
            seen.add(key); add(r.get("venue"), r.get("year"), r.get("title"), "", "", r.get("local_path"), "")
    for f in (os.path.join(root, "metadata", "journals.csv"), os.path.join(root, "nature", "metadata", "journals.csv")):
        if not os.path.exists(f): continue
        for r in csv.DictReader(open(f, encoding="utf-8", errors="replace")):
            key = (r.get("journal"), r.get("title", "").lower()[:80])
            if key in seen: continue
            seen.add(key); add(r.get("journal"), r.get("year"), r.get("title"), r.get("abstract"), r.get("doi"), r.get("local_path"), r.get("cited_by"))
    con.commit(); con.close()
    print(f"indexed {n} papers -> {db}")

GROUP = {"CVPR": "cv", "ICCV": "cv", "ECCV": "cv", "WACV": "cv", "TIP": "cv", "TPAMI": "cv", "IJCV": "cv", "MM": "cv",
         "NeurIPS": "ml", "ICML": "ml", "AAAI": "ml", "IJCAI": "ml", "MICCAI": "medimg"}

STOP = {"the", "and", "for", "with", "from", "using", "based", "via", "towards", "toward", "deep", "learning", "neural",
        "network", "networks", "model", "models", "approach", "method", "methods", "novel", "new", "framework", "data"}

def terms(q):
    """content terms of a free-text claim: quoted phrases kept whole, hyphens split, generic ML words dropped."""
    phrases = [p.lower() for p in re.findall(r'"([^"]+)"', q)]
    rest = re.sub(r'"[^"]+"', " ", q).replace("-", " ")
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", rest) if w.lower() not in STOP]
    return phrases, words

def fts_query(q):
    phrases, words = terms(q)
    parts = [f'"{p.replace(chr(34), "")}"' for p in phrases] + [f'"{w}"' for w in words]   # quote every token: FTS5 treats bare hyphens/colons as syntax
    return " OR ".join(parts) if parts else '"' + q.replace('"', "") + '"'

def strict_match(q, title, abstract):
    """saturation filter: every quoted phrase present AND all content words present (not 70 %): with generic words removed,
    'all' is the right bar — a 2-word query like 'satellite nowcasting' must have both."""
    phrases, words = terms(q)
    t = (title + " " + abstract).lower().replace("-", " ")
    return all(p.replace("-", " ") in t for p in phrases) and all(w in t for w in words)

def search(db, q, limit=20000):
    """BM25 hits for a free-text query: [(venue, year, title, abstract, doi, local_path, cited_by, bm25)], best first (bm25 is negative: lower = better)"""
    con = sqlite3.connect(db)
    try: return con.execute("SELECT venue, year, title, abstract, doi, local_path, cited_by, bm25(papers) AS s FROM papers WHERE papers MATCH ? ORDER BY s LIMIT ?", (fts_query(q), limit)).fetchall()
    finally: con.close()

def scout(db, q, years, venues, top):
    con = sqlite3.connect(db); cur = con.cursor()
    fq = fts_query(q)
    rows = search(db, q)
    if years:
        lo, hi = years
        rows = [r for r in rows if r[1].isdigit() and lo <= int(r[1]) <= hi]
    if venues:
        rows = [r for r in rows if r[0] in venues]
    # all-words-in-title-or-abstract filter for the saturation count (stricter than BM25 OR)
    strict_rows = [r for r in rows if strict_match(q, r[2], r[3])]
    now = datetime.date.today()
    cut18 = now.year - 2 if now.month > 6 else now.year - 1   # whole-year proxy for "last 18 months"
    n18 = sum(1 for r in strict_rows if r[1].isdigit() and int(r[1]) >= cut18)
    print(f"query: {q}\nFTS: {fq}\nBM25 hits {len(rows)} | strict (≥70% words + all phrases) {len(strict_rows)} | since {cut18}: {n18}\n")
    yc = collections.Counter(); gc = collections.Counter()
    for r in strict_rows:
        yc[r[1]] += 1; gc[(GROUP.get(r[0], "nature" if r[0] not in GROUP else r[0]), r[1])] += 1
    print("per year (strict):", " ".join(f"{y}:{c}" for y, c in sorted(yc.items())))
    for g in ("cv", "ml", "medimg", "nature"):
        ys = {y: c for (gg, y), c in gc.items() if gg == g}
        if ys: print(f"  {g:7s}", " ".join(f"{y}:{c}" for y, c in sorted(ys.items())))
    print(f"\ntop {top} (BM25):")
    for r in rows[:top]:
        path = r[5] if r[5] and os.path.exists(r[5]) else ("[pdf]" if r[5] else "")
        print(f"  {r[0]:10s} {r[1]} {r[2][:95]}{'  cited=' + r[6] if r[6] else ''}{'  ' + path if path else ''}")
    con.close()

def trend(db, q):
    con = sqlite3.connect(db); cur = con.cursor()
    rows = cur.execute("SELECT venue, year, title, abstract FROM papers WHERE papers MATCH ? LIMIT 50000", (fts_query(q),)).fetchall()
    c = collections.Counter()
    for v, y, t, a in rows:
        if strict_match(q, t, a):
            c[(GROUP.get(v, "nature"), y)] += 1
    years = sorted({y for _, y in c})
    print("group   " + " ".join(f"{y:>6}" for y in years))
    for g in ("cv", "ml", "medimg", "nature"):
        print(f"{g:7s} " + " ".join(f"{c.get((g, y), 0):6d}" for y in years))
    con.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("root"); b.add_argument("db")
    s = sub.add_parser("scout"); s.add_argument("db"); s.add_argument("query"); s.add_argument("--years", default=""); s.add_argument("--venues", default=""); s.add_argument("--top", type=int, default=30)
    t = sub.add_parser("trend"); t.add_argument("db"); t.add_argument("query")
    a = ap.parse_args()
    if a.cmd == "build": build(a.root, a.db)
    elif a.cmd == "scout":
        yrs = tuple(int(x) for x in a.years.split("-")) if a.years else None
        scout(a.db, a.query, yrs, set(a.venues.split(",")) if a.venues else None, a.top)
    else: trend(a.db, a.query)
