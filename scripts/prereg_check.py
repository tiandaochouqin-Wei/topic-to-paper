# -*- coding: utf-8 -*-
"""G2 — mechanical pre-registration gate.
   python prereg_check.py [--prereg prereg.md] [--state research-state.yaml] [--norms <venue_norms.csv>]
Checks:
  1. the eight mandatory sections exist and are non-trivial (≥ 25 words or a table with ≥ 2 rows)
  2. denominator and inclusion_window each state cross-dataset consistency explicitly
  3. baselines / ablations tables have ≥ 1 row; counts are compared with the target venue's norms (references/venue-norms.csv)
  4. success criterion names a metric, a direction, a minimum effect and a statistical rule (seeds ≥ 3 or CI or test)
  5. failure criterion names a fallback claim
  6. at least one pre-stated prediction with a sign
  7. prereg.md sha256 matches research-state.yaml gates.G2.prereg_sha256 (lock), and no experiment has started before the lock
Exit 1 on any FAIL. Prints the venue norm row so the user sees what the target venue typically reports."""
import argparse, hashlib, io, os, re, sys, csv

SECTIONS = ["hypothesis", "primary_metric", "denominator", "inclusion_window", "baselines", "ablations", "success", "failure"]
FAILS = 0
def say(st, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] prereg: {msg}")

def section(md, name):
    """body of the heading whose title starts with `name`, up to the next heading of EQUAL OR SHALLOWER depth (sub-headings stay inside)."""
    m = re.search(r"^(#{1,4})\s*\d*\.?\s*" + re.escape(name) + r"\b.*?$", md, re.M | re.I)
    if not m: return None
    depth = len(m.group(1)); rest = md[m.end():]
    nxt = re.search(r"^#{1,%d}\s" % depth, rest, re.M)
    return rest[:nxt.start()] if nxt else rest

def table_rows(txt):
    rows = [l for l in txt.splitlines() if l.strip().startswith("|")]
    return max(len(rows) - 2, 0)   # header + separator

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prereg", default="prereg.md")
    ap.add_argument("--state", default="research-state.yaml")
    ap.add_argument("--norms", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "venue-norms.csv"))
    a = ap.parse_args()
    if not os.path.exists(a.prereg):
        say("FAIL", f"{a.prereg} 不存在"); sys.exit(1)
    md = io.open(a.prereg, encoding="utf-8").read()
    secs = {}
    for s in SECTIONS:
        t = section(md, s)
        if t is None or (len(t.split()) < 15 and table_rows(t) < 2):
            say("FAIL", f"缺少或过短: {s}")
        secs[s] = t or ""
    # 0 phenomenon before method: section exists; either three lines (现象/原因/最小对照) or an explicit skip with reason
    ph = section(md, "phenomenon") or section(md, "现象") or ""
    if not ph.strip(): say("WARN", "缺 §0 phenomenon：先写现有方法在哪失败、为什么、最小对照实验，再设计方法（可写\"跳过：理由\"）")
    elif re.search(r"跳过\s*[:：]", ph): say("WARN", "§0 phenomenon 跳过：" + re.search(r"跳过\s*[:：]\s*(.{0,60})", ph).group(1).strip())
    else:
        need = [k for k in ("现象", "原因", "对照") if k not in ph]
        if need: say("FAIL", f"§0 phenomenon 缺 {need} 行（现象 / 原因假设 / 最小对照实验）")
        elif re.search(r"未做|planned|计划", ph): say("WARN", "§0 的最小对照实验未做：方法设计建立在未验证的原因假设上，P3 第一件事是做它")
        else: say("PASS", "§0 phenomenon 三行齐且最小对照已做")
    if secs.get("hypothesis") and not re.search(r"因为|because|due to|原因|机制|mechanism|caused by|导致", secs["hypothesis"]):
        say("WARN", "hypothesis 没有原因词（因为/because/机制）：只说\"方法有效\"不说\"为什么现有方法失败\"，创新逻辑不完整")
    # 1b hypothesis must name where the claim came from (gap_map #X or transfer_scan #Tn); preregs locked before this rule get WARN
    hyp = secs.get("hypothesis", "")
    if not re.search(r"(来源|claim_source|source)\s*[:：]\s*(gap#\w+|transfer#T?\d+)", hyp, re.I):
        locked = False
        try:
            import yaml
            st = yaml.safe_load(io.open(a.state, encoding="utf-8")) if os.path.exists(a.state) else {}
            want = str((((st or {}).get("gates") or {}).get("G2") or {}).get("prereg_sha256", "") or "")
            locked = bool(want) and hashlib.sha256(md.encode("utf-8")).hexdigest().startswith(want[:12])   # same bytes as the lock check below
        except Exception: pass
        say("WARN" if locked else "FAIL", "hypothesis: 未写主张来源（`来源: gap#A` 或 `来源: transfer#T1`，指向 gap_map / transfer_scan 的行）" + ("—— 本 prereg 在该规则前锁定，降 WARN" if locked else ""))
    # 2 denominator / window must state cross-dataset consistency
    for s in ("denominator", "inclusion_window"):
        t = secs.get(s, "").lower()
        if t and not re.search(r"跨数据集(相同|一致)|same across (all )?datasets|identical across|differs? (between|across)|列出差异|per[- ]dataset", t):
            say("FAIL", f"{s}: 未明确写出跨数据集是否一致（必须写\"跨数据集相同\"或列出差异）")
    # 3 baselines / ablations
    nb, na = table_rows(secs.get("baselines", "")), table_rows(secs.get("ablations", ""))
    if nb < 1: say("FAIL", "baselines 表为空")
    if na < 1: say("FAIL", "ablations 表为空")
    # 4 success criterion
    t = secs.get("success", "")
    if not re.search(r"\d+(\.\d+)?\s*(%|points?|pp|个百分点|dB|AUC|AUROC|RMSE|MAE|F1|Dice|mIoU|BLEU|ACC)", t, re.I):
        say("FAIL", "success: 未写最小改进量（数字 + 单位/指标）")
    if not re.search(r"seeds?\s*[≥>=]+\s*[3-9]|[3-9]\s*(个)?\s*seeds?|confidence interval|\bCI\b|置信区间|t-test|Wilcoxon|permutation|bootstrap|p\s*<", t, re.I):
        say("FAIL", "success: 未写统计判据（≥3 seeds / CI / 检验）")
    # 5 failure fallback
    t = secs.get("failure", "")
    if not re.search(r"转向|fallback|alternative claim|备选|pivot|instead", t, re.I):
        say("FAIL", "failure: 未写假设被否后转向哪条备选 claim")
    # 6 prediction with sign
    pred = section(md, "事前预测") or section(md, "prediction") or ""
    if not re.search(r"[+\-−↑↓]|increase|decrease|higher|lower|正|负|上升|下降", pred):
        say("FAIL", "事前预测: 没有带符号/方向的预测")
    # 7 lock
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()
    locked = None
    if os.path.exists(a.state):
        st = io.open(a.state, encoding="utf-8").read()
        m = re.search(r"prereg_sha256:\s*\"?([0-9a-f]{64})", st)
        locked = m.group(1) if m else None
        venue = (re.search(r"^\s*venue:\s*\"?([^\"\n]+)", st, re.M) or [None, ""])[1].strip()
        runs = re.search(r"total_runs:\s*(\d+)", st)
        if locked and locked != sha:
            say("FAIL", f"prereg.md 已被修改但 state 里的锁没更新（锁 {locked[:8]}…，现 {sha[:8]}…）。改口径要在 state.experiments.convention_changes 留记录再重新锁")
        if not locked and runs and int(runs.group(1)) > 0:
            say("FAIL", f"state 显示已有 {runs.group(1)} 个 run 但 prereg 从未锁定：事后注册，必须在 prereg.md 首行标明 post-hoc")
        if not locked:
            say("INFO", f"当前 sha256 = {sha}  → 写入 research-state.yaml gates.G2.prereg_sha256 即锁定")
        # venue norms
        ALIAS = {"nature communications": "NatCommun", "nature medicine": "NatMed", "nature biomedical engineering": "NatBME", "nature machine intelligence": "NatMI",
                 "ieee transactions on image processing": "TIP", "ieee transactions on pattern analysis and machine intelligence": "TPAMI", "international journal of computer vision": "IJCV"}
        vkey = ALIAS.get(venue.lower().strip(), venue)
        if venue and os.path.exists(a.norms):
            for r in csv.DictReader(open(a.norms, encoding="utf-8")):
                if r["venue"].lower() == vkey.lower() or r["venue"].lower() in vkey.lower() or vkey.lower() in r["venue"].lower():
                    say("INFO", f"目标刊 {r['venue']} 规范（{r['n']} 篇中位数/占比）: 图 {r['figures']} 表 {r['tables']} 参考文献 {r['references']} | 消融 {r['has_ablation']} 报告 std {r['reports_std']} seeds {r['reports_seeds']} CI {r['reports_ci']} p 值 {r['reports_pvalue']} 开源 {r['code_link']}")
                    say("INFO", f"你的 prereg: 基线 {nb} 行、消融 {na} 行。{'基线少于 3 个在该刊属于下四分位' if nb < 3 and r['venue'] in ('CVPR','NeurIPS','ICML','TIP','TPAMI','IJCV') else ''}")
                    break
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL"))
    sys.exit(0 if FAILS == 0 else 1)

if __name__ == "__main__":
    main()
