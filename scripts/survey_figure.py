# -*- coding: utf-8 -*-
"""S4 — the standard survey figures, generated from the project's own files (never hand-drawn). Run by Claude.

  python survey_figure.py prisma   [--project .] --out figures/fig_prisma.png [--width-mm 120] [--reasons-pass abstract,fulltext]
      PRISMA 2020 flow diagram from literature/prisma_flow.json; per-source counts from search_log.json, snowball records
      as "other methods", exclusion reasons (counted from screening_sheet.csv rows excluded at the given screen_pass values;
      `rule:` reasons are title-level and are not listed). Reasons that do not add up to the excluded count are a FAIL.
  python survey_figure.py timeline --out figures/fig_timeline.png [--by <coded column>] [--since 2015] [--until 2026] [--cumulative]
      included studies per year (stacked by a single-valued coded column); the "field is growing / shifting" figure
  python survey_figure.py coverage --out figures/fig_coverage.png [--csv coding/coverage.csv | --rows <col> --cols <col>]
      coverage heatmap with counts; zero cells outlined in the accent colour = the gaps the roadmap section must address
  python survey_figure.py bubble   --out figures/fig_evidence.png --x <col> --y <col> [--colour "<col>=<val>"]
      evidence map: bubble area = number of studies in the cell, colour = share of those studies with <col>=<val>
      (e.g. ext_val=yes), so a well-populated but weakly validated cell is visible at a glance
  python survey_figure.py rob      --out figures/fig_rob.png --domains d1,d2,... [--levels low,some,high,unclear] [--labels "d1=Patient selection,..."]
      risk-of-bias / applicability summary (QUADAS-2, PROBAST, RoB 2, or any per-domain rating in coded.csv):
      one 100 % stacked bar per domain, robvis colours, n per level printed for the caption

Every figure goes through make_figure.finish: 400 dpi PNG at --width-mm, vector PDF, <out>.source.csv with the plotted
numbers, a grayscale preview, the layout audit, and a figures.csv row (inspected=no → crop and look, then set yes).
Multi-valued (`|`-joined) columns are refused where a study would be counted twice.
"""
import argparse, collections, csv, io, json, os, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import make_figure as mf                       # house rcParams (7.5 pt serif, TrueType in PDF), Agg backend, finish()
import matplotlib.pyplot as plt
from matplotlib import patches
plt.rcParams["savefig.pad_inches"] = 0.02

ROB_COLOURS = {"low": "#5c9e6e", "some": "#e3b448", "unclear": "#b8c4d0", "high": "#c8553d"}   # robvis family; grey = unclear / not reported

def rob_colour(level):
    l = level.lower()
    if l.startswith("low"): return ROB_COLOURS["low"]
    if l.startswith("high") or l.startswith("serious") or l.startswith("critical"): return ROB_COLOURS["high"]
    if l.startswith("some") or l.startswith("mod") or "concern" in l: return ROB_COLOURS["some"]
    return ROB_COLOURS["unclear"]

def fail(msg): print(f"[FAIL] survey_figure: {msg}"); sys.exit(1)

def ctx(a):
    root = os.path.abspath(a.project); sp = os.path.join(root, "research-state.yaml")
    st = {}
    if os.path.exists(sp):
        import yaml
        st = yaml.safe_load(io.open(sp, encoding="utf-8").read()) or {}
    return root, st.get("survey") or {}

def coded_rows(root, cfg):
    p = os.path.join(root, cfg.get("coded", "coding/coded.csv"))
    if not os.path.exists(p): fail(f"{os.path.relpath(p, root)} 不存在")
    return list(csv.DictReader(io.open(p, encoding="utf-8-sig")))

def single(rows, col):
    if rows and col not in rows[0]: fail(f"coded.csv 没有列 {col!r}（有 {list(rows[0])[:12]}）")
    if any("|" in (r.get(col) or "") for r in rows): fail(f"{col} 是多值列（含 |）：一篇文献会被画两次。用单值的主值列")
    return [((r.get(col) or "").strip() or "?") for r in rows]

def size(a, h_in):
    return plt.figure(figsize=(a.width_mm / 25.4, h_in))

def finish(fig, a, src, hdr, root, caption):
    mf.finish(fig, a, src, hdr, root, caption); plt.close(fig)

# ------------------------------------------------------------------ PRISMA 2020
def _box(ax, x, y, w, h, text, fc="#ffffff", ec="#3d6a94", bold=False):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0", fc=fc, ec=ec, lw=0.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=6.3, linespacing=1.25, fontweight="bold" if bold else "normal", wrap=False)

def _arrow(ax, x0, y0, x1, y1):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="-|>", lw=0.6, color="#2b4c6f", mutation_scale=6, shrinkA=0, shrinkB=0))

def fig_prisma(a):
    root, cfg = ctx(a)
    pp = os.path.join(root, cfg.get("prisma", "literature/prisma_flow.json"))
    if not os.path.exists(pp): fail(f"{os.path.relpath(pp, root)} 不存在（S3 的 triage 写它）")
    pr = json.load(io.open(pp, encoding="utf-8"))
    need = ["identified", "deduplicated", "screened_title", "screened_abstract", "included"]
    miss = [k for k in need if not isinstance(pr.get(k), (int, float))]
    if miss: fail(f"prisma_flow.json 缺 {miss}")
    n = {k: int(pr[k]) for k in need}
    if not (n["identified"] >= n["deduplicated"] >= n["screened_title"] >= n["screened_abstract"] >= n["included"]): fail(f"PRISMA 计数不单调 {n}（先过 G-S3）")
    # per-source counts; snowball rows are "other methods" in PRISMA 2020
    db, other = [], []
    lp = os.path.join(root, cfg.get("search_log", "literature/search_log.json"))
    if os.path.exists(lp):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import survey_check
        for name, q, d, c in survey_check._sources(json.load(io.open(lp, encoding="utf-8"))):
            (other if any(k in name.lower() for k in ("snowball", "citation", "s2", "manual", "hand")) else db).append((name, c))
    # exclusion reasons at the assessed-for-eligibility stage
    reasons = collections.Counter()
    sp = os.path.join(root, cfg.get("screening_sheet", "coding/screening_sheet.csv"))
    passes = {p.strip() for p in a.reasons_pass.split(",")}
    if os.path.exists(sp):
        for r in csv.DictReader(io.open(sp, encoding="utf-8-sig")):
            if (r.get("decision") or "").strip().lower() == "exclude" and (r.get("screen_pass") or "").strip() in passes and not (r.get("reason") or "").startswith("rule:"):
                reasons[(r.get("reason_code") or r.get("reason") or "unspecified").strip()] += 1
    excl_title = n["screened_title"] - n["screened_abstract"]; excl_full = n["screened_abstract"] - n["included"]
    if reasons and sum(reasons.values()) != excl_full:
        fail(f"排除理由合计 {sum(reasons.values())} ≠ 全文/摘要级排除数 {excl_full}（screened_abstract − included）：screening_sheet 与 prisma_flow.json 不同步，或 --reasons-pass 选错了")
    top = reasons.most_common(a.max_reasons)
    if len(reasons) > a.max_reasons: top.append(("other reasons", sum(reasons.values()) - sum(c for _, c in top)))

    fig = size(a, a.height_in or 3.3); ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    L, W, R, RW = 4, 46, 58, 40          # main column x, width; side column x, width
    src_line = "\n".join(f"{nm} (n = {c})" for nm, c in db[:4]) if db else ""
    h0 = max(13.0, 3.6 * (2 + (src_line.count("\n") + 1 if src_line else 0)) + 3.5)   # grows with the per-source lines
    gap = (97 - h0 - 4 - 3 * 11) / 3                     # three equal gaps between the four stages
    rows_y = [97 - h0] + [97 - h0 - (k + 1) * (gap + 11) for k in range(3)]; H = [h0, 11, 11, 11]
    _box(ax, L, rows_y[0], W, H[0], f"Records identified from databases\n(n = {n['identified'] - sum(int(c or 0) for _, c in other)})" + ("\n" + src_line if src_line else ""))
    _box(ax, R, rows_y[0] + H[0] / 2 - 6, RW, 12, f"Records removed before screening:\nduplicates (n = {n['identified'] - n['deduplicated']})" + (f"\nOther methods (n = {sum(int(c or 0) for _, c in other)})" if other else ""))
    _box(ax, L, rows_y[1], W, H[1], f"Records screened\n(title, n = {n['screened_title']})")
    _box(ax, R, rows_y[1], RW, H[1], f"Records excluded\n(n = {excl_title})")
    _box(ax, L, rows_y[2], W, H[2], f"Reports assessed for eligibility\n(n = {n['screened_abstract']})")
    rtxt = "Reports excluded (n = %d)" % excl_full + ("".join(f"\n{k} (n = {v})" for k, v in top) if top else "")
    rh = max(H[2], 4.2 * (1 + len(top)) + 2)
    _box(ax, R, rows_y[2] + H[2] / 2 - rh / 2, RW, rh, rtxt)
    _box(ax, L, rows_y[3], W, H[3], f"Studies included in review\n(n = {n['included']})", fc="#eef3f8", bold=True)
    for i in range(3): _arrow(ax, L + W / 2, rows_y[i], L + W / 2, rows_y[i + 1] + H[i + 1])
    for i in range(3): _arrow(ax, L + W, rows_y[i] + H[i] / 2, R, rows_y[i] + H[i] / 2)
    for i, lab in enumerate(["Identification", "Screening", "", "Included"]):
        if lab: ax.text(1.2, rows_y[i] + H[i] / 2, lab, rotation=90, ha="center", va="center", fontsize=6.3, color="#2b4c6f")
    src = [["identified", n["identified"]], ["duplicates_removed", n["identified"] - n["deduplicated"]], ["screened", n["screened_title"]],
           ["excluded_title", excl_title], ["assessed", n["screened_abstract"]], ["excluded_assessed", excl_full], ["included", n["included"]]]
    src += [[f"source:{nm}", c] for nm, c in db + other] + [[f"reason:{k}", v] for k, v in top]
    finish(fig, a, src, ["count", "n"], root, f"PRISMA 2020 flow: {n['identified']} records identified, {n['included']} studies included")
    print(f"caption numbers: identified {n['identified']}, duplicates {n['identified'] - n['deduplicated']}, screened {n['screened_title']}, excluded {excl_title}, assessed {n['screened_abstract']}, excluded {excl_full}, included {n['included']}")

# ------------------------------------------------------------------ timeline
def fig_timeline(a):
    root, cfg = ctx(a); rows = coded_rows(root, cfg)
    yrs = []
    for r in rows:
        try: yrs.append(int(float(r.get("year") or "")))
        except ValueError: yrs.append(None)
    if any(y is None for y in yrs): fail(f"{sum(1 for y in yrs if y is None)} 行 year 为空或非数字")
    lo = int(a.since) if a.since else min(yrs); hi = int(a.until) if a.until else max(yrs)
    xs = list(range(lo, hi + 1)); groups = single(rows, a.by) if a.by else ["all"] * len(rows)
    order = [g for g, _ in collections.Counter(groups).most_common()]
    cnt = collections.Counter(zip(yrs, groups))
    fig = size(a, a.height_in or 2.0); ax = fig.add_subplot(111)
    bottom = np.zeros(len(xs)); src = []
    for i, g in enumerate(order):
        v = np.array([cnt[(x, g)] for x in xs], float)
        if a.cumulative: v = np.cumsum(v)
        ax.bar(xs, v, 0.72, bottom=bottom, color=mf.PALETTE[(i + 2) % len(mf.PALETTE)] if len(order) > 1 else mf.PALETTE[4], edgecolor="white", lw=0.3, label=g if a.by else None, zorder=3)
        bottom += v; src += [[x, g, int(c)] for x, c in zip(xs, v)]
    ax.set_xticks(xs[:: max(1, len(xs) // 12)]); ax.set_ylabel("cumulative studies" if a.cumulative else "studies"); ax.grid(axis="y", lw=0.3, color="#dddddd", zorder=0)
    if a.by: ax.legend(fontsize=6, ncol=min(4, len(order)), loc="upper left", handlelength=1, columnspacing=0.8)
    out_of = sum(1 for y in yrs if y < lo or y > hi)
    if out_of: print(f"[WARN] survey_figure: {out_of} 篇在 {lo}–{hi} 之外，未画")
    finish(fig, a, src, ["year", a.by or "group", "n"], root, f"included studies per year {lo}-{hi}" + (f" by {a.by}" if a.by else ""))
    peak = max(xs, key=lambda x: sum(cnt[(x, g)] for g in order))
    print(f"caption numbers: {len(rows)} studies, {lo}–{hi}, peak {peak} ({sum(cnt[(peak, g)] for g in order)})" + (f"; by {a.by}: " + ", ".join(f"{g} {groups.count(g)}" for g in order) if a.by else ""))

# ------------------------------------------------------------------ coverage heatmap
def _matrix(a, root, cfg):
    if a.rows and a.cols:
        rows = coded_rows(root, cfg); rv, cv = single(rows, a.rows), single(rows, a.cols)
        R = sorted(set(rv)); C = sorted(set(cv)); cnt = collections.Counter(zip(rv, cv))
        return a.rows, a.cols, R, C, np.array([[cnt[(r, c)] for c in C] for r in R], float)
    p = os.path.join(root, a.csv or cfg.get("coverage", "coding/coverage.csv"))
    if not os.path.exists(p): fail(f"{os.path.relpath(p, root)} 不存在（survey_tables.py crosstab 生成）")
    body = [r for r in csv.reader(io.open(p, encoding="utf-8-sig")) if any(c.strip() for c in r)]
    hdr = body[0]; keep = [j for j, h in enumerate(hdr) if j and h.strip().lower() not in ("total", "合计", "sum")]
    data = [r for r in body[1:] if r[0].strip().lower() not in ("total", "合计", "sum")]
    return hdr[0], "", [r[0] for r in data], [hdr[j] for j in keep], np.array([[float(r[j] or 0) for j in keep] for r in data])

def fig_coverage(a):
    root, cfg = ctx(a); rname, cname, R, C, M = _matrix(a, root, cfg)
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("t2p", ["#ffffff", "#b8c4d0", "#5b8bb5", "#2b4c6f"])
    h = a.height_in or max(1.4, 0.22 * len(R) + 0.7)
    fig = size(a, h); ax = fig.add_subplot(111)
    ax.imshow(M, cmap=cmap, aspect="auto", vmin=0, vmax=max(M.max(), 1))
    for i in range(len(R)):
        for j in range(len(C)):
            v = int(M[i, j])
            if v == 0: ax.add_patch(patches.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, ec=mf.ACCENT, lw=0.8, zorder=4))
            ax.text(j, i, str(v), ha="center", va="center", fontsize=6, color="white" if v > 0.55 * M.max() else "#222222", zorder=5)
    ax.set_xticks(range(len(C))); ax.set_xticklabels(C, rotation=30 if max(map(len, C)) > 5 else 0, ha="right" if max(map(len, C)) > 5 else "center")
    ax.set_yticks(range(len(R))); ax.set_yticklabels(R)
    for s in ax.spines.values(): s.set_visible(False)
    ax.tick_params(length=0)
    if rname: ax.set_ylabel(rname)
    if cname: ax.set_xlabel(cname)
    gaps = [(R[i], C[j]) for i in range(len(R)) for j in range(len(C)) if M[i, j] == 0]
    src = [[R[i], C[j], int(M[i, j])] for i in range(len(R)) for j in range(len(C))]
    finish(fig, a, src, [rname or "row", cname or "col", "n"], root, f"coverage {len(R)}x{len(C)}, {len(gaps)} empty cells outlined")
    print(f"caption numbers: {int(M.sum())} studies, {len(gaps)} empty cells: {gaps[:10]}")

# ------------------------------------------------------------------ evidence map (bubble)
def fig_bubble(a):
    root, cfg = ctx(a); rows = coded_rows(root, cfg)
    xv, yv = single(rows, a.x), single(rows, a.y)
    X = sorted(set(xv)); Y = sorted(set(yv)); cnt = collections.Counter(zip(xv, yv))
    good = collections.Counter()
    if a.colour:
        ccol, cval = a.colour.split("=", 1)
        for r, x, y in zip(rows, xv, yv):
            if cval in {v.strip() for v in (r.get(ccol) or "").split("|")}: good[(x, y)] += 1
    fig = size(a, a.height_in or max(1.6, 0.26 * len(Y) + 0.8)); ax = fig.add_subplot(111)
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("t2p_div", [mf.ACCENT, "#e9e3d6", "#3d6a94"])
    mx = max(cnt.values()); src = []
    for (x, y), n in cnt.items():
        share = good[(x, y)] / n if a.colour else None
        ax.scatter(X.index(x), Y.index(y), s=18 + 260 * n / mx, color=cmap(share) if share is not None else mf.PALETTE[4], edgecolor="#2b4c6f", lw=0.4, alpha=0.9, zorder=3)
        ax.text(X.index(x), Y.index(y), str(n), ha="center", va="center", fontsize=5.5, zorder=4, color="#111111")
        src.append([x, y, n, "" if share is None else f"{share:.3f}"])
    ax.set_xticks(range(len(X))); ax.set_xticklabels(X, rotation=30 if max(map(len, X)) > 5 else 0, ha="right" if max(map(len, X)) > 5 else "center")
    ax.set_yticks(range(len(Y))); ax.set_yticklabels(Y); ax.set_xlim(-0.6, len(X) - 0.4); ax.set_ylim(-0.6, len(Y) - 0.4)
    ax.set_xlabel(a.x); ax.set_ylabel(a.y); ax.grid(lw=0.3, color="#e5e5e5", zorder=0)
    if a.colour:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1)); cb = fig.colorbar(sm, ax=ax, fraction=0.04, pad=0.02)
        cb.set_label(f"share {a.colour}", fontsize=6); cb.ax.tick_params(labelsize=5.5, length=1.5); cb.outline.set_linewidth(0.4)
    finish(fig, a, src, [a.x, a.y, "n", f"share_{a.colour}" if a.colour else "share"], root, f"evidence map {a.x} x {a.y}" + (f", colour = share {a.colour}" if a.colour else ""))
    if a.colour:
        weak = sorted(((n, k) for k, n in cnt.items() if good[k] / n < 0.25), reverse=True)[:5]
        print(f"caption numbers: {len(rows)} studies in {len(cnt)} cells; well-populated cells with share {a.colour} < 25%: {[(k, n) for n, k in weak]}")

# ------------------------------------------------------------------ risk of bias summary
def fig_rob(a):
    root, cfg = ctx(a); rows = coded_rows(root, cfg)
    doms = [d.strip() for d in a.domains.split(",") if d.strip()]
    miss = [d for d in doms if rows and d not in rows[0]]
    if miss: fail(f"coded.csv 没有偏倚风险列 {miss}")
    levels = [l.strip() for l in a.levels.split(",")]
    labels = dict(kv.split("=", 1) for kv in a.labels.split(",") if "=" in kv) if a.labels else {}
    bad = collections.Counter((d, (r.get(d) or "").strip()) for r in rows for d in doms if (r.get(d) or "").strip() not in levels)
    if bad: fail(f"偏倚风险列里有不在 --levels {levels} 的值: {dict(bad.most_common(6))}（空/? 也要明确记为 unclear）")
    fig = size(a, a.height_in or 0.24 * len(doms) + 0.75); ax = fig.add_subplot(111)
    src = []
    for i, d in enumerate(doms[::-1]):
        c = collections.Counter((r.get(d) or "").strip() for r in rows); left = 0.0
        for lv in levels:
            w = 100 * c[lv] / len(rows)
            col = rob_colour(lv)
            ax.barh(i, w, left=left, color=col, edgecolor="white", lw=0.4, height=0.68, label=lv if i == 0 else None, zorder=3)
            if w >= 9: ax.text(left + w / 2, i, str(c[lv]), ha="center", va="center", fontsize=5.5, color="white" if lv.lower() in ("low", "high") else "#222222", zorder=4)
            left += w; src.append([d, lv, c[lv], f"{100 * c[lv] / len(rows):.1f}"])
    ax.set_yticks(range(len(doms))); ax.set_yticklabels([labels.get(d, d) for d in doms[::-1]]); ax.set_xlim(0, 100); ax.set_xlabel("studies (%)")
    ax.legend(fontsize=6, ncol=len(levels), loc="lower center", bbox_to_anchor=(0.5, 1.0), handlelength=1, columnspacing=0.8)
    finish(fig, a, src, ["domain", "level", "n", "percent"], root, f"risk-of-bias summary over {len(doms)} domains, {len(rows)} studies")
    worst = max(doms, key=lambda d: sum(1 for r in rows if (r.get(d) or "").strip().lower() == "high"))
    print(f"caption numbers: {len(rows)} studies; domain with most high-risk ratings: {labels.get(worst, worst)} ({sum(1 for r in rows if (r.get(worst) or '').strip().lower() == 'high')})")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    ps = {}
    for name, w in (("prisma", 120), ("timeline", 90), ("coverage", 90), ("bubble", 120), ("rob", 120)):
        p = ps[name] = sub.add_parser(name); p.add_argument("--project", default="."); p.add_argument("--out", required=True)
        p.add_argument("--width-mm", type=float, default=w); p.add_argument("--height-in", type=float, default=0.0)
    ps["prisma"].add_argument("--reasons-pass", default="abstract,fulltext"); ps["prisma"].add_argument("--max-reasons", type=int, default=5)
    ps["timeline"].add_argument("--by", default=""); ps["timeline"].add_argument("--since", default=""); ps["timeline"].add_argument("--until", default=""); ps["timeline"].add_argument("--cumulative", action="store_true")
    ps["coverage"].add_argument("--csv", default=""); ps["coverage"].add_argument("--rows", default=""); ps["coverage"].add_argument("--cols", default="")
    ps["bubble"].add_argument("--x", required=True); ps["bubble"].add_argument("--y", required=True); ps["bubble"].add_argument("--colour", "--color", dest="colour", default="")
    ps["rob"].add_argument("--domains", required=True); ps["rob"].add_argument("--levels", default="low,some,high,unclear"); ps["rob"].add_argument("--labels", default="")
    a = ap.parse_args()
    {"prisma": fig_prisma, "timeline": fig_timeline, "coverage": fig_coverage, "bubble": fig_bubble, "rob": fig_rob}[a.cmd](a)

if __name__ == "__main__":
    main()
