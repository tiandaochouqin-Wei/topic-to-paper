# -*- coding: utf-8 -*-
"""Method track (project.paper_type: method) — a path that ends in a method paper, not a diagnosis.

  python method_track.py init          [--project .] [--force]
  python method_track.py headroom      [--project .]                       G1c 方法可行性与提升空间
  python method_track.py ideas-check   [--project .]                       想法清单（只 WARN）
  python method_track.py log add --id I07 --hypothesis "…" --change "…" --runs "runs/i07_s*" [--decision keep|drop|revise] [--note …]
  python method_track.py dev-check     [--project .]                       G2m 开发迭代与冻结
  python method_track.py freeze --iteration I12 [--project .]
  python method_track.py confirm-check [--project .] [--prereg prereg.md]  G4m 验证
  python method_track.py status        [--project .]
  python method_track.py code-sha      [--project .]                       冻结用的代码哈希（训练脚本写进 args.json 的 code_sha256）

Why: every paper this skill produced was an analysis paper. A method needs (1) a headroom test BEFORE designing (does an oracle fix of the
targeted bottleneck leave room, and do the cheapest alternatives already take it?), (2) a free but LOGGED dev loop (every attempt has a
denominator, so the best of K attempts is not read as an effect), (3) a freeze, (4) ONE confirmation on data nobody evaluated.

State: research-state.yaml `method:` block (templates/research-state.yaml). Runs: results.runs_dir/<id>/args.json carries
`eval_split: dev|confirm`, `role: baseline|oracle|cheap_fix|ours|ablation|tuning`, `method`, `seed`, `iteration: I07` (ours/ablation), `code_sha256`
(confirm runs); the metric is read from results.eval_file through results.metric_map[primary_metric] (or a dotted `key`).
`code_sha256` = sha256 over the bytes of every *.py under audits.code_dirs (default [code]), sorted by path, line ends normalised to LF.
Output lines: `[PASS|WARN|FAIL|INFO] G1c|G2m|G4m: …`; exit 1 when any FAIL.
Known leaks (stated in references/method-track.md): eval_split / role are self-reported; the winner's-curse bar assumes the K attempts are independent."""
import argparse, csv, datetime, glob, hashlib, io, json, math, os, re, shutil, statistics, sys
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__)); SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE); import metric_direction as mdir

NAN = float("nan")
ITER_COLS = ["id", "date", "hypothesis", "change", "runs", "n_seeds", "dev_mean", "dev_sd", "baseline_mean", "gain", "se_gain", "best_so_far", "decision", "note", "code_sha256"]
IDEA_COLS = ["id", "type", "mechanism", "predicted_effect", "cheapest_test", "kill_result", "status"]
IDEA_TYPES = {"data", "objective", "architecture", "inference", "training", "other"}
ROLES = ("baseline", "oracle", "cheap_fix", "ours", "ablation", "tuning")
TEMPLATES = ("bottleneck.md", "ideas.csv", "iterations.csv", "baseline_tuning.csv")

class Rep:
    """prints `[ST] gate: msg` and counts FAILs; quiet=True collects without printing (freeze re-uses dev-check items 1-4)"""
    def __init__(self, gate, quiet=False): self.gate, self.quiet, self.fails, self.lines = gate, quiet, 0, []
    def say(self, st, msg, gate=None):
        if st == "FAIL": self.fails += 1
        line = f"[{st}] {gate or self.gate}: {msg}"; self.lines.append(line)
        if not self.quiet: print(line)

# ------------------------------------------------------------------ state
def load_state(root):
    import yaml
    p = os.path.join(root, "research-state.yaml")
    if not os.path.exists(p): return None
    return yaml.safe_load(io.open(p, encoding="utf-8").read()) or {}

def _dump_val(v):
    import yaml
    if isinstance(v, str): return json.dumps(v, ensure_ascii=False)
    if v is None: return "null"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v)
    return yaml.safe_dump(v, default_flow_style=True, allow_unicode=True, width=10**6, sort_keys=False).strip()

def _split_comment(rest):
    """-> (value text, comment text or ''); a '#' starts a comment only outside quotes and after whitespace"""
    q = None
    for i, ch in enumerate(rest):
        if q:
            if ch == q: q = None
        elif ch in "\"'": q = ch
        elif ch == "#" and (i == 0 or rest[i - 1] in " \t"): return rest[:i].rstrip(), rest[i:]
    return rest.rstrip(), ""

def _indent(l): return len(l) - len(l.lstrip(" \t"))

def state_set(sp, path, value):
    """Set method.<path...> = value in research-state.yaml in place (comments and the other blocks stay byte-identical) when the
    target is a scalar or an inline `{...}` dict; any other layout falls back to a full re-dump (comments lost, a WARN says so).
    Same idea as t2p.py's set_gate_key. Returns 'inline' or 'dump'."""
    import yaml
    txt = io.open(sp, encoding="utf-8").read(); eol = "\r\n" if "\r\n" in txt else "\n"
    lines = txt.replace("\r\n", "\n").split("\n")
    def fallback():
        st = yaml.safe_load(txt) or {}
        d = st.setdefault("method", {})
        for k in path[:-1]: d = d.setdefault(k, {})
        d[path[-1]] = value
        io.open(sp, "w", encoding="utf-8", newline="").write(yaml.safe_dump(st, allow_unicode=True, sort_keys=False, width=10**6))
        print("[WARN] method: research-state.yaml 不是内联写法，已整体重写（其中的注释丢失）")
        return "dump"
    bi = next((i for i, l in enumerate(lines) if re.match(r"^method:\s*(#.*)?$", l)), None)
    if bi is None: return fallback()
    end = next((i for i in range(bi + 1, len(lines)) if lines[i].strip() and lines[i][0] not in " \t#"), len(lines))
    lo, hi, parent = bi + 1, end, -1
    for depth, key in enumerate(path):
        kids = [i for i in range(lo, hi) if lines[i].strip() and not lines[i].lstrip().startswith("#")]
        if not kids: return fallback()
        ci = _indent(lines[kids[0]])
        if ci <= parent: return fallback()
        at = next((i for i in kids if _indent(lines[i]) == ci and re.match(r"^\s*" + re.escape(key) + r":(\s|$)", lines[i])), None)
        if at is None: return fallback()
        m = re.match(r"^(\s*)" + re.escape(key) + r":[ \t]*(.*)$", lines[at]); val, com = _split_comment(m.group(2))
        last = depth == len(path) - 1
        if val.startswith("{"):
            try: d = yaml.safe_load(val)
            except Exception: return fallback()
            if not isinstance(d, dict): return fallback()
            if last: d = value
            else:
                cur = d
                for k in path[depth + 1:-1]:
                    cur = cur.setdefault(k, {})
                    if not isinstance(cur, dict): return fallback()
                cur[path[-1]] = value
            lines[at] = f"{m.group(1)}{key}: {_dump_val(d)}" + (f"  {com}" if com else "")
            io.open(sp, "w", encoding="utf-8", newline="").write(eol.join(lines)); return "inline"
        if val == "" and not last:
            parent = ci
            sub_end = next((i for i in range(at + 1, hi) if lines[i].strip() and not lines[i].lstrip().startswith("#") and _indent(lines[i]) <= ci), hi)
            lo, hi = at + 1, sub_end; continue
        if last and not (val == "" and at + 1 < hi and _indent(lines[at + 1]) > ci and lines[at + 1].strip()):
            lines[at] = f"{m.group(1)}{key}: {_dump_val(value)}" + (f"  {com}" if com else "")
            io.open(sp, "w", encoding="utf-8", newline="").write(eol.join(lines)); return "inline"
        return fallback()
    return fallback()

# ------------------------------------------------------------------ small helpers
def get_path(o, path):
    for part in str(path).split("."):
        o = o[int(part)] if isinstance(o, list) else o[part]
    return o

def mean(xs): return statistics.mean(xs) if xs else NAN
def sd(xs): return statistics.stdev(xs) if len(xs) >= 2 else NAN
def isn(x): return x is None or (isinstance(x, float) and math.isnan(x))
def f(x, nd=4): return "nan" if isn(x) else f"{x:.{nd}f}"
def zero(x): return 0.0 if isn(x) else x

def rel(p, root): return os.path.relpath(p, root).replace("\\", "/")

def to_ts(v):
    """state/ISO date or datetime -> POSIX timestamp (naive = local time); None when unparsable"""
    if isinstance(v, datetime.datetime): return v.timestamp()
    if isinstance(v, datetime.date): return datetime.datetime(v.year, v.month, v.day).timestamp()
    try: return datetime.datetime.fromisoformat(str(v)).timestamp()
    except Exception: return None

def read_csv_rows(p):
    """csv with '#' comment lines (the templates carry a commented example row); returns (rows, header) or (None, [])"""
    if not os.path.exists(p): return None, []
    lines = [l for l in io.open(p, encoding="utf-8-sig").read().splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not lines: return [], []
    rd = csv.DictReader(lines)
    rows = [dict(r) for r in rd]
    return rows, list(rd.fieldnames or [])

def write_csv_rows(p, cols, rows):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow({c: r.get(c, "") for c in cols})

def mfiles(m):
    d = {"bottleneck": "method/bottleneck.md", "ideas": "method/ideas.csv", "iterations": "method/iterations.csv", "tuning": "method/baseline_tuning.csv"}
    d.update({k: v for k, v in (m.get("files") or {}).items() if v}); return d

def code_dirs(st): return (st.get("audits") or {}).get("code_dirs") or ["code"]

def code_sha(root, st):
    """sha256 over the bytes of all *.py under audits.code_dirs, sorted by path (CRLF -> LF so a Windows checkout does not change it)"""
    files = set()
    for d in code_dirs(st):
        for p in glob.glob(os.path.join(root, d, "**", "*.py"), recursive=True):
            if "__pycache__" not in p.replace("\\", "/").split("/"): files.add(os.path.normpath(p))
    h = hashlib.sha256()
    for p in sorted(files, key=lambda p: rel(p, root)):
        h.update(open(p, "rb").read().replace(b"\r\n", b"\n"))
    return h.hexdigest()

def expand_files(root, items):
    out = []
    for it in items or []:
        p = os.path.join(root, it)
        if os.path.isdir(p):
            for dp, _, fs in os.walk(p):
                out += [rel(os.path.join(dp, x), root) for x in fs]
        else: out.append(it.replace("\\", "/"))
    return sorted(set(out))

def files_sha(root, items):
    h = hashlib.sha256()
    for it in expand_files(root, items): h.update(open(os.path.join(root, it), "rb").read())
    return h.hexdigest()

# ------------------------------------------------------------------ runs
class Run:
    def __init__(self, root, d, args, ev, mt):
        self.dir, self.rel, self.args, self.ev, self.mtime = d, rel(d, root), args or {}, ev, mt
        a = self.args
        self.split, self.role, self.method = a.get("eval_split"), a.get("role"), a.get("method")
        self.seed, self.iteration, self.code = a.get("seed"), a.get("iteration"), a.get("code_sha256")
    def tagged(self): return bool(self.split) and bool(self.role)
    def value(self, key):
        try: return float(get_path(self.ev, key))
        except Exception: return None

def _jload(p):
    try: return json.load(io.open(p, encoding="utf-8"))
    except Exception: return None

def load_runs(root, st):
    res = st.get("results") or {}
    rd, ef = res.get("runs_dir", "runs"), res.get("eval_file", "eval.json")
    base = os.path.join(root, rd); out = []
    if not os.path.isdir(base): return out
    for n in sorted(os.listdir(base)):
        d = os.path.join(base, n)
        if not os.path.isdir(d) or n.startswith("_"): continue
        ap, ep = os.path.join(d, "args.json"), os.path.join(d, ef)
        if not (os.path.exists(ap) or os.path.exists(ep)): continue
        a = _jload(ap) if os.path.exists(ap) else {}
        out.append(Run(root, d, a if isinstance(a, dict) else {}, _jload(ep) if os.path.exists(ep) else None, os.path.getmtime(ep) if os.path.exists(ep) else None))
    return out

def run_glob(root, pat):
    if not pat: return set()
    return {os.path.normpath(p) for p in glob.glob(os.path.join(root, pat))}

def sel(runs, root=None, role=None, split=None, pat=None, method=None):
    g = run_glob(root, pat) if pat is not None else None
    return [r for r in runs if (role is None or r.role == role) and (split is None or r.split == split) and (g is None or os.path.normpath(r.dir) in g)
            and (method is None or r.method == method)]

def pm_key(st, m):
    res = st.get("results") or {}
    pm = m.get("primary_metric") or res.get("primary_metric") or ""
    return pm, ((res.get("metric_map") or {}).get(pm) or pm)

def direction(st, m):
    """'lower' | 'higher' | None; method.primary_direction > results.primary_direction (same metric only) > name regex"""
    res = dict(st.get("results") or {}); pm = m.get("primary_metric") or res.get("primary_metric") or ""
    if m.get("primary_direction"): res["primary_direction"] = m["primary_direction"]
    elif pm != res.get("primary_metric"): res.pop("primary_direction", None)
    res["primary_metric"] = pm
    return mdir.direction(pm, res)

def vals(runs, key):
    xs = []
    for r in runs:
        v = r.value(key)
        if v is not None: xs.append(v)
    return xs

def gain(x, ref, dirn):
    if isn(x) or isn(ref): return NAN
    return (x - ref) if dirn == "higher" else (ref - x)

def se_of(sd1, n1, sd2, n2):
    if n1 < 1 or n2 < 1: return NAN
    return math.sqrt((zero(sd1) ** 2) / n1 + (zero(sd2) ** 2) / n2)

def baseline_runs(runs, m, split):
    """role=baseline runs on `split`; when some carry baseline.name as their method, only those (a weaker baseline is not the bar)"""
    name = (m.get("baseline") or {}).get("name")
    rs = sel(runs, role="baseline", split=split)
    named = [r for r in rs if name and r.method == name]
    return named or rs

def seeds_of(rs): return len({str(r.seed) for r in rs if r.seed is not None}) or len(rs)

class Ctx:
    """everything the gates share: state, method block, runs, metric key, direction"""
    def __init__(self, root):
        self.root = root; self.st = load_state(root)
        self.m = (self.st or {}).get("method") if self.st is not None else None
        if self.st is None or not isinstance(self.m, dict): return
        self.res = self.st.get("results") or {}
        self.runs = load_runs(root, self.st)
        self.pm, self.key = pm_key(self.st, self.m)
        self.min_effect = float(self.m.get("min_effect") or 0)
        self.min_seeds = int(self.res.get("min_seeds", 3))
        self.files = mfiles(self.m)
        try: self.dirn, self.dirn_err = direction(self.st, self.m), None
        except ValueError as e: self.dirn, self.dirn_err = None, str(e)
    def path(self, k): return os.path.join(self.root, self.files[k])

def need_state(R, ctx, gate_name):
    if ctx.st is None: R.say("FAIL", "research-state.yaml 不存在：先 `t2p.py init --paper-type method`"); return False
    if not isinstance(ctx.m, dict): R.say("FAIL", "state 无 method: 段（templates/research-state.yaml 末尾的块）"); return False
    return True

def need_direction(R, ctx):
    if ctx.dirn_err: R.say("FAIL", f"research-state.yaml {ctx.dirn_err}"); return False
    if ctx.dirn is None:
        R.say("FAIL", f"主指标 '{ctx.pm}' 的方向猜不出：在 method.primary_direction 或 results.primary_direction 写 lower / higher（headroom 与提升都要方向）"); return False
    return True

def runs_txt(rs, n=3): return "[" + ", ".join(r.rel for r in rs[:n]) + (f", …(+{len(rs) - n})" if len(rs) > n else "") + "]"

# ------------------------------------------------------------------ shared checks
def check_no_early_confirm(R, ctx, label):
    conf = [r for r in ctx.runs if r.split == "confirm"]
    if (ctx.m.get("freeze") or {}) :
        return
    if conf: R.say("FAIL", f"冻结前评测了验证集（run {', '.join(r.rel for r in conf[:3])}）：验证集只在 freeze 之后看一次，现在看过就烧掉了")
    else: R.say("PASS", "冻结前没有任何 confirm 评测")

def bottleneck_fields(path):
    """{field: text} from `## field` headings or `field: value` lines of method/bottleneck.md, with HTML comments and <placeholders> removed"""
    txt = re.sub(r"(?s)<!--.*?-->", "", io.open(path, encoding="utf-8").read())
    out = {}
    names = ["瞄准的瓶颈", "证据文件", "占基线误差的比例"]
    for n in names:
        mh = re.search(r"(?m)^#{1,4}[ \t]*" + n + r"[^\n]*\n(.*?)(?=^#{1,4}[ \t]|\Z)", txt, re.S)
        body = mh.group(1) if mh else ""
        for ml in re.finditer(r"(?m)^[ \t]*[-*]?[ \t]*" + n + r"[ \t]*[:：][ \t]*(.*)$", txt): body += "\n" + ml.group(1)
        body = re.sub(r"<[^<>\n]{0,80}>", "", body)
        out[n] = body.strip()
    return out

# ------------------------------------------------------------------ init
def cmd_init(root, force):
    R = Rep("G1c"); ctx = Ctx(root)
    if not need_state(R, ctx, "init"): return R.fails
    m, sp = ctx.m, os.path.join(root, "research-state.yaml")
    for fn in TEMPLATES:
        dst = os.path.join(root, ctx.files[{"bottleneck.md": "bottleneck", "ideas.csv": "ideas", "iterations.csv": "iterations", "baseline_tuning.csv": "tuning"}[fn]])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst): R.say("INFO", f"{rel(dst, root)} 已存在，保留"); continue
        shutil.copy(os.path.join(SKILL, "templates", "method", fn), dst); R.say("PASS", f"建 {rel(dst, root)}")
    cf = ((m.get("splits") or {}).get("confirm") or {}).get("files") or []
    if not cf: R.say("FAIL", "method.splits.confirm.files 为空：先填验证集文件（官方 test 或留出集），再跑 init 算 sha256"); return R.fails
    miss = [x for x in expand_files(root, cf) if not os.path.isfile(os.path.join(root, x))]
    if miss: R.say("FAIL", f"验证集文件不存在: {miss[:3]}"); return R.fails
    new, old = files_sha(root, cf), ((m.get("splits") or {}).get("confirm") or {}).get("sha256") or ""
    if old and old != new and not force:
        R.say("FAIL", f"splits.confirm.sha256 已登记且与现在的文件不同（{old[:12]}… vs {new[:12]}…）：验证集被改过；确认是有意换新验证集再加 --force"); return R.fails
    state_set(sp, ["splits", "confirm", "sha256"], new)
    R.say("PASS", f"splits.confirm.sha256 = {new}（{len(expand_files(root, cf))} 个文件）")
    print("\n下一步：\n  1. 填 method/bottleneck.md（瞄准的瓶颈 / 证据文件 / 占基线误差的比例）\n  2. 复现最强基线 ≥3 seeds、跑 oracle 与 ≥2 个便宜做法（dev 集，args.json 带 eval_split / role）\n"
          "  3. python method_track.py headroom   # G1c：GO 才开始设计方法\n  4. 填 method/ideas.csv，`ideas-check`；然后 dev 迭代，每轮 `log add`，`dev-check`")
    return R.fails

# ------------------------------------------------------------------ G1c
def cmd_headroom(root):
    R = Rep("G1c"); ctx = Ctx(root)
    if not need_state(R, ctx, "headroom"): return R.fails
    m, st = ctx.m, ctx.st
    def blank(v): return v is None or str(v).strip() == ""
    bm, bl = m.get("benchmark") or {}, m.get("baseline") or {}
    for lab, v in (("benchmark.name", bm.get("name")), ("benchmark.split_source", bm.get("split_source")), ("benchmark.metric_source", bm.get("metric_source")),
                   ("baseline.name", bl.get("name")), ("baseline.code", bl.get("code")), ("min_effect_basis", m.get("min_effect_basis"))):
        if blank(v): R.say("FAIL", f"method.{lab} 为空：公认基准、官方划分/评测脚本、最强基线的代码、min_effect 的依据都要写出处")
    if not ctx.min_effect > 0: R.say("FAIL", "method.min_effect 要 > 0（值得写一篇方法论文的最小提升，指标单位）")
    if not ctx.pm: R.say("FAIL", "method.primary_metric / results.primary_metric 都为空")
    if not need_direction(R, ctx): return _verdict_g1c(R, None)
    dirn, key = ctx.dirn, ctx.key
    hr = m.get("headroom") or {}; k_sd = float(hr.get("k_sd") or 3)
    nums = {}
    # 2. baseline reproduced on dev
    brs = baseline_runs(ctx.runs, m, "dev"); bx = vals(brs, key); b, sd_b = mean(bx), sd(bx); n_b = seeds_of(brs)
    waiver = str(ctx.res.get("seed_waiver") or "").strip()
    if len(bx) < ctx.min_seeds:
        if waiver and len(bx) >= 2: R.say("WARN", f"基线 dev 只有 {len(bx)} 个 run（要求 ≥{ctx.min_seeds}），按 results.seed_waiver 接受：{waiver[:60]}")
        else: R.say("FAIL", f"基线在 dev 上只有 {len(bx)} 个 run（role=baseline, eval_split=dev, 要求 ≥{ctx.min_seeds}）：噪声 s.d. 估不出来，提升空间无从比较")
    if len(bx) >= 2:
        nums.update(b=b, sd_b=sd_b)
        pub = bl.get("published") or {}
        if pub.get("value") is None or str(pub.get("value")).strip() == "":
            R.say("WARN", "没有可对账的已发表数字（baseline.published.value 为空）：基线没有复现到论文数字就不知道差距是实现还是方法")
        else:
            try:
                bp = float(pub["value"]); tol = float(bl["tol"]) if bl.get("tol") not in (None, "") else 2 * zero(sd_b)
                if abs(bp - b) > tol: R.say("FAIL", f"基线没复现到论文数字，先查实现（G3b）：复现 {b:.4f} vs 论文 {bp:.4f}（{pub.get('source', '')}），|Δ| = {abs(bp - b):.4f} > tol {tol:.4f}")
                else: R.say("PASS", f"基线复现 {b:.4f} vs 论文 {bp:.4f}，|Δ| = {abs(bp - b):.4f} ≤ tol {tol:.4f}")
            except (TypeError, ValueError): R.say("FAIL", "baseline.published.value / tol 不是数")
    thr = max(ctx.min_effect, k_sd * zero(sd_b))
    # 3. oracle
    orc = hr.get("oracle") or {}; okey = orc.get("key") or key
    ors = sel(ctx.runs, ctx.root, role="oracle", split="dev", pat=orc.get("run_glob") or "")
    o = NAN; H = NAN
    if not ors:
        R.say("FAIL", f"没有 oracle dev run（headroom.oracle.run_glob = {orc.get('run_glob') or '未登记'}，要求 role=oracle, eval_split=dev）：先量出理想解决瓶颈后的上界")
    elif len(bx) >= 2:
        ox = vals(ors, okey)
        if not ox: R.say("FAIL", f"oracle run 里读不到指标 {okey}")
        else:
            o = mean(ox); H = gain(o, b, dirn); nums.update(o=o, H=H)
            if len(ox) < 3: R.say("WARN", f"oracle 只有 {len(ox)} 个 seed（基线 {len(bx)} 个）：提升空间是拿来和 seed 噪声比的，补到 ≥3 个再信这个 H")   # fusion replay: 2 oracle seeds
            if H < 0: R.say("FAIL", f"瞄准的瓶颈判断错了：理想地解决它反而更差（oracle {o:.4f} vs 基线 {b:.4f}，H = {H:+.4f}）。这个方向做不出方法论文，改瓶颈或转分析")
            elif H < thr: R.say("FAIL", f"瞄准的瓶颈没有提升空间（oracle 只比基线好 H = {H:.4f} < max(min_effect {ctx.min_effect:g}, {k_sd:g}×sd_b {zero(sd_b):.4f}) = {thr:.4f}）：这个方向做不出方法论文，改瓶颈或转分析")
            else: R.say("PASS", f"提升空间：oracle {o:.4f} vs 基线 {b:.4f}，H = {H:.4f} ≥ {thr:.4f}（n_oracle={len(ox)}）")
    # 4. cheap fixes
    cfx = hr.get("cheap_fixes") or []
    if len(cfx) < 2: R.say("FAIL", f"便宜做法只登记了 {len(cfx)} 个（要求 ≥2：数据增强、更长训练、换大骨干……最便宜的替代做法）")
    best_c, best_name, gains = NAN, "", []
    for c in cfx:
        crs = sel(ctx.runs, ctx.root, role="cheap_fix", split="dev", pat=c.get("run_glob") or "")
        cx = vals(crs, c.get("key") or key)
        if not cx: R.say("FAIL", f"便宜做法 {c.get('name')}: 没有 dev run（run_glob = {c.get('run_glob') or '未登记'}，要求 role=cheap_fix, eval_split=dev）"); continue
        if len(cx) < 3: R.say("WARN", f"便宜做法 {c.get('name')}: 只有 {len(cx)} 个 seed，补到 ≥3 个")
        if len(bx) >= 2: gains.append((c.get("name") or "?", gain(mean(cx), b, dirn), len(cx)))
    if gains and not isn(H):
        gains.sort(key=lambda t: -t[1]); best_name, best_g = gains[0][0], gains[0][1]
        for nm, g, n in gains:
            R.say("INFO", f"便宜做法 {nm}: 提升 {g:+.4f}" + (f"，占提升空间 {g / H * 100:.0f}%" if H > 0 else "") + f"（n={n}）")
        if H >= thr:
            Rr = H - best_g; nums.update(R=Rr)
            if Rr < thr: R.say("FAIL", f"便宜做法 {best_name} 已经拿走 {best_g / H * 100:.0f}% 的提升空间，剩 R = {Rr:.4f} < {thr:.4f}：方法没有立足点（把 {best_name} 当成强基线重新算，或换瓶颈）")
            else: R.say("PASS", f"便宜做法之后的剩余空间 R = {Rr:.4f} ≥ {thr:.4f}（最强便宜做法 {best_name} 拿走 {best_g / H * 100:.0f}%）")
        else: R.say("INFO", "提升空间本身已不足，不再核对便宜做法后的剩余空间")
    # 5. splits
    sp_ = m.get("splits") or {}; dev_f = expand_files(root, (sp_.get("dev") or {}).get("files")); con = sp_.get("confirm") or {}; con_f = expand_files(root, con.get("files"))
    if not dev_f or not con_f: R.say("FAIL", f"splits.dev / splits.confirm 的 files 不能为空（dev {len(dev_f)} 个，confirm {len(con_f)} 个）")
    else:
        both = sorted(set(dev_f) & set(con_f))
        if both: R.say("FAIL", f"dev 与 confirm 有重叠文件 {both[:3]}：验证集必须是没参与开发的数据")
        elif not con.get("sha256"): R.say("FAIL", "splits.confirm.sha256 为空：先跑 `method_track.py init` 登记验证集哈希")
        elif any(not os.path.isfile(os.path.join(root, x)) for x in con_f): R.say("FAIL", "验证集文件缺失，哈希无法核对")
        elif files_sha(root, con.get("files")) != con["sha256"]: R.say("FAIL", "验证集文件和登记的 sha256 不一致：验证集被改过")
        else: R.say("PASS", f"dev {len(dev_f)} 个 / confirm {len(con_f)} 个文件互不相交，验证集哈希一致")
    check_no_early_confirm(R, ctx, "G1c")
    # 6. budget
    bud = m.get("budget") or {}; ih = bud.get("iter_hours"); mi = int(bud.get("max_iters") or 30)
    if ih in (None, ""): R.say("WARN", "budget.iter_hours 未填：一轮 dev 实验要几个小时？没有它算不出迭代预算（一轮要几天的任务不适合方法轨道）")
    else:
        try: R.say("INFO", f"dev 预算 = {float(ih):g} h/轮 × {mi} 轮 = {float(ih) * mi:g} GPU-小时")
        except ValueError: R.say("FAIL", "budget.iter_hours 不是数")
    # 7. bottleneck.md
    bp_ = ctx.path("bottleneck")
    if not os.path.exists(bp_): R.say("FAIL", f"{ctx.files['bottleneck']} 不存在（method_track.py init 建模板）")
    else:
        fl = bottleneck_fields(bp_); bad = []
        if not fl["瞄准的瓶颈"]: bad.append("没有写出瞄准的瓶颈")
        ev = [t for t in re.split(r"[\s,;，；`'\"()（）]+", fl["证据文件"]) if t and os.path.exists(os.path.join(root, re.sub(r"(:\d+)?(#.*)?$", "", t)))]
        if not ev: bad.append("证据文件（failure_slice / 误差分解的输出）不存在或没写")
        if not re.search(r"\d", fl["占基线误差的比例"]): bad.append("没有占基线误差的比例（数）")
        if bad: R.say("FAIL", f"{ctx.files['bottleneck']}：" + "；".join(bad))
        else: R.say("PASS", f"{ctx.files['bottleneck']}：瓶颈、证据文件 {ev[0]}、占基线误差 {fl['占基线误差的比例'][:30]}")
    return _verdict_g1c(R, nums, thr, ctx)

def _verdict_g1c(R, nums, thr=None, ctx=None):
    nums = nums or {}
    desc = (f"headroom H = {f(nums.get('H'))}, residual after cheap fixes R = {f(nums.get('R'))}, noise sd_b = {f(nums.get('sd_b'))}, min_effect = {ctx.min_effect:g}" if ctx else "方向未知，数字未算")
    if R.fails == 0: R.say("PASS", f"GO ({desc})")
    else: R.say("FAIL", f"NO-GO ({desc}；{R.fails} 项未过)")
    return R.fails

# ------------------------------------------------------------------ ideas
def cmd_ideas(root):
    R = Rep("G2m"); ctx = Ctx(root)
    if not need_state(R, ctx, "ideas-check"): return 0
    rows, _ = read_csv_rows(ctx.path("ideas"))
    if rows is None: R.say("WARN", f"{ctx.files['ideas']} 不存在（method_track.py init）：先列 ≥5 个想法、覆盖 ≥3 类，再动手"); return 0
    types = {str(r.get("type") or "").strip().lower() for r in rows}; types.discard("")
    odd = sorted(types - IDEA_TYPES)
    bad = False
    if len(rows) < 5: R.say("WARN", f"ideas.csv 只有 {len(rows)} 个想法（建议 ≥5）：第一个想法常常不是最好的，先列够再按 cheapest_test 排序"); bad = True
    if len(types & IDEA_TYPES) < 3: R.say("WARN", f"想法只覆盖 {len(types & IDEA_TYPES)} 类（建议 ≥3 类：data / objective / architecture / inference / training / other）"); bad = True
    if odd: R.say("WARN", f"type 不在 {sorted(IDEA_TYPES)} 里: {odd}"); bad = True
    for r in rows:
        miss = [c for c in ("mechanism", "cheapest_test", "kill_result") if not str(r.get(c) or "").strip()]
        if miss: R.say("WARN", f"想法 {r.get('id')}: 缺 {'/'.join(miss)}（没有 kill_result 的想法永远不会被杀死）"); bad = True
    if not bad: R.say("PASS", f"ideas.csv：{len(rows)} 个想法、{len(types)} 类，每个都有 mechanism / cheapest_test / kill_result")
    return 0

# ------------------------------------------------------------------ iterations
def iter_rows(ctx):
    rows, _ = read_csv_rows(ctx.path("iterations"))
    return rows

def iter_stats(ctx, row):
    """(runs, n, mean, sd, baseline mean, sd_b, n_b, gain, se) recomputed from the run dirs"""
    ors = sel(ctx.runs, ctx.root, role="ours", split="dev", pat=row.get("runs") or "")
    ox = vals(ors, ctx.key); brs = baseline_runs(ctx.runs, ctx.m, "dev"); bx = vals(brs, ctx.key)
    g = gain(mean(ox), mean(bx), ctx.dirn) if ox and len(bx) >= 1 else NAN
    return dict(runs=ors, n=len(ox), mean=mean(ox), sd=sd(ox), b=mean(bx), sd_b=sd(bx), n_b=len(bx), gain=g, se=se_of(sd(ox), len(ox), sd(bx), len(bx)))

def best_series(ctx, rows):
    """[(row, stats, best_so_far, improvement)] in file order"""
    out, best = [], NAN
    for r in rows:
        s = iter_stats(ctx, r); prev = 0.0 if isn(best) else best
        nb = best if isn(s["gain"]) else (s["gain"] if isn(best) else max(best, s["gain"]))
        out.append((r, s, nb, 0.0 if isn(s["gain"]) else (nb - prev if not isn(nb) else 0.0))); best = nb
    return out

def cmd_log_add(root, a):
    R = Rep("G2m"); ctx = Ctx(root)
    if not need_state(R, ctx, "log"): return R.fails
    if not need_direction(R, ctx): return R.fails
    if not re.match(r"^[A-Za-z]\w*$", a.id): R.say("FAIL", f"id {a.id!r}：用 I07 这样的短 id"); return R.fails
    row = dict(id=a.id, hypothesis=a.hypothesis, change=a.change, runs=a.runs)
    s = iter_stats(ctx, row)
    if not s["runs"]:
        R.say("FAIL", f"{a.runs} 匹配不到 role=ours, eval_split=dev 的 run：先跑完再登记；数字从 run 目录算，不手填"); return R.fails
    p = ctx.path("iterations"); rows = iter_rows(ctx) or []
    old = next((r for r in rows if r.get("id") == a.id), None)
    row.update(date=datetime.date.today().isoformat(), n_seeds=seeds_of(s["runs"]), dev_mean=f(s["mean"], 6), dev_sd="" if isn(s["sd"]) else f(s["sd"], 6),
               baseline_mean=f(s["b"], 6), gain=f(s["gain"], 6), se_gain="" if isn(s["se"]) else f(s["se"], 6),
               decision=a.decision or (old or {}).get("decision", ""), note=a.note if a.note is not None else (old or {}).get("note", ""), code_sha256=code_sha(root, ctx.st))
    if old is not None: rows[rows.index(old)] = row
    else: rows.append(row)
    ser = best_series(ctx, rows)
    for r, _, b, _ in ser: r["best_so_far"] = "" if isn(b) else f(b, 6)
    write_csv_rows(p, ITER_COLS, rows)
    R.say("PASS", f"{a.id}: n={s['n']} seeds，dev {s['mean']:.4f} ± {zero(s['sd']):.4f} vs 基线 {s['b']:.4f}，gain {s['gain']:+.4f}（se {zero(s['se']):.4f}），best_so_far {ser[[r['id'] for r, *_ in ser].index(a.id)][2]:+.4f}；共 {len(rows)} 轮，code {row['code_sha256'][:8]}"
          + ("（更新了已有行）" if old is not None else ""))
    if not row["decision"]: R.say("INFO", "decision 还空着：下一轮开始前补 keep / drop / revise")
    return 0

# ------------------------------------------------------------------ G2m
def dev_items_1_4(R, ctx):
    m = ctx.m; rows = iter_rows(ctx) or []
    # 1
    ids = {str(r.get("id")) for r in rows}
    globs = [(r.get("id"), run_glob(ctx.root, r.get("runs") or "")) for r in rows]
    untagged = [r for r in ctx.runs if not r.tagged()]
    if untagged: R.say("FAIL", f"run 没有 eval_split/role（args.json）：{runs_txt(untagged)}。每个 run 都要标是 dev 还是 confirm、是什么角色，否则没法证明验证集没被看过")
    stray = [r for r in ctx.runs if r.split == "dev" and r.role in ("ours", "ablation")
             and not any(os.path.normpath(r.dir) in g for _, g in globs) and str(r.iteration) not in ids]
    for r in stray[:5]: R.say("FAIL", f"未登记的 dev 实验 {r.rel}：每次尝试都要记（log add），否则挑出来的最好结果没有分母")
    if len(stray) > 5: R.say("FAIL", f"…另有 {len(stray) - 5} 个未登记的 dev 实验")
    if not untagged and not stray: R.say("PASS", f"所有 dev 的 ours/ablation run 都属于某个迭代行（{len(rows)} 轮），没有未标注的 run")
    # 2
    bad = 0
    for i, r in enumerate(rows):
        miss = [c for c in ("hypothesis", "change", "runs") if not str(r.get(c) or "").strip()]
        if miss: bad += 1; R.say("FAIL", f"迭代 {r.get('id')}: 缺 {'/'.join(miss)}（每轮先写假设再跑）"); continue
        if not any(os.path.isdir(p) for p in globs[i][1]): bad += 1; R.say("FAIL", f"迭代 {r.get('id')}: runs = {r.get('runs')} 匹配不到任何 run 目录")
        if i < len(rows) - 1 and not str(r.get("decision") or "").strip(): R.say("WARN", f"迭代 {r.get('id')}: 已有后续迭代但没有 decision（keep / drop / revise）")
    if rows and not bad: R.say("PASS", f"{len(rows)} 个迭代行都有 hypothesis / change / runs")
    # 3
    check_no_early_confirm(R, ctx, "G2m")
    # 4
    bud = m.get("budget") or {}; mi, stall = int(bud.get("max_iters") or 30), int(bud.get("stall") or 5); K = len(rows)
    if K > mi and not str(bud.get("extension") or "").strip():
        R.say("FAIL" if K > 1.5 * mi else "WARN", f"迭代 {K} 轮，超过 budget.max_iters = {mi}" + ("（>1.5 倍）" if K > 1.5 * mi else "") + "：停下，或在 budget.extension 写明继续的理由")
    elif K: R.say("PASS", f"迭代 {K} 轮，预算 {mi} 轮" + ("（已有 extension）" if K > mi else ""))
    if ctx.dirn is not None and K >= stall > 0:
        ser = best_series(ctx, rows)[-stall:]
        if all(isn(s["gain"]) or imp <= zero(s["se"]) for _, s, _, imp in ser):
            R.say("WARN", f"连续 {stall} 轮没有超过噪声的提升（best_so_far 的增量都 ≤ se_gain）：停下来换假设或收手")

def cmd_dev(root):
    R = Rep("G2m"); ctx = Ctx(root)
    if not need_state(R, ctx, "dev-check"): return R.fails
    if not need_direction(R, ctx): return R.fails
    m = ctx.m
    if not os.path.exists(ctx.path("iterations")): R.say("FAIL", f"{ctx.files['iterations']} 不存在（method_track.py init）"); return R.fails
    dev_items_1_4(R, ctx)
    fz = m.get("freeze") or {}
    if not fz:
        R.say("INFO", "尚未 freeze：迭代中。选定最优轮后 `method_track.py freeze --iteration Ixx`")
        return R.fails
    rows = iter_rows(ctx) or []; K = len(rows)
    row = next((r for r in rows if r.get("id") == fz.get("iteration")), None)
    # 5a
    st_ = None
    if row is None: R.say("FAIL", f"freeze.iteration = {fz.get('iteration')} 不在迭代日志里")
    else:
        st_ = iter_stats(ctx, row)
        if str(row.get("decision") or "").strip().lower() != "keep": R.say("FAIL", f"冻结的迭代 {row['id']} 的 decision 不是 keep（是 {row.get('decision') or '空'}）")
        elif seeds_of(st_["runs"]) < ctx.min_seeds and not str(ctx.res.get("seed_waiver") or "").strip():
            R.say("FAIL", f"冻结的迭代 {row['id']} 只有 {seeds_of(st_['runs'])} 个 seed（要求 ≥{ctx.min_seeds}）")
        else: R.say("PASS", f"冻结的迭代 {row['id']}：decision = keep，{seeds_of(st_['runs'])} 个 seed")
    # 5b
    if st_ is not None and st_["n"] >= 1:
        bias = 0.0 if K < 2 else zero(st_["se"]) * math.sqrt(2 * math.log(K)); adj = st_["gain"] - bias
        arith = f"gain_dev {st_['gain']:+.4f}（ours {st_['mean']:.4f}±{zero(st_['sd']):.4f} n={st_['n']} vs 基线 {st_['b']:.4f} n={st_['n_b']}），se_gain {zero(st_['se']):.4f}，K = {K}，bias = se×√(2 ln K) = {bias:.4f}，gain_adj = {adj:+.4f}，min_effect = {ctx.min_effect:g}"
        if adj >= ctx.min_effect: R.say("PASS", "扣掉挑选偏差后仍达标：" + arith)
        elif adj > 0: R.say("WARN", f"扣掉从 {K} 次尝试里挑最好的偏差后只剩 gain_adj = {adj:+.4f}，验证集上可能达不到 min_effect：加 dev seeds 或继续迭代。{arith}")
        else: R.say("FAIL", f"dev 上的提升不超过挑选噪声（gain_adj = {adj:+.4f} ≤ 0）。{arith}")
    # 5c
    comps = m.get("components") or []
    if not comps: R.say("WARN", "method.components 为空：把 prereg §6 的每个组件登记成 {name, ablation_glob}，才能核对每个组件在 dev 上去掉是否掉点")
    elif st_ is not None:
        for c in comps:
            ars = sel(ctx.runs, ctx.root, role="ablation", split="dev", pat=c.get("ablation_glob") or "")
            ax = vals(ars, ctx.key)
            if not ax: R.say("FAIL", f"组件 {c.get('name')}: 没有 dev 消融 run（ablation_glob = {c.get('ablation_glob') or '未登记'}）"); continue
            drop = gain(st_["mean"], mean(ax), ctx.dirn); se = se_of(st_["sd"], st_["n"], sd(ax) if len(ax) >= 2 else st_["sd"], len(ax))
            if isn(se) or se == 0 or drop > 2 * se: R.say("PASS", f"组件 {c.get('name')}: 去掉后掉 {drop:+.4f} > 2×se {2 * zero(se):.4f}")
            else: R.say("FAIL", f"组件 {c.get('name')} 在 dev 上去掉不掉点（掉 {drop:+.4f} ≤ 2×se {2 * se:.4f}）：删掉它再冻结（方法越简单越好）")
    # 5d
    mech = m.get("mechanism") or {}
    if not mech or not str(mech.get("desc") or "").strip(): R.say("WARN", "method.mechanism 未登记：{desc, run_glob|file, key, expect}。提升为什么发生？没有机制检验，赢了也只是个数")
    else:
        v = None
        try:
            if mech.get("file"): v = float(get_path(json.load(io.open(os.path.join(root, mech["file"]), encoding="utf-8")), mech.get("key")))
            else:
                xs = vals(sel(ctx.runs, ctx.root, pat=mech.get("run_glob") or ""), mech.get("key"))
                v = mean(xs) if xs else None
        except Exception: v = None
        ex = str(mech.get("expect") or "").strip()
        mm = re.match(r"^(>=|<=|>|<)\s*(-?[\d.]+(?:e-?\d+)?)$", ex)
        if v is None or isn(v): R.say("FAIL", f"机制检验 {mech.get('desc')[:30]}: 读不到 {mech.get('key')}（file / run_glob 不对或还没跑）")
        elif ex in ("+", "-") or mm:
            ok = (v > 0) if ex == "+" else (v < 0) if ex == "-" else {">=": v >= float(mm.group(2)), "<=": v <= float(mm.group(2)), ">": v > float(mm.group(2)), "<": v < float(mm.group(2))}[mm.group(1)]
            R.say("PASS" if ok else "FAIL", f"机制检验「{str(mech['desc'])[:40]}」: {mech.get('key')} = {v:.4f}，预期 {ex}" + ("" if ok else "。提升不是因为你说的原因：改机制叙述或换方法"))
        else: R.say("FAIL", f"mechanism.expect = {ex!r}：用 + / - / >=x / <=x / >x / <x")
    # 5e
    bname = ((m.get("baseline") or {}).get("name") or "").strip()
    trows, _ = read_csv_rows(ctx.path("tuning"))
    if trows is None: R.say("FAIL", f"基线没有得到同等调参预算：{ctx.files['tuning']} 不存在")
    else:
        mine = [r for r in trows if str(r.get("method") or "").strip().lower() == bname.lower()]
        pub = [r for r in mine if str(r.get("trial") or "").strip() == "published_config"]; n = len(mine) - len(pub)
        need = min(K, 10)
        if n >= need or (pub and n >= 5): R.say("PASS", f"基线 {bname} 调参 {n} 次" + ("（含 published_config）" if pub else "") + f"，迭代 {K} 轮")
        else: R.say("FAIL", f"基线没有得到同等调参预算：{bname} 只调了 {n} 次（要求 ≥ min(K,10) = {need}，或 published_config + ≥5 次）；基线数字用它调参后最好的 dev 配置")
        dv = []
        for r in mine:
            try: dv.append(float(r.get("dev_metric")))
            except (TypeError, ValueError): pass
        if dv and st_ is not None and not isn(st_["b"]):
            bt = max(dv) if ctx.dirn == "higher" else min(dv)
            if gain(bt, st_["b"], ctx.dirn) > 2 * zero(st_["sd_b"]) and gain(bt, st_["b"], ctx.dirn) > 0:
                R.say("WARN", f"调参表里有比基线 runs 更好的 dev 配置（{bt:.4f} vs {st_['b']:.4f}）：基线数字应是它最好的调参配置的多 seed 复现")
    # 5f
    cur = code_sha(root, ctx.st)
    if cur != fz.get("code_sha256"): R.say("FAIL", f"冻结后代码改过（现 {cur[:8]} vs 冻结 {str(fz.get('code_sha256'))[:8]}）：重新登记一轮迭代并重新 freeze")
    else: R.say("PASS", f"代码与冻结时一致（{cur[:8]}）")
    return R.fails

# ------------------------------------------------------------------ freeze
def cmd_freeze(root, it):
    R = Rep("G2m"); ctx = Ctx(root)
    if not need_state(R, ctx, "freeze"): return R.fails
    if not need_direction(R, ctx): return R.fails
    if any(r.split == "confirm" for r in ctx.runs): R.say("FAIL", "已经有 confirm run：验证集看过之后不能再 freeze / 重新 freeze（用新的验证集重来）"); return R.fails
    q = Rep("G2m", quiet=True); dev_items_1_4(q, ctx)
    if q.fails:
        for l in q.lines:
            if l.startswith("[FAIL]"): print(l)
        R.say("FAIL", "dev-check 第 1–4 项未过，拒绝 freeze"); return R.fails
    rows = iter_rows(ctx) or []; row = next((r for r in rows if r.get("id") == it), None)
    if row is None: R.say("FAIL", f"迭代 {it} 不在 {ctx.files['iterations']}"); return R.fails
    if str(row.get("decision") or "").strip().lower() != "keep": R.say("FAIL", f"迭代 {it} 的 decision 不是 keep：先 `log add --id {it} … --decision keep`"); return R.fails
    s = iter_stats(ctx, row); K = len(rows)
    if s["n"] < 1: R.say("FAIL", f"迭代 {it} 没有 dev run"); return R.fails
    bias = 0.0 if K < 2 else zero(s["se"]) * math.sqrt(2 * math.log(K)); adj = s["gain"] - bias
    sha = code_sha(root, ctx.st)
    fz = dict(date=datetime.datetime.now().isoformat(timespec="seconds"), iteration=it, code_sha256=sha, dev_gain=round(s["gain"], 6), se_gain=round(zero(s["se"]), 6), k_iters=K, bias=round(bias, 6), gain_adj=round(adj, 6))
    state_set(os.path.join(root, "research-state.yaml"), ["freeze"], fz)
    R.say("PASS", f"已冻结 {it}：code {sha[:8]}，dev_gain {s['gain']:+.4f}，se {zero(s['se']):.4f}，K = {K}，bias {bias:.4f}，gain_adj {adj:+.4f}（min_effect {ctx.min_effect:g}）")
    if adj < ctx.min_effect: R.say("WARN", "gain_adj 低于 min_effect：验证集上可能达不到。可以继续迭代；冻结后只要没有 confirm run，还能再 freeze")
    print(f"\n贴进 prereg.md（再 `t2p.py lock`）：\n  §1 假设：冻结的方法 = 迭代 {it}（{row.get('change')}）；freeze: {sha[:8]}\n"
          f"  §5 基线：与方法同等调参预算（dev 上 ≥ min({K},10) 次），用调参后最好的 dev 配置\n"
          f"  §7 成功标准：在验证集（{', '.join(((ctx.m.get('splits') or {}).get('confirm') or {}).get('files') or [])[:60]}）上只评测一次：方向感知的 (方法 − 最强调参基线) ≥ {ctx.min_effect:g} 且 > 2×se，各 ≥ {ctx.min_seeds} seeds\n"
          f"  训练/评测脚本把 code_sha256 = {sha} 写进每个 confirm run 的 args.json（`method_track.py code-sha` 可重算）")
    return R.fails

# ------------------------------------------------------------------ G4m
VOLATILE = {"seed", "eval_split", "role", "iteration", "code_sha256", "out", "out_dir", "output", "output_dir", "exp", "run_id", "name", "date", "time", "timestamp", "log_dir", "ckpt", "hardware", "host", "config_hash"}

def cfg_hash(r):
    a = r.args
    if a.get("config_hash"): return str(a["config_hash"])
    core = {k: v for k, v in a.items() if k not in VOLATILE}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:8]

def cmd_confirm(root, prereg):
    R = Rep("G4m"); ctx = Ctx(root)
    if not need_state(R, ctx, "confirm-check"): return R.fails
    if not need_direction(R, ctx): return R.fails
    m = ctx.m; fz = m.get("freeze") or {}; conf = [r for r in ctx.runs if r.split == "confirm"]
    if not conf: R.say("FAIL", "没有 eval_split=confirm 的 run：先 freeze、锁预注册，再在验证集上评测一次"); return R.fails
    if not fz: R.say("FAIL", "还没有 method.freeze：验证集在冻结前被评测了（`method_track.py freeze`）"); return R.fails
    fts, fsha = to_ts(fz.get("date")), str(fz.get("code_sha256") or "")
    # 1
    pp = os.path.join(root, prereg); locked = (((ctx.st.get("gates") or {}).get("G2") or {}).get("prereg_sha256")) or ""
    if not os.path.exists(pp) or not locked: R.say("FAIL", "prereg.md 没有锁定（gates.G2.prereg_sha256 为空）：先把冻结的方法写进 prereg 再 `t2p.py lock`，然后才能看验证集")
    else:
        txt = io.open(pp, encoding="utf-8").read()
        if fsha[:8] not in txt: R.say("FAIL", f"prereg.md 里没有 freeze: {fsha[:8]}：预注册没有写入冻结的方法")
        elif hashlib.sha256(txt.encode("utf-8")).hexdigest() != locked: R.say("FAIL", "prereg.md 与锁定的 sha256 不一致：锁后被改过")
        elif fts is not None and os.path.getmtime(pp) < fts - 1: R.say("FAIL", "prereg.md 最后修改早于 freeze：预注册在冻结之前锁的，不含冻结的方法（先 freeze 再锁）")
        else: R.say("PASS", f"prereg 已锁定且含 freeze: {fsha[:8]}，晚于 freeze")
    # 2
    bad = 0
    for r in conf:
        why = []
        if r.mtime is None: why.append("没有 eval 文件")
        elif fts is not None and r.mtime <= fts: why.append("评测早于 freeze")
        if r.code is None: why.append("args.json 没有 code_sha256")
        elif r.code != fsha: why.append(f"code_sha256 {str(r.code)[:8]} ≠ 冻结的 {fsha[:8]}")
        if why: bad += 1; R.say("FAIL", f"confirm run {r.rel}: " + "；".join(why))
    cur = code_sha(root, ctx.st)
    if cur != fsha: bad += 1; R.say("FAIL", f"当前代码 {cur[:8]} ≠ 冻结的 {fsha[:8]}：验证集结果不是冻结代码产生的")
    if not bad: R.say("PASS", f"{len(conf)} 个 confirm run 都晚于 freeze 且 code_sha256 = {fsha[:8]}")
    # 3
    cm = m.get("confirm") or {}; regd = int(cm.get("registered_looks") or 1); looks = list(cm.get("looks") or [])
    known = {str(l.get("id")) for l in looks if isinstance(l, dict)}
    variants = sorted({f"{r.method}:{cfg_hash(r)}" for r in conf if r.role == "ours"})
    new = [v for v in variants if v not in known]
    if new:
        looks += [{"id": v, "first_seen": datetime.datetime.now().isoformat(timespec="seconds")} for v in new]
        state_set(os.path.join(root, "research-state.yaml"), ["confirm", "looks"], looks)
    n_looks = len({str(l.get("id")) for l in looks if isinstance(l, dict)})
    if n_looks > regd: R.say("FAIL", f"验证集看了 {n_looks} 次（登记 {regd} 次）：结论已被验证集调过，换新的验证集或如实报告。看过的变体 {sorted(str(l.get('id')) for l in looks)[:4]}")
    else: R.say("PASS", f"验证集看了 {n_looks} 次，登记 {regd} 次（登记簿 method.confirm.looks）")
    bcfg = {}
    for r in conf:
        if r.role == "baseline": bcfg.setdefault(r.method, set()).add(cfg_hash(r))
    for nm, hs in bcfg.items():
        if len(hs) > 1: R.say("WARN", f"基线 {nm} 在验证集上有 {len(hs)} 种配置：只能用 baseline_tuning.csv 里 dev 最优的那一种")
    # 4
    ors = [r for r in conf if r.role == "ours"]; brs = baseline_runs(ctx.runs, m, "confirm")
    ox, bx = vals(ors, ctx.key), vals(brs, ctx.key)
    waiver = str(ctx.res.get("seed_waiver") or "").strip()
    if min(len(ox), len(bx)) < ctx.min_seeds and not waiver:
        R.say("FAIL", f"验证集上 ours {len(ox)} 个、基线 {len(bx)} 个 run（各要求 ≥{ctx.min_seeds}）"); verdict = None
    elif len(ox) < 2 or len(bx) < 2: R.say("FAIL", "验证集 run 太少，估不出 se"); verdict = None
    else:
        g = gain(mean(ox), mean(bx), ctx.dirn); se = se_of(sd(ox), len(ox), sd(bx), len(bx))
        verdict = "confirmed" if (g >= ctx.min_effect and g > 2 * se) else "not_confirmed"
        arith = f"confirm gain {g:+.4f}（ours {mean(ox):.4f} n={len(ox)} vs 基线 {mean(bx):.4f} n={len(bx)}），se {se:.4f}，min_effect {ctx.min_effect:g}，2×se {2 * se:.4f}"
        out = str(m.get("outcome") or "").strip()
        if not out: R.say("FAIL", f"method.outcome 为空：数字说 {verdict}。{arith}")
        elif out not in ("confirmed", "not_confirmed"): R.say("FAIL", f"method.outcome = {out!r}：只能是 confirmed | not_confirmed")
        elif out != verdict: R.say("FAIL", f"method.outcome = {out}，但数字说 {verdict}。{arith}")
        else: R.say("PASS", f"{verdict}：{arith}")
        if verdict == "not_confirmed":
            print("两个诚实的出口：\n  (a) 把 project.paper_type 改成 analysis：dev 日志 + headroom 数字 + 这次验证集结果就是一篇分析论文的材料；\n  (b) 拿一个新的验证集（旧的已经烧掉），method.splits.confirm 换文件、`init --force`、回到 dev 迭代。")
        # 5
        dg = fz.get("dev_gain")
        if dg is not None: R.say("INFO", f"收缩：dev 提升 {float(dg):+.4f}（从 {fz.get('k_iters')} 次尝试里选出，扣偏差后 {fz.get('gain_adj')}）→ 验证集 {g:+.4f}" + (f"，保留 {g / float(dg) * 100:.0f}%" if float(dg) else "") + "。写进论文的局限：K、dev→confirm 收缩、验证集看了几次")
    return R.fails

# ------------------------------------------------------------------ status / code-sha
def cmd_status(root):
    ctx = Ctx(root); R = Rep("G1c", quiet=True)
    if not need_state(R, ctx, "status"): print("\n".join(R.lines)); return 1
    m = ctx.m
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): cmd_headroom(root)
    verdict = next((l for l in buf.getvalue().splitlines() if "G1c: GO" in l or "G1c: NO-GO" in l), "?")
    rows = (iter_rows(ctx) or []) if os.path.exists(ctx.path("iterations")) and ctx.dirn else []
    ser = best_series(ctx, rows) if rows and ctx.dirn else []
    best = max([b for _, _, b, _ in ser if not isn(b)] or [NAN]); fz = m.get("freeze") or {}
    cm = m.get("confirm") or {}
    print(f"== method track: {os.path.basename(root)} ==")
    print(f"G1c        {verdict.split('G1c: ')[-1]}")
    print(f"迭代       K = {len(rows)}（预算 {(m.get('budget') or {}).get('max_iters')}），最好 dev gain {f(best)}，min_effect {ctx.min_effect:g}")
    print(f"冻结       " + (f"{fz.get('iteration')} @ {fz.get('date')}，code {str(fz.get('code_sha256'))[:8]}，gain_adj {fz.get('gain_adj')}" if fz else "未冻结"))
    print(f"验证集     confirm run {len([r for r in ctx.runs if r.split == 'confirm'])} 个，看过 {len(cm.get('looks') or [])} 次 / 登记 {cm.get('registered_looks')}")
    print(f"结论       {m.get('outcome') or '（未定）'}")
    return 0

def main():
    ap = argparse.ArgumentParser(description="method track: headroom / dev log / freeze / confirm")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("init", "headroom", "ideas-check", "dev-check", "freeze", "confirm-check", "status", "code-sha", "log"):
        p = sub.add_parser(n); p.add_argument("--project", default=".")
        if n == "init": p.add_argument("--force", action="store_true")
        if n == "freeze": p.add_argument("--iteration", required=True)
        if n == "confirm-check": p.add_argument("--prereg", default="prereg.md")
        if n == "log":
            p.add_argument("action", choices=["add"]); p.add_argument("--id", required=True); p.add_argument("--hypothesis", required=True); p.add_argument("--change", required=True)
            p.add_argument("--runs", required=True); p.add_argument("--decision", choices=["keep", "drop", "revise"]); p.add_argument("--note")
    a = ap.parse_args(); root = os.path.abspath(a.project)
    try: import yaml  # noqa: F401
    except ImportError: print("[FAIL] method: 需要 pyyaml"); sys.exit(1)
    fails = {"init": lambda: cmd_init(root, a.force), "headroom": lambda: cmd_headroom(root), "ideas-check": lambda: cmd_ideas(root), "dev-check": lambda: cmd_dev(root),
             "freeze": lambda: cmd_freeze(root, a.iteration), "confirm-check": lambda: cmd_confirm(root, a.prereg), "status": lambda: cmd_status(root),
             "log": lambda: cmd_log_add(root, a), "code-sha": lambda: print(code_sha(root, load_state(root) or {})) or 0}[a.cmd]()
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
