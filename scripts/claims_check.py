# -*- coding: utf-8 -*-
"""G6e — the claim layer: every headline sentence of the manuscript is a row of paper/claims.csv, and every row is computed
from the result files, not asserted. Companion to shape_check (G6c), which can only tell that a "Here we show" sentence or a
contribution list exists, not that what it says is backed by a number. Run by Claude.

  python claims_check.py [--project .] [--claims paper/claims.csv] [--manuscript paper/manuscript.md] [--state research-state.yaml] [--family cs_conf|cs_journal|nature]

paper/claims.csv (templates/claims.csv):
  claim_id, statement, dataset, metric_convention, evidence_file, evidence_key, expected, table_or_figure, scope_words, verified
  evidence_key — how to compute the claim from evidence_file (csv under results/ unless stated):
    rel:<metric>:<a>:<b>     100 × (mean_a − mean_b) / mean_b   over rows whose group_key (state.results.group_key) or `ablation` is a / b
    delta:<metric>:<a>:<b>   mean_a − mean_b                      (a, b looked up in evidence_file, then in results.main_table / ablation_table)
    z:<metric>:<a>           |mean_a − mean_ref| / (σ_ref·√2)     ref = state.results.reference_method, σ_ref from its seeds in main_table — the
                                                                 ablation resolution of ablation_plan.py resolve; z < 2 = not resolvable
    mean:<metric>:<a>        mean_a
    <col>=<val>[|<col>=<val>],<col>   one cell of a csv (numbers.csv style);  a.b.0.c   dotted path into a json
  expected — what the computed value must satisfy:  <x  <=x  >x  >=x  ==x  x±t  x (equal after rounding to x's decimals)  +  −  (sign only)
  A row with no evidence_key is qualitative: WARN, never PASS — the review seats must look at it by hand.

Checks (exit = #FAIL):
  rows      statement non-empty; evidence_file exists; evidence_key computes; expected holds; numbers in the statement appear in the manuscript
  where     the statement is made in the section that holds its table_or_figure caption (token overlap ≥ 0.5 or a shared number)
  headline  nature: the "Here we show …" sentence maps to a claims row (FAIL) and each sentence-style Results subheading maps to one (WARN);
            cs: each contribution bullet maps to a claims row (FAIL); the abstract shares at least one number with a claims row (WARN)
  scope     every strong-scope sentence of the body (gate_check.SCOPE_STRONG: "the first to", "outperforms all", "new state-of-the-art" …)
            maps to a claims row whose scope_words are non-empty (FAIL) — the "which table?" question is answered before a reviewer asks it
  prereg    a rel: claim below the minimum improvement of prereg §7 is WARN: the §8 fallback applies and the text must say so
"""
import argparse, csv, io, json, math, os, re, statistics, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] claims: {msg}")

STOP = set("the a an of to in on for and or with by from as is are be that this we our it its at under over than into via using use used based across between per each all any not no non new novel method methods approach model models result results paper work study data set sets while when which who whose where because so than then also both only very more most less".split())
def stem(w): return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w
def toks(s):
    return [stem(w) for w in re.findall(r"[A-Za-z][A-Za-z0-9]+|[一-鿿]{2,}", (s or "").lower().replace("-", " ").replace("_", " ")) if len(w) > 2 and w not in STOP]
def nums(s): return {n for n in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", s or "") if not re.fullmatch(r"(19|20)\d\d", n) and ("." in n or int(n) >= 10)}
def maps(statement, text, thr=0.5):
    """statement is 'in' text: ≥ thr of its content tokens occur, or they share a number"""
    st = list(dict.fromkeys(toks(statement)))
    if not st: return False
    t = text.lower().replace("-", " ")
    if nums(statement) & nums(text): return True
    return sum(1 for w in st if w in t) / len(st) >= thr

def section_of(md, pos):
    """body of the innermost heading that contains character offset pos"""
    hs = [(m.start(), len(m.group(1))) for m in re.finditer(r"^(#{1,4})\s+\S", md, re.M)]
    before = [(s, lv) for s, lv in hs if s <= pos]
    if not before: return md
    s, lv = before[-1]
    nxt = next((s2 for s2, lv2 in hs if s2 > s and lv2 <= lv), len(md))
    return md[s:nxt]

def read_rows(p):
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    return [r for r in rows if (r.get("claim_id") or "").strip() and (r.get("statement") or "").strip()]

# ------------------------------------------------------------------ evidence
def load_table(root, rel):
    p = os.path.join(root, rel)
    if not os.path.exists(p): return None
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))

def group_vals(rows, name, metric, gk):
    out = []
    for r in rows or []:
        if (r.get(gk) == name or r.get("ablation") == name or r.get("run_id") == name) and (r.get(metric) or "").strip() != "":
            try: out.append(float(r[metric]))
            except ValueError: pass
    return out

def vals_anywhere(root, res, ev_rows, name, metric, gk):
    v = group_vals(ev_rows, name, metric, gk)
    if v: return v
    for key in ("main_table", "ablation_table"):
        v = group_vals(load_table(root, res.get(key, "")), name, metric, gk)
        if v: return v
    return []

def compute(root, res, ev_file, key):
    """-> float, or raise with a reason"""
    gk = res.get("group_key", "method")
    fp = os.path.join(root, ev_file)
    if key.startswith(("rel:", "delta:", "z:", "mean:")):
        parts = key.split(":")
        kind, metric = parts[0], parts[1]
        rows = load_table(root, ev_file)
        if rows is None: raise KeyError(f"{ev_file} 不存在")
        if kind == "mean":
            v = vals_anywhere(root, res, rows, parts[2], metric, gk)
            if not v: raise KeyError(f"{parts[2]} 在 {ev_file} 无 {metric}")
            return statistics.mean(v)
        if kind == "z":
            ref = res.get("reference_method", "ours")
            va = vals_anywhere(root, res, rows, parts[2], metric, gk); vr = group_vals(load_table(root, res.get("main_table", "results/main.csv")), ref, metric, gk)
            if not va: raise KeyError(f"{parts[2]} 无 {metric}")
            if len(vr) < 2: raise KeyError(f"参照 {ref} 在 main_table 不足 2 seeds，σ_ref 不可得")
            sd = statistics.stdev(vr)
            return abs(statistics.mean(va) - statistics.mean(vr)) / (sd * math.sqrt(2)) if sd > 0 else float("inf")
        a_, b_ = parts[2], parts[3]
        va, vb = vals_anywhere(root, res, rows, a_, metric, gk), vals_anywhere(root, res, rows, b_, metric, gk)
        if not va or not vb: raise KeyError(f"{a_ if not va else b_} 无 {metric}（查了 {ev_file} 与 main/ablation 表）")
        ma, mb = statistics.mean(va), statistics.mean(vb)
        return (ma - mb) if kind == "delta" else (100.0 * (ma - mb) / mb if mb else float("nan"))
    if not os.path.exists(fp): raise KeyError(f"{ev_file} 不存在")
    if ev_file.endswith(".json"):
        o = json.load(open(fp, encoding="utf-8"))
        for part in key.split("."): o = o[int(part)] if isinstance(o, list) else o[part]
        return float(o)
    rows = list(csv.DictReader(open(fp, encoding="utf-8-sig")))
    if "=" in key:
        sel, col = key.rsplit(",", 1)
        conds = [kv.split("=", 1) for kv in sel.split("|")]
        hit = [r for r in rows if all(r.get(k) == v for k, v in conds)]
        if len(hit) != 1: raise KeyError(f"{sel} 命中 {len(hit)} 行")
        return float(hit[0][col])
    i, col = key.split(",", 1); return float(rows[int(i)][col])

def holds(value, expected):
    e = expected.strip().replace("−", "-").replace("％", "%").replace("%", "")
    if e in ("+", "-"): return (value > 0) if e == "+" else (value < 0), f"sign {'+' if value > 0 else '-' if value < 0 else '0'}"
    m = re.fullmatch(r"(<=|>=|==|<|>|=)?\s*(-?\d+(?:\.\d+)?)\s*(?:±\s*(\d+(?:\.\d+)?))?", e)
    if not m: raise ValueError(f"expected '{expected}' 看不懂（<x <=x >x >=x ==x x±t + −）")
    op, x, tol = m.group(1) or "=", float(m.group(2)), m.group(3)
    if tol is not None: return abs(value - x) <= float(tol), f"|{value:.4g} − {x}| {'≤' if abs(value - x) <= float(tol) else '>'} {tol}"
    if op in ("=", "=="):
        dec = len(m.group(2).split(".")[1]) if "." in m.group(2) else 0
        return round(value, dec) == x, f"{round(value, dec)} vs {x}"
    ok = {"<": value < x, "<=": value <= x, ">": value > x, ">=": value >= x}[op]
    return ok, f"{value:.4g} {op} {x}"

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default="."); ap.add_argument("--claims", default="paper/claims.csv"); ap.add_argument("--manuscript", default="paper/manuscript.md")
    ap.add_argument("--state", default="research-state.yaml"); ap.add_argument("--family", default="")
    a = ap.parse_args(); root = os.path.abspath(a.project)
    import yaml
    sp = os.path.join(root, a.state); st = (yaml.safe_load(io.open(sp, encoding="utf-8")) or {}) if os.path.exists(sp) else {}
    res = st.get("results") or {}
    cp = os.path.join(root, a.claims)
    if not os.path.exists(cp): say("FAIL", f"{a.claims} 不存在"); sys.exit(1)
    rows = read_rows(cp)
    if not rows: say("FAIL", f"{a.claims} 没有填写的主张行（每条主张一行：陈述、证据文件、evidence_key、expected、表/图、作用域词）"); sys.exit(1)
    hdr = next(csv.reader(open(cp, encoding="utf-8-sig")), [])
    if "evidence_key" not in hdr or "expected" not in hdr: say("WARN", "claims.csv 没有 evidence_key / expected 列（模板 templates/claims.csv 已加）：主张无法机械核验，全部按定性行处理")
    mp = os.path.join(root, a.manuscript); md = io.open(mp, encoding="utf-8").read() if os.path.exists(mp) else ""
    md = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith(">"))
    body = md.split("\n## References")[0]
    try:
        import shape_check
        fam, why = (a.family, "--family") if a.family else shape_check.infer_family(st)
    except Exception:
        fam, why = (a.family or "cs_journal"), "default"
    # ---- rows: evidence
    computed = {}
    for r in rows:
        cid, stmt = r["claim_id"].strip(), r["statement"].strip()
        ev, key, exp = (r.get("evidence_file") or "").strip(), (r.get("evidence_key") or "").strip(), (r.get("expected") or "").strip()
        if ev and not os.path.exists(os.path.join(root, ev)): say("FAIL", f"{cid}: evidence_file {ev} 不存在")
        if not key:
            say("WARN", f"{cid}: 无 evidence_key，定性主张不可机械核验（审稿席位人工回看）: {stmt[:70]}"); continue
        try: v = compute(root, res, ev, key)
        except Exception as ex: say("FAIL", f"{cid}: evidence_key `{key}` 算不出来 —— {ex}"); continue
        computed[cid] = v
        if not exp: say("FAIL", f"{cid}: 有 evidence_key 但无 expected（算出 {v:.4g}，写 expected 让它成为可证伪的判据）"); continue
        try: ok, how = holds(v, exp)
        except ValueError as ex: say("FAIL", f"{cid}: {ex}"); continue
        say("PASS" if ok else "FAIL", f"{cid}: `{key}` = {v:.4g}，expected {exp} {'成立' if ok else '不成立'}（{how}）" + ("" if ok else f" —— 主张与证据相反或数字过时: {stmt[:60]}"))
    # ---- rows: numbers in the statement must be in the manuscript; rel/delta claims vs prereg §7 minimum
    if md:
        for r in rows:
            cid, stmt = r["claim_id"].strip(), r["statement"].strip()
            missing = sorted(n for n in nums(stmt) if n not in body)
            if missing: say("FAIL", f"{cid}: 主张里的数字 {missing} 不在正文里（claims.csv 与正文不同步）")
    pr = os.path.join(root, "prereg.md")
    if os.path.exists(pr):
        pmd = io.open(pr, encoding="utf-8").read()
        m = re.search(r"^(#{1,4})\s*\d*\.?\s*success\b.*?$", pmd, re.M | re.I)
        suc = pmd[m.end():m.end() + 800] if m else ""
        mm = re.search(r"(\d+(?:\.\d+)?)\s*%", suc)
        if mm:
            need = float(mm.group(1))
            for r in rows:
                cid = r["claim_id"].strip(); key = (r.get("evidence_key") or "").strip()
                if key.startswith("rel:") and cid in computed and abs(computed[cid]) < need:
                    say("WARN", f"{cid}: 相对改进 {abs(computed[cid]):.1f}% 低于 prereg §7 的最小改进量 {need}% —— §8 备选主张生效，正文必须说明")
    if not md: say("WARN", f"{a.manuscript} 不存在：只核验了 claims.csv 的证据，未核对正文"); print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)
    # ---- where: the claim is stated in the section of its table/figure
    for r in rows:
        cid, stmt, tf = r["claim_id"].strip(), r["statement"].strip(), (r.get("table_or_figure") or "").strip()
        if not tf: continue
        mt = re.match(r"(Table|Tab\.?|Fig\.?|Figure)\s*(S?\d+)", tf, re.I)
        if not mt: continue
        kind = "Table" if mt.group(1).lower().startswith("tab") else r"Fig(?:\.|ure)"; num = mt.group(2)
        cap = re.search(r"^\**\s*%s\s*%s[a-z]?[.:*]" % (kind, num), body, re.M | re.I)
        if not cap: say("FAIL", f"{cid}: 正文里没有 {tf} 的题注（claims.csv 指向的表/图不存在）"); continue
        sec = section_of(body, cap.start())
        if maps(stmt, sec): say("PASS", f"{cid}: 在 {tf} 所在节陈述")
        else: say("FAIL", f"{cid}: {tf} 所在节没有陈述这条主张（词元重合 <50% 且无共享数字）: {stmt[:60]}")
    # ---- headline sentences -> claims rows
    def best(sentence):
        return next((r["claim_id"] for r in rows if maps(r["statement"], sentence) or maps(sentence, r["statement"])), None)
    try:
        import shape_check as sc
        _, hs = sc.headings(md)
        top = [(sc.canon(t), t, s, e) for lv, t, s, e in hs if lv <= 2]
        def sec(name):
            c = [body[s:e] for cn, t, s, e in top if cn == name] + [body[s:e] for lv, t, s, e in hs if sc.canon(t) == name]
            return max(c, key=len) if c else ""
        intro, ab, resu = sec("intro"), sec("abstract"), sec("results")
        res_subs = [t for lv, t, s, e in hs if lv == 3 and any(cn == "results" and s0 <= s < e0 for cn, t0, s0, e0 in top)]
    except Exception:
        intro = ab = resu = body; res_subs = []
    if fam == "nature":
        hw = re.search(r"\bHere,?\s+we\s+(?:show|report|present|demonstrate|develop|introduce|propose|describe|find|establish)\b[^.]*\.", intro or body[:8000], re.I)
        if not hw: say("WARN", "没有 'Here we show …' 句（G6c 也会报）")
        else:
            c = best(hw.group(0))
            if c: say("PASS", f"'Here we show' 句对应 claims {c}")
            else: say("FAIL", f"'Here we show' 句在 claims.csv 里没有对应行（≥50% 词元或共享数字）: {hw.group(0)[:90]}")
        claimy = [t for t in res_subs if len(t.split()) >= 5]
        orphan = [t for t in claimy if not best(t)]
        if orphan: say("WARN", f"{len(orphan)}/{len(claimy)} 个句式小标题没有 claims 行: {[t[:50] for t in orphan][:3]}")
        elif claimy: say("PASS", f"{len(claimy)} 个句式小标题都对应 claims 行")
    else:
        contrib = re.search(r"contributions?\s+(of this (paper|work)\s+)?(are|can be|is|include|lie)|(three|four|two)[- ]?fold", intro, re.I)
        bullets = re.findall(r"^\s*(?:\d+[.)]|[-*•▪–]|\(\d\)|\(?[ivx]+\))\s+(.+)$", intro[contrib.end():contrib.end() + 3500], re.M) if contrib else []
        if contrib and not bullets: say("WARN", "有 contributions 句但未识别到条目（PDF 转换丢项目符时正常）")
        for i, b in enumerate(bullets, 1):
            c = best(b)
            if c: say("PASS", f"贡献条目 {i} 对应 claims {c}")
            else: say("FAIL", f"贡献条目 {i} 在 claims.csv 里没有对应行（每条贡献 = 一条可核验的主张）: {b[:80]}")
        if ab:
            if any(nums(ab) & nums(r["statement"]) for r in rows): say("PASS", "摘要与 claims 行共享数字")
            elif nums(ab): say("WARN", f"摘要里的数字 {sorted(nums(ab))[:4]} 没有一个在 claims.csv 的主张里")
    # ---- strong-scope sentences -> claims rows with scope_words
    try:
        import gate_check as gc; strong = gc.SCOPE_STRONG
    except Exception:
        strong = re.compile(r"\b(the first to|outperforms? (?:all|every)|new state[- ]of[- ]the[- ]art)\b", re.I)
    n_strong = 0
    SELF = re.compile(r"\b(we|our|ours|this (?:paper|work|study)|the proposed|proposed (?:method|model|approach|framework))\b", re.I)
    for i, line in enumerate(body.splitlines(), 1):
        if not strong.search(line): continue
        # judge the SENTENCE, not the paragraph: a paragraph's other numbers would otherwise match any row
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z])", line.strip()):
            m_s = strong.search(sent)
            if not m_s: continue
            if not SELF.search(sent):      # "must transfer across every platform" is motivation about the field, not a claim the paper makes about itself
                say("INFO", f"L{i} 强作用域词但不是本文自述（无 we/our/proposed）: {sent[:80]}"); continue
            n_strong += 1
            phrase = m_s.group(0).lower()
            cands = [r for r in rows if maps(r["statement"], sent) or maps(sent, r["statement"])]
            hit = next((r for r in cands if phrase in r["statement"].lower() or phrase in (r.get("scope_words") or "").lower()), cands[0] if cands else None)
            if hit is None: say("FAIL", f"L{i} 强作用域主张没有 claims 行（哪个表？什么口径？）: {sent[:100]}")
            elif not (hit.get("scope_words") or "").strip(): say("FAIL", f"L{i} 强作用域主张对应 {hit['claim_id']}，但该行 scope_words 为空 —— 把作用域词（best/first/all/SOTA…）与它成立的数据集/口径写进去: {sent[:100]}")
            else: say("PASS", f"L{i} 强作用域主张 ↔ {hit['claim_id']}（scope_words: {hit['scope_words'][:40]}）")
    if n_strong == 0: say("INFO", "正文无强作用域主张句（the first to / outperforms all / new SOTA …）")
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)

if __name__ == "__main__":
    main()
