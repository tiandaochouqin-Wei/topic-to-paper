# -*- coding: utf-8 -*-
"""P6 — section-by-section must-write checklist, generated from what P1–P4 already produced, then checked against the draft.

  python draft_plan.py plan  [--project .] [--out paper/draft_plan.md]      build the checklist (markdown + json)
  python draft_plan.py check [--project .] [--manuscript paper/manuscript.md] verify every item has a matching sentence; exit = #FAIL

Sources -> items (each item: section, what must be said, probe used to verify):
  gap_map.md   判定.重要性 / 关键论文失效点原句 / 评测盲区 / 邻域默认假设  -> Introduction (works named must be cited there; 盲区 -> Results or Discussion)
  prereg.md    §0 现象+原因 -> Introduction & Method motivation; §1 一句话主张 -> Introduction; §5 baselines -> Results (each name);
               §6 ablations -> Method (each component named) & Results; §8 failure 分支 + §7 最小改进量 -> Limitations/Discussion
  claims.csv   每条 statement 的数字 -> Introduction contributions AND the section its table_or_figure lives in
  results/     main.csv: ref vs strongest baseline on primary metric -> Results must state the relative change (±1 in last digit);
               strongest = min or max by results.metric_direction / primary_direction (metric_direction.py; name regex if unset);
               ablation resolve: unresolvable cells -> Results must say "noise/resolution/not resolvable/within" — in the prose OR in a figure/table caption / table footnote;
               failure_slices.md: worst slice + AUROC -> Results/Discussion must mention them
  transfer_scan.md  selected row's 失效点 -> Method/Introduction (tokens)

Verification is token overlap inside the right section (≥ 60 % of content words, or the exact number), not semantics.
It catches "forgot to say it" and "said it in the wrong section"; it cannot catch "said it wrong" — G6 numbers/scope do that.
"""
import argparse, csv, io, json, os, re, sys, statistics, collections
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); import metric_direction as mdir
FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {msg}")

def section(md, name):
    m = re.search(r"^(#{1,4})\s*\d*\.?\s*" + re.escape(name) + r"\b.*?$", md, re.M | re.I)
    if not m: return None
    depth = len(m.group(1)); rest = md[m.end():]
    nxt = re.search(r"^#{1,%d}\s" % depth, rest, re.M)
    return rest[:nxt.start()] if nxt else rest

SECTION_ALIASES = {
    "intro": ["Introduction", "引言", "绪论"],
    "method": ["Method", "Methods", "Methodology", "Approach", "Proposed", "方法"],
    "results": ["Experiments", "Results", "Experimental", "Evaluation", "实验", "结果"],
    "limitations": ["Limitation", "Discussion", "讨论", "局限"],
    "conclusion": ["Conclusion", "结论"],
}
def ms_section(md, key):
    """body of the first top-level/second-level heading matching any alias; limitations may be a sub-heading inside results."""
    for al in SECTION_ALIASES[key]:
        m = re.search(r"^(#{1,3})\s*\d*\.?\d*\s*[^\n]*\b" + re.escape(al) + r"[^\n]*$", md, re.M | re.I)
        if m:
            depth = len(m.group(1)); rest = md[m.end():]
            nxt = re.search(r"^#{1,%d}\s" % depth, rest, re.M)
            return rest[:nxt.start()] if nxt else rest
    return None

STOP = set("the a an of to in on for and or with by from as is are be that this we our it its at under over than into via using use used based across between per each all any not no non new novel method methods approach model models result results paper work study data set sets".split())
def toks(s):
    return [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}|[一-鿿]{2,}", s.lower()) if w not in STOP]
CJK = re.compile(r"[一-鿿]")
def overlap(need, hay):
    need = [t for t in dict.fromkeys(toks(need))]
    if not CJK.search(hay): need = [t for t in need if not CJK.search(t)]   # English manuscript: CJK probe tokens (bilingual prereg) cannot match by construction
    if not need: return 1.0
    h = hay.lower()
    return sum(1 for t in need if t in h) / len(need)

def table_rows(txt):
    """data rows of markdown tables: the line right before a |---| separator is a header and is dropped."""
    out = []; lines = (txt or "").splitlines()
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("|") or set(ln.replace("|", "").strip()) <= set("-: "): continue
        if i + 1 < len(lines) and lines[i + 1].strip().startswith("|") and set(lines[i + 1].replace("|", "").strip()) <= set("-: "): continue   # header
        cells = [c.strip().strip("*`") for c in ln.strip().strip("|").split("|")]
        if cells and cells[0]: out.append(cells)
    return out

def read_csv(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig"))) if os.path.exists(p) else []

def numbers_in(s): return set(re.findall(r"\d+(?:\.\d+)?", s))

def _seed_key(s):
    try: return (0, float(s), s)
    except ValueError: return (1, 0.0, s)

def seed_means(rows, gk, pm):
    """{method: mean of pm} over all seeds every method shares (per-seed mean first, so repeat rows or extra seeds
    of one method cannot shift its mean), and a note naming those seeds for the checklist line."""
    cell = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        try: cell[r[gk]][str(r.get("seed", "")).strip()].append(float(r[pm]))
        except Exception: pass
    if not cell: return {}, ""
    common = set.intersection(*(set(d) for d in cell.values()))
    if common == {""}: return {k: statistics.mean(d[""]) for k, d in cell.items()}, "全部行均值（无 seed 列）"
    use = common - {""} if common - {""} else None
    out = {k: statistics.mean(statistics.mean(v) for s, v in d.items() if use is None or s in use) for k, d in cell.items()}
    if use is None: return out, "各方法 seed 无交集：按各自全部 seed 平均"
    seeds = sorted(use, key=_seed_key); extra = any(set(d) - use for d in cell.values())
    return out, f"{len(seeds)} 个共同 seed 的均值（seed {', '.join(seeds)}）" + ("；只在部分方法出现的 seed 不计" if extra else "")

_UP, _DOWN = r"higher|increas|rise|rose|raise|larger|greater|more|above|提高|增加|上升|增大", r"lower|reduc|decreas|drop|fell|fall|smaller|less|fewer|below|降低|减少|下降|减小"
def direction_words(better, lower_better):
    """Regex of words that state the sign of ref-vs-baseline in prose ("4% lower RMSE", "4% worse AUC")."""
    w = (r"improv|better|outperform|gain|advantage|提升|改善|优于|改进|" + (_DOWN if lower_better else _UP)) if better else \
        (r"worse|degrad|underperform|trail|lag|behind|short\s+of|劣于|变差|退化|落后|" + (_UP if lower_better else _DOWN))
    return r"(?<![A-Za-z])(?:" + w + ")"

_MINUS = "-\u2212"
def pct_change_stated(v, hay, dirw=None):
    """number_pm1: the relative change v (signed, whole %) appears within ±1. Positive: "4%" or "+4%", never as "-4%".
    Negative: "-4%" / "\u22124%", or "4%" plus a direction word (dirw) in the same sentence. A range "3-4%" is not a sign."""
    def signed_neg(m, hay): return m.start() > 0 and hay[m.start() - 1] in _MINUS and not (m.start() > 1 and hay[m.start() - 2].isdigit())
    for x in (v - 1, v, v + 1):
        a = abs(x); num = r"(?<![\d.])%d(?:\.\d+)?\s*%%" % a
        if x == 0:
            if re.search(num, hay): return True
        elif x > 0:
            if any(not signed_neg(m, hay) for m in re.finditer(num, hay)): return True
        else:
            if any(signed_neg(m, hay) for m in re.finditer(num, hay)): return True
            if dirw:
                for sent in re.split(r"(?<=[.!?;。！？；])\s+|\n", hay):
                    if any(not signed_neg(m, sent) for m in re.finditer(num, sent)) and re.search(dirw, sent, re.I): return True
    return False

# ------------------------------------------------------------------ plan
def build(root):
    items = []
    def add(sec, src, must, probe, kind="tokens", level="FAIL"):
        items.append({"id": f"{sec[:3].upper()}{len(items)+1:02d}", "section": sec, "source": src, "must": must, "probe": probe, "kind": kind, "level": level})
    import yaml
    st = yaml.safe_load(io.open(os.path.join(root, "research-state.yaml"), encoding="utf-8")) if os.path.exists(os.path.join(root, "research-state.yaml")) else {}
    res = st.get("results") or {}
    # ---- family-specific shape items (references/venue-profiles.md)
    tgt = (st.get("target") or {}); fam = (tgt.get("family") or "").lower()
    if not fam:
        v = tgt.get("venue") or ""
        fam = "nature" if re.search(r"nature|science|npj|sci\.?\s*adv|cell\b|lancet|nejm|jama", v, re.I) else "cs_conf" if re.search(r"cvpr|neurips|nips|icml|iclr|aaai|ijcai|miccai|eccv|iccv|acl\b|emnlp|kdd", v, re.I) else "cs_journal"
    if fam == "nature":
        add("intro", "venue-profile nature", "引言末段必须有一句 'Here we show/report …' 给出主张（代替贡献列表）", r"\bHere,?\s+we\s+(show|report|present|demonstrate|develop|introduce|find|establish)", "regex")
        add("results", "venue-profile nature", "Results 每个小标题是完整主张句（≥2 个含动词的句式小标题）", r"^###\s+.*\b(is|are|does|improves?|reduces?|predicts?|reveals?|enables?|outperforms?|generali[sz]es?|transfers?|requires?|depends?|fails?|holds?|collapses?)\b", "regex")
        add("limitations", "venue-profile nature", "Discussion 里要有与前人结论的关系（supports / contrasts / consistent with / in contrast to）", r"consistent with|in contrast to|contrary to|supports? the|extends? the|reconcil|previous(ly)? (reported|proposed|observed)", "regex", "WARN")
    else:
        add("intro", "venue-profile cs", "引言末尾贡献列表 3–5 条（'contributions … as follows'）", r"contributions?\s+(of this (paper|work)\s+)?(are|can be|is|include)", "regex")
        add("results", "venue-profile cs", "实验节有消融小节（Ablation）", r"^#{2,4}\s*\d*\.?\d*\s*.*ablation|ablation stud", "regex")
        add("conclusion", "venue-profile cs", "有 Conclusion 节且含一个数字", r"\d", "regex", "WARN")
    # ---- gap_map
    gp = os.path.join(root, "literature", "gap_map.md"); gap = io.open(gp, encoding="utf-8").read() if os.path.exists(gp) else ""
    if gap:
        t = section(gap, "判定") or ""
        m = re.search(r"重要性\s*[:：]\s*(\S.*)", t)
        if m: add("intro", "gap_map 判定.重要性", "第一段说清问题为什么重要：" + m.group(1)[:80], m.group(1), "tokens")
        for cells in table_rows(section(gap, "现有方法在哪里失效") or ""):
            if len(cells) >= 3 and cells[2] and not cells[0].startswith("陆地"):
                work = re.sub(r"\(.*?\)|\*", "", cells[0]).strip()
                add("intro", f"gap_map 失效点：{work}", f"引言或相关工作里点名 {work} 并说它的失效点（{cells[2][:60]}…）", work, "name")
        for k, sec in (("评测盲区", "results"), ("邻域默认假设", "intro")):
            t = section(gap, k) or ""
            if t.strip() and not t.strip().startswith("未知"):
                add(sec, f"gap_map {k}", f"{k}的答案要进正文（{t.strip()[:60]}…）", t.strip()[:300], "tokens", "WARN")
    # ---- prereg
    pp = os.path.join(root, "prereg.md"); pr = io.open(pp, encoding="utf-8").read() if os.path.exists(pp) else ""
    if pr:
        ph = section(pr, "phenomenon") or section(pr, "现象") or ""
        for lab, sec in (("现象", "intro"), ("原因", "method")):
            m = re.search(lab + r"[^：:]*[:：]\s*(\S.*)", ph)
            if m and not m.group(1).startswith("<"): add(sec, f"prereg §0 {lab}", f"{'引言' if sec=='intro' else '方法动机段'}必须复述 §0 的{lab}：{m.group(1)[:70]}", m.group(1), "tokens")
        hyp = section(pr, "hypothesis") or ""
        first = next((l.strip() for l in hyp.splitlines() if l.strip() and not l.strip().startswith(("来源", "一句"))), "")
        if first: add("intro", "prereg §1 主张", "引言末段用一句话给出主张（与 prereg §1 同义）", first[:400], "tokens")
        for cells in table_rows(section(pr, "baselines") or ""):
            if cells[0] and not cells[0].lower().startswith(("persistence",)): add("results", f"prereg §5 基线 {cells[0]}", f"结果节必须出现基线 {cells[0]}", cells[0], "name")
        for cells in table_rows(section(pr, "ablations") or ""):
            if cells[0]:
                add("method", f"prereg §6 消融 {cells[0]}", f"方法节必须描述组件 {cells[0]}（有消融的组件才算贡献）", cells[0], "name", "WARN")
                add("results", f"prereg §6 消融 {cells[0]}", f"结果/消融节必须出现 {cells[0]}", cells[0], "name")
        fail = section(pr, "failure") or ""
        for l in [x.strip("-* ").strip() for x in fail.splitlines() if x.strip() and len(x.strip()) > 20][:4]:
            add("limitations", "prereg §8 失败分支", "局限节要覆盖预注册写下的失败分支：" + l[:70], l, "tokens", "WARN")
        suc = section(pr, "success") or ""
        m = re.search(r"(\d+(?:\.\d+)?)\s*(%|points?|pp|个百分点|CSI|RMSE|AUC|F1|Dice|mIoU)", suc)
        if m: add("results", "prereg §7 最小改进量", f"结果节要对照预注册的最小改进量 {m.group(0)} 说明达到与否", m.group(1), "number", "WARN")
    # ---- claims.csv
    for r in read_csv(os.path.join(root, "paper", "claims.csv")):
        if r.get("statement", "").strip():
            nums = numbers_in(r["statement"])
            add("intro", f"claims {r.get('claim_id')}", "贡献条目要含该主张的数字：" + r["statement"][:70], " ".join(sorted(nums)) if nums else r["statement"], "numbers" if nums else "tokens")
            if (r.get("table_or_figure") or "").strip():     # a claim without a table/figure (prereg §0 control experiment, protocol claims) is stated in the intro only
                add("results", f"claims {r.get('claim_id')} @ {r.get('table_or_figure','')}", "结果节陈述该主张并指向 " + str(r.get("table_or_figure", "")), " ".join(sorted(nums)) if nums else r["statement"], "numbers" if nums else "tokens")
    # ---- results: ref vs strongest baseline on primary metric
    mt = os.path.join(root, res.get("main_table", "results/main.csv")); rows = read_csv(mt)
    pm = res.get("primary_metric"); gk = res.get("group_key", "method"); ref = res.get("reference_method", "ours")
    if rows and pm and pm in rows[0]:
        by, seed_note = seed_means(rows, gk, pm)
        if ref in by and len(by) > 1:
            try: lower_better = mdir.lower_is_better(pm, res)   # results.metric_direction / primary_direction, else the name regex
            except ValueError as e: print(f"[FAIL] research-state.yaml {e}"); sys.exit(1)
            rv = by[ref]; others = {k: v for k, v in by.items() if k != ref}
            if lower_better: others = {k: v for k, v in others.items() if v > 0} or others   # a risk identically 0 is a trivial set, not a strongest baseline
            best = min(others, key=others.get) if lower_better else max(others, key=others.get)
            rel = (others[best] - rv) / others[best] * 100 if lower_better else (rv - others[best]) / others[best] * 100
            add("results", "main.csv 主指标", f"结果节必须给出 {ref} 相对最强基线 {best} 在 {pm} 上的相对变化（约 {rel:.0f}%，{seed_note}；正文可取整到 ±1，"
                f"写成带符号的 {rel:.0f}% 或绝对值加方向词，如 {abs(rel):.0f}% {'better' if rel >= 0 else 'worse'}）", f"{rel:.0f}", "number_pm1")
            items[-1]["dir"] = direction_words(rel >= 0, lower_better)
            add("results", "main.csv 主指标", f"结果节必须出现最强基线的名字 {best}", best, "name")
    # ---- ablation resolution
    at = os.path.join(root, res.get("ablation_table", "results/ablation.csv"))
    if os.path.exists(at) and rows:
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(HERE, "ablation_plan.py"), "resolve", "--project", root], capture_output=True, text=True, encoding="utf-8")
        m = re.search(r"可解读格 (\d+)/(\d+)", r.stdout)
        if m and int(m.group(1)) < int(m.group(2)):
            add("results", "ablation resolve", f"消融节必须写明 {int(m.group(2))-int(m.group(1))}/{m.group(2)} 格在 seed 噪声内不可解读（用 not resolvable / resolution limit / within seed noise / below the noise 之类措辞；写在结果正文、或图表题注 / 表脚注里都算，make_figure.py 的灰色柱题注即是）", r"(not|un|non-?)\s*resolv|resolution\s+limit|within\s+(the\s+)?(seed|run|replicate)[- ]to[- ](seed|run|replicate)|within\s+(the\s+)?(seed|noise|s\.d\.)|below\s+(the\s+)?(seed\s+)?noise|不可(解读|分辨)|噪声内", "regex_cap")
    # ---- failure slices
    fs = os.path.join(root, res.get("failure_slices", "results/failure_slices.md"))
    if os.path.exists(fs):
        t = io.open(fs, encoding="utf-8").read()
        m = re.search(r"最差切片：([^（(]+)", t); au = re.search(r"AUROC\(sig → top-10% error\) = ([\d.]+)", t)
        if m: add("results", "failure_slices 最差切片", "失败分析必须点名误差集中的切片：" + m.group(1).strip(), m.group(1).split("=")[0].strip(), "tokens", "WARN")
        if au: add("results", "failure_slices AUROC", f"失败分析必须给出不确定度对高误差的 AUROC（{au.group(1)}）或等价的\"模型知不知道\"陈述", au.group(1)[:4], "number_prefix", "WARN")
    # ---- transfer_scan selected
    tp = os.path.join(root, "literature", "transfer_scan.md")
    if os.path.exists(tp):
        for cells in table_rows(io.open(tp, encoding="utf-8").read()):
            if len(cells) >= 8 and "选定" in cells[7] and cells[6]:
                add("method", f"transfer_scan {cells[1][:20]} 失效点", "方法节要说明借来的方法在本领域会在哪坏、本文修了什么：" + cells[6][:70], cells[6], "tokens", "WARN")
    return items

def plan(a):
    root = os.path.abspath(a.project); items = build(root)
    out = os.path.join(root, a.out); os.makedirs(os.path.dirname(out), exist_ok=True)
    L = ["# 写作必写清单（draft_plan.py plan 自动生成；写完跑 `draft_plan.py check`）", "", f"{len(items)} 项。来源：gap_map / prereg / claims.csv / results。每项写在指定章节，check 用词元重合或精确数字核对。", ""]
    for sec in ("intro", "method", "results", "limitations", "conclusion"):
        its = [i for i in items if i["section"] == sec]
        if not its: continue
        L.append(f"## {sec}  ({len(its)})"); L.append("")
        L += [f"- [ ] **{i['id']}** ({i['level']}) {i['must']}  ←{i['source']}" for i in its]; L.append("")
    io.open(out, "w", encoding="utf-8").write("\n".join(L))
    json.dump(items, open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(L)); print(f"-> {out} (+ .json)")

# ------------------------------------------------------------------ check
def caption_text(md):
    """figure/table captions (`**Fig. N.** …`, `Table N: …`) and table footnotes (non-table lines right under a markdown table, or `Note:`/`*`/`†` lines) anywhere in the manuscript."""
    out, lines = [], md.splitlines()
    for i, l in enumerate(lines):
        s = l.strip()
        if re.match(r"\*\*(?:Fig(?:ure|\.)?|Table|Tab\.)\s*[A-Z]?\d+[.:]?\s*\*\*|(?:Fig(?:ure|\.)?|Table|Tab\.)\s*[A-Z]?\d+\s*[.:]\s", s, re.I) or re.match(r"(?:\*(?!\*)|†|‡|Notes?\b)", s): out.append(s)
        elif s and not s.startswith("|") and i and lines[i - 1].lstrip().startswith("|") and not s.startswith("#"): out.append(s)   # footnote directly under a table
    return "\n".join(out)

def check(a):
    root = os.path.abspath(a.project); jp = os.path.join(root, os.path.splitext(a.plan)[0] + ".json")
    items = json.load(open(jp, encoding="utf-8")) if os.path.exists(jp) else build(root)
    mp = os.path.join(root, a.manuscript)
    if not os.path.exists(mp): say("FAIL", f"{a.manuscript} 不存在"); sys.exit(1)
    md = io.open(mp, encoding="utf-8").read().split("\n## References")[0]
    md = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith(">"))   # drop editing-log quote lines: they are not prose
    secs = {k: ms_section(md, k) for k in SECTION_ALIASES}
    missing_secs = [k for k, v in secs.items() if v is None and k != "conclusion"]
    if missing_secs: say("WARN", f"正文里找不到章节 {missing_secs}（按标题别名匹配 {[SECTION_ALIASES[k][0] for k in missing_secs]}）；这些项退化为全文搜索")
    hits = 0; done = {}
    for it in items:
        hay = secs.get(it["section"]) or md; k = it["kind"]; p = it["probe"]
        if k == "name":
            ok = bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(p) + r"(?![A-Za-z0-9])", hay, re.I)) or overlap(p, hay) >= 0.99
            if ok and len(p) <= 2: it = {**it, "level": "WARN", "must": it["must"] + "（名字太短，匹配不可靠：人工确认）"}; ok = False
            if not ok and CJK.search(p) and not CJK.search(hay):   # Chinese prereg row, English manuscript: match on the Latin tokens of the row; none -> human check
                lat = [t for t in dict.fromkeys(toks(p)) if not CJK.search(t)]
                if lat: ok = overlap(" ".join(lat), hay) >= 0.99
                else: it = {**it, "level": "WARN", "must": it["must"] + "（中文行无拉丁词元，英文稿无法机械匹配：人工确认）"}; ok = False
        elif k == "numbers": ok = all(n in hay for n in p.split())
        elif k == "number": ok = p in hay
        elif k == "number_prefix": ok = p in hay
        elif k == "number_pm1": ok = pct_change_stated(int(p), hay, it.get("dir"))
        elif k == "regex": ok = bool(re.search(p, hay, re.I))
        elif k == "regex_cap": ok = bool(re.search(p, hay + "\n" + caption_text(md), re.I))   # the statement may live in a caption / table footnote instead of the prose
        else: ok = overlap(p, hay) >= a.min_overlap
        done[it["id"]] = ok
        if ok: hits += 1; print(f"[PASS] {it['id']} {it['section']}: {it['must'][:70]}")
        else: say(it["level"], f"{it['id']} {it['section']}: 缺 —— {it['must'][:90]}  (来源 {it['source']})")
    # update checkboxes in the md plan
    pm = os.path.join(root, a.plan)
    if os.path.exists(pm):
        txt = io.open(pm, encoding="utf-8").read()
        for it, ok in done.items():
            txt = re.sub(r"- \[[ x]\] \*\*" + re.escape(it) + r"\*\*", ("- [x] **" if ok else "- [ ] **") + it + "**", txt)
        io.open(pm, "w", encoding="utf-8").write(txt)
    print(f"\n{hits}/{len(items)} 项已写；" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--project", default="."); p.add_argument("--out", default="paper/draft_plan.md")
    c = sub.add_parser("check"); c.add_argument("--project", default="."); c.add_argument("--manuscript", default="paper/manuscript.md"); c.add_argument("--plan", default="paper/draft_plan.md"); c.add_argument("--min-overlap", type=float, default=0.6)
    a = ap.parse_args(); {"plan": plan, "check": check}[a.cmd](a)

if __name__ == "__main__":
    main()
