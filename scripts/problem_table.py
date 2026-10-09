# -*- coding: utf-8 -*-
"""P1 — problem-oriented literature table and recurring-gap count. Run by Claude.

  python problem_table.py recurring [--table literature/problem_table.csv] [--min 2]
      -> for the four gap columns (hidden_assumption, failure_scene, missing_experiment, limitation) tokenises each cell on ';'
         and counts how many DISTINCT papers share each gap phrase (exact after normalisation). Prints gaps shared by >= --min papers
         with the paper tags. A gap shared by 3+ papers beats any single paper's Future Work.
  python problem_table.py check [--table ...] [--min-rows 8]
      -> every row has tag, question, finding; >= 60 % of rows have hidden_assumption AND failure_scene AND missing_experiment
         filled (or the literal 未读全文); rows marked 未读全文 are excluded from the recurring count.

Columns (templates/problem_table.csv): tag, year, venue, question, method, finding, hidden_assumption, failure_scene, limitation,
missing_experiment, contradicts, followup_question, potential_innovation, read_depth (全文|摘要|未读全文).
Gap phrases: short, reusable, ';'-separated — "no held-out sensor; time split only" — so the same phrase recurs across rows.
"""
import argparse, csv, io, os, re, sys, collections
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

GAP_COLS = ["hidden_assumption", "failure_scene", "missing_experiment", "limitation"]
REQ = ["tag", "question", "finding"]
FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {msg}")

def norm(s): return re.sub(r"[\s\-_]+", " ", s.strip().lower().rstrip("。.;；"))

def rows_of(p):
    if not os.path.exists(p): return None
    return [r for r in csv.DictReader(open(p, encoding="utf-8-sig")) if r.get("tag", "").strip()]

def recurring(a):
    rows = rows_of(a.table)
    if rows is None: say("FAIL", f"{a.table} 不存在"); sys.exit(1)
    used = [r for r in rows if "未读全文" not in r.get("read_depth", "")]
    print(f"{len(rows)} rows, {len(used)} with full/abstract reading")
    any_hit = False
    for c in GAP_COLS:
        cnt = collections.defaultdict(set)
        for r in used:
            for ph in re.split(r"[;；]", r.get(c, "") or ""):
                if ph.strip(): cnt[norm(ph)].add(r["tag"])
        hits = sorted(((len(v), k, sorted(v)) for k, v in cnt.items() if len(v) >= a.min), reverse=True)
        if hits:
            any_hit = True; print(f"\n== {c}: {len(hits)} gaps shared by >= {a.min} papers")
            for n, k, tags in hits: print(f"  {n:2d}×  {k}   [{', '.join(tags)}]")
    if not any_hit: print(f"\nno gap phrase shared by >= {a.min} papers — phrases too specific? reuse the same wording across rows")

def check(a):
    rows = rows_of(a.table)
    if rows is None: say("FAIL", f"{a.table} 不存在（P1 问题表，模板 templates/problem_table.csv）"); sys.exit(1)
    hdr = next(csv.reader(open(a.table, encoding="utf-8-sig")), [])   # header even when the table is still empty
    miss = [c for c in REQ + GAP_COLS + ["read_depth"] if c not in hdr]
    if miss: say("FAIL", f"problem_table 缺列 {miss}")
    if len(rows) < a.min_rows: say("FAIL", f"problem_table 只有 {len(rows)} 行，至少 {a.min_rows}（核心文献集）")
    else: say("PASS", f"problem_table {len(rows)} 行")
    bad = [r["tag"] for r in rows if any(not (r.get(c) or "").strip() for c in REQ)]
    if bad: say("FAIL", f"{len(bad)} 行缺 tag/question/finding: {bad[:5]}")
    full = [r for r in rows if "未读全文" not in (r.get("read_depth") or "")]
    filled = [r for r in full if all((r.get(c) or "").strip() for c in ("hidden_assumption", "failure_scene", "missing_experiment"))]
    frac = len(filled) / len(full) if full else 0
    if frac < 0.6: say("FAIL", f"已读行里只有 {len(filled)}/{len(full)} 填齐 hidden_assumption+failure_scene+missing_experiment（要 ≥60%）—— 读论文时记\"哪里不够\"，不是\"做了什么\"")
    else: say("PASS", f"{len(filled)}/{len(full)} 已读行填齐三个缺口列")
    unread = [r["tag"] for r in rows if "未读全文" in (r.get("read_depth") or "")]
    if unread: say("INFO", f"{len(unread)} 行标未读全文，不计入反复缺口: {unread[:6]}")
    # recurring summary
    cnt = collections.defaultdict(set)
    for r in full:
        for c in GAP_COLS:
            for ph in re.split(r"[;；]", r.get(c, "") or ""):
                if ph.strip(): cnt[(c, norm(ph))].add(r["tag"])
    rec = [(len(v), c, k) for (c, k), v in cnt.items() if len(v) >= 2]
    if rec: say("PASS", f"{len(rec)} 条缺口被 ≥2 篇共享（最高 {max(rec)[0]}×：{max(rec)[2]}）—— gap_map 的候选主张应来自这些")
    else: say("WARN", "没有缺口短语被 ≥2 篇共享：要么语料太散，要么短语写法不统一（同一缺口用同一句话）")
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recurring"); r.add_argument("--table", default="literature/problem_table.csv"); r.add_argument("--min", type=int, default=2)
    c = sub.add_parser("check"); c.add_argument("--table", default="literature/problem_table.csv"); c.add_argument("--min-rows", type=int, default=8)
    a = ap.parse_args(); {"recurring": recurring, "check": check}[a.cmd](a)

if __name__ == "__main__":
    main()
