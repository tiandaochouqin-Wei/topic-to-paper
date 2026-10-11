# -*- coding: utf-8 -*-
"""P3/P4 — remote experiment bundle: pack, verify, ingest. For the "Claude writes scripts, user uploads and runs" workflow. Run by Claude.

  python bundle.py make   [--state research-state.yaml] [--out bundle/]      build the upload package from state.bundle + prereg
  python bundle.py check  [--state ...]                                        G3 half: matrix covers prereg §5/§6, seeds, no leak flags, inputs
  python bundle.py ingest <results_*.tar.gz> [--state ...]                     unpack what collect.sh sent back: <code>/runs/<run>/* -> <project>/runs/<run>/,
                                                                               bundle-level files (smoke_report, failed.txt, slurm_*.out) -> bundle/returned_<date>/
  python bundle.py tables [--state ...] [--runs runs]                          after ingest: runs/*/eval.json -> results/main.csv + ablation.csv (+ results/main.md
                                                                               convention note from prereg §3/§4) via state.results.metric_map; hardware from
                                                                               hardware.json; never hand-typed

state.bundle (see templates/research-state.yaml):
  code_dir, entry ("python train.py --exp {run} {args}"), eval ("python eval.py --exp {runs}"), post (optional, e.g. preds dump),
  env (requirements.txt | environment.yml), python_min, data: [{name, remote, inputs: [...]}], scheduler: bash|slurm,
  slurm: {partition, gres, time, mem, cpus, max_parallel, modules: [], conda: ""}, smoke: {args: "--epochs 1", runs: [ref]},
  require_gpu (default true; false = CUDA absence is INFO in check_env, for CPU-only pipelines and the regression tests),
  data[i].clip_glob: "*" = every sub-directory is a clip; "." = the data directory itself holds the inputs (no clip level)
  matrix: {seeds: [...], ref: {name, args}, baselines: {name: args}, ablations: {name: args}, extra: {name: args}, seed_flag: "--seed {seed}", seeded: [names]}

Bundle contents:
  README.md        what to run, in order, and what to send back
  check_env.py     CUDA / GPU / disk / every data input exists -> exits non-zero on any miss (silent-fallback guard, remote edition)
  run_one.sh       one run: records hardware.json + git/sha manifest, then entry; eval + post afterwards
  smoke.sh         one short run on the reference config, then eval; proves the pipeline end-to-end in minutes
  run_all.sh       full matrix (bash: sequential, restartable; slurm: check_env then sbatch jobs.sbatch — an array job, one task per matrix row,
                   finished runs (eval.json present) exit at once so the array is restartable too)
  sbatch_local.sh  slurm only: a serial emulator of `sbatch` for dry-running jobs.sbatch on a workstation (what the regression suite uses)
  matrix.csv       run_id, role, method/ablation, seed, args — the single source the tables step reads back
  collect.sh       tar runs/*/{args,log,eval,hardware}.json + stats.npz + preds/ (no checkpoints) -> results_<date>.tar.gz
  manifest.json    sha256 of every code file and of prereg.md; tables step refuses results whose manifest differs
"""
import argparse, csv, hashlib, io, json, os, re, sys, datetime, tarfile
for _s in (sys.stdout, sys.stderr):   # Windows consoles/pipes default to GBK, which cannot print the check marks / minus signs used below
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

FAILS = 0
def say(st, g, msg):
    global FAILS
    if st == "FAIL": FAILS += 1
    print(f"[{st}] {g}: {msg}")

def load_state(p):
    import yaml
    return yaml.safe_load(io.open(p, encoding="utf-8")) or {}

def section(md, name):
    m = re.search(r"^(#{1,4})\s*\d*\.?\s*" + re.escape(name) + r"\b.*?$", md, re.M | re.I)
    if not m: return ""
    depth = len(m.group(1)); rest = md[m.end():]
    nxt = re.search(r"^#{1,%d}\s" % depth, rest, re.M)
    return rest[:nxt.start()] if nxt else rest

def table_first_col(txt):
    out = []
    for ln in txt.splitlines():
        if ln.strip().startswith("|") and not set(ln.replace("|", "").strip()) <= set("-: "):
            c = ln.strip().strip("|").split("|")[0].strip().strip("*`")
            if c and c.lower() not in ("name", "名称", "remove", "去掉/替换什么", "ablation", "method", "方法"): out.append(c)
    return out

def norm(s): return re.sub(r"[^a-z0-9]", "", s.lower())
def fuzzy_in(item, pool):
    n = norm(item); return any(n == norm(p) or n in norm(p) or norm(p) in n for p in pool if norm(p))

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

# ------------------------------------------------------------------ matrix
def build_matrix(b):
    m = b.get("matrix") or {}; seeds = m.get("seeds") or [0]; sf = m.get("seed_flag", "--seed {seed}")
    seeded = set(m.get("seeded") or [m.get("ref", {}).get("name", "ref")])
    rows = []
    def add(role, name, args):
        for s in (seeds if name in seeded else [seeds[0]]):
            rid = f"{name}_s{s}" if name in seeded else name
            rows.append({"run_id": rid, "role": role, "name": name, "seed": s, "args": f"{args} {sf.format(seed=s)}".strip()})
    ref = m.get("ref") or {}
    if ref: add("ref", ref.get("name", "ref"), ref.get("args", ""))
    for k, v in (m.get("baselines") or {}).items(): add("baseline", k, v)
    for k, v in (m.get("ablations") or {}).items(): add("ablation", k, v)
    for k, v in (m.get("extra") or {}).items(): add("extra", k, v)
    return rows

# ------------------------------------------------------------------ make
def make(a):
    st = load_state(a.state); b = st.get("bundle") or {}
    if not b: say("FAIL", "bundle", "state 无 bundle: 段（模板见 templates/research-state.yaml）"); sys.exit(1)
    root = os.path.dirname(os.path.abspath(a.state)); out = os.path.join(root, a.out); os.makedirs(out, exist_ok=True)
    code_dir = os.path.join(root, b.get("code_dir", "code")); aud = st.get("audits") or {}
    cdn = os.path.basename(os.path.normpath(code_dir)) or "code"       # name of the code dir INSIDE the bundle
    rows = build_matrix(b)
    with open(os.path.join(out, "matrix.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["run_id", "role", "name", "seed", "args"], lineterminator="\n"); w.writeheader(); w.writerows(rows)   # LF only: jobs.sbatch reads this back on Linux
    # manifest: code + prereg
    man = {"created": datetime.date.today().isoformat(), "files": {}}
    for dp, _, fs in os.walk(code_dir):
        for fn in fs:
            if fn.endswith((".py", ".yaml", ".yml", ".txt", ".sh", ".json")) and "runs" not in dp.replace("\\", "/").split("/") and "__pycache__" not in dp:
                p = os.path.join(dp, fn); man["files"][os.path.relpath(p, code_dir).replace("\\", "/")] = sha(p)
    pr = os.path.join(root, "prereg.md")
    if os.path.exists(pr): man["prereg_sha256"] = sha(pr)
    json.dump(man, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    inputs = aud.get("inputs") or []; data = b.get("data") or []
    # check_env.py
    chk = f'''# -*- coding: utf-8 -*-
"""Remote pre-flight. Exits non-zero on ANY missing piece — never let a run start half-blind."""
import os, sys, json, shutil, subprocess, importlib, fnmatch
bad = 0
def ok(c, msg):
    global bad
    print(("[OK]   " if c else "[MISS] ") + msg); bad += (0 if c else 1)
v = sys.version_info; ok(v >= tuple(int(x) for x in "{b.get('python_min', '3.9')}".split(".")), f"python {{v.major}}.{{v.minor}}")
for mod in {json.dumps(b.get('import_check') or ['numpy', 'torch'])}:
    try: importlib.import_module(mod); ok(True, f"import {{mod}}")
    except Exception as ex: ok(False, f"import {{mod}}: {{ex}}")
REQUIRE_GPU = {bool(b.get('require_gpu', True))} and "--no-gpu" not in sys.argv   # --no-gpu: Slurm login nodes have no GPU; the job re-checks
try:
    import torch
    if torch.cuda.is_available(): ok(True, "CUDA available")
    elif REQUIRE_GPU: ok(False, "CUDA available")
    else: print("[INFO] no CUDA here (" + ("--no-gpu: checked again inside the job" if "--no-gpu" in sys.argv else "bundle.require_gpu = false, CPU run accepted") + ")")
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            p = torch.cuda.get_device_properties(i); ok(p.total_memory / 2**30 >= {b.get('min_vram_gb', 8)}, f"GPU{{i}} {{p.name}} {{p.total_memory/2**30:.0f}} GB (need >= {b.get('min_vram_gb', 8)})")
except Exception as ex:
    if REQUIRE_GPU: ok(False, f"torch/cuda: {{ex}}")
    else: print(f"[INFO] torch unavailable ({{ex}}); bundle.require_gpu = false")
free = shutil.disk_usage(".").free / 2**30; ok(free >= {b.get('min_disk_gb', 20)}, f"free disk {{free:.0f}} GB (need >= {b.get('min_disk_gb', 20)})")
DATA = {json.dumps([{"name": d.get("name"), "path": d.get("remote"), "inputs": d.get("inputs") or inputs, "clip_glob": d.get("clip_glob", "*")} for d in data], ensure_ascii=False)}
for d in DATA:   # remote 里的 ~ 与 $VAR 要在服务器上展开，否则路径存在也会报 MISS
    d["path"] = os.path.expanduser(os.path.expandvars(d["path"] or ""))
for d in DATA:
    ok(os.path.isdir(d["path"]), f"data {{d['name']}} at {{d['path']}}")
    if os.path.isdir(d["path"]):
        subs = [d["path"]] if d["clip_glob"] in ("", ".") else ([os.path.join(d["path"], s) for s in sorted(os.listdir(d["path"])) if os.path.isdir(os.path.join(d["path"], s)) and fnmatch.fnmatch(s, d["clip_glob"])] or [d["path"]])
        ok(len(subs) > 0, f"  {{len(subs)}} clips match '{{d['clip_glob']}}'")
        for inp in d["inputs"]:
            miss = [s for s in subs[:{b.get('check_first_n', 50)}] if not os.path.exists(os.path.join(s, inp))]
            ok(not miss, f"  input '{{inp}}' present in {{len(subs[:{b.get('check_first_n', 50)}])-len(miss)}}/{{len(subs[:{b.get('check_first_n', 50)}])}} clips" + (f" — first missing: {{os.path.basename(miss[0])}}" if miss else ""))
for f in ["manifest.json", "matrix.csv", "run_one.sh"]: ok(os.path.exists(f), f"bundle file {{f}}")
print("\\n" + ("ENV OK" if bad == 0 else f"{{bad}} MISSING — do not run"))
sys.exit(0 if bad == 0 else 1)
'''
    io.open(os.path.join(out, "check_env.py"), "w", encoding="utf-8").write(chk)
    # run_one.sh
    entry = b.get("entry", "python train.py --exp {run} {args}"); ev = b.get("eval", ""); post = b.get("post", "")
    # 路径里的 ~ 在双引号里不会被 bash 展开，所以生成时换成 ${HOME}；训练脚本可以直接用这些环境变量当默认值
    data_env = "\n".join(f'export {d["name"].upper()}_PATH="{re.sub(r"^~(?=/|$)", "${HOME}", str(d.get("remote", "")))}"' for d in data)
    r1 = f'''#!/usr/bin/env bash
# one run: $1 = run_id, $2.. = args. Records hardware + manifest before training; eval + post after.
set -euo pipefail
RUN="$1"; shift; ARGS="$*"
cd "$(dirname "$0")/{cdn}"
{data_env}
mkdir -p "runs/$RUN"
PYBIN="${{PYTHON:-python}}"   # export PYTHON=python3 on servers where `python` is absent
"$PYBIN" - "$RUN" <<'PY'
import json, sys, subprocess, platform, datetime
r = sys.argv[1]; hw = {{"host": platform.node(), "time": datetime.datetime.now().isoformat(timespec="seconds")}}
try:
    import torch; hw["hardware"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"; hw["torch"] = torch.__version__; hw["cuda"] = torch.version.cuda
except Exception as ex: hw["hardware"] = "unknown: " + str(ex)
try: hw["nvidia_smi"] = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
except Exception: pass
json.dump(hw, open(f"runs/{{r}}/hardware.json", "w"), indent=1)
PY
cp ../manifest.json "runs/$RUN/manifest.json"
echo "== train $RUN :: $ARGS"
{entry.replace('{run}', '"$RUN"').replace('{args}', '$ARGS')} 2>&1 | tee "runs/$RUN/train.log"
{('echo "== eval $RUN"; ' + ev.replace('{runs}', '"$RUN"').replace('{run}', '"$RUN"') + ' 2>&1 | tee "runs/$RUN/eval.log"') if ev else 'echo "(no eval command configured)"'}
{(post.replace('{runs}', '"$RUN"').replace('{run}', '"$RUN"') + ' 2>&1 | tee -a "runs/$RUN/eval.log"') if post else ''}
echo "== done $RUN"
'''
    io.open(os.path.join(out, "run_one.sh"), "w", encoding="utf-8", newline="\n").write(r1)
    # smoke.sh
    sm = b.get("smoke") or {}; sm_args = sm.get("args", "--epochs 1"); ref = (b.get("matrix") or {}).get("ref") or {}
    if sm.get("eval"):   # smoke-only eval command (e.g. one condition) so the smoke test stays minutes long
        r1s = r1.replace(ev.replace('{runs}', '"$RUN"').replace('{run}', '"$RUN"'), sm["eval"].replace('{runs}', '"$RUN"').replace('{run}', '"$RUN"')) if ev else r1
        io.open(os.path.join(out, "run_one_smoke.sh"), "w", encoding="utf-8", newline="\n").write(r1s)
    sm_runs = sm.get("runs") or [ref.get("name", "ref")]
    by_name = {}
    for r in rows: by_name.setdefault(r["name"], r)          # first row = seeds[0]
    lines = ["#!/usr/bin/env bash", "# smoke: short run(s) on the reference config, then eval. Minutes, not hours. Send back smoke_report.txt.", "set -euo pipefail", 'cd "$(dirname "$0")"', '"${PYTHON:-python}" check_env.py | tee smoke_report.txt']
    for n in sm_runs:
        r = by_name.get(n) or {"args": ""}
        lines.append(f'bash {"run_one_smoke.sh" if sm.get("eval") else "run_one.sh"} _smoke_{n} {r["args"]} {sm_args} 2>&1 | tail -40 | tee -a smoke_report.txt')
    lines.append('"${PYTHON:-python}" - <<\'PY\' | tee -a smoke_report.txt\nimport json, glob, os\nfor d in sorted(glob.glob("%s/runs/_smoke_*")):\n    have = {f: os.path.exists(os.path.join(d, f)) for f in ["args.json", "log.json", "eval.json", "hardware.json"]}\n    print(os.path.basename(d), have, "log entries:", len(json.load(open(os.path.join(d, "log.json")))) if have["log.json"] else 0)\nPY' % cdn)
    lines.append('echo "SMOKE DONE — send smoke_report.txt back"')
    io.open(os.path.join(out, "smoke.sh"), "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    # run_all.sh / slurm
    sched = b.get("scheduler", "bash")
    if sched == "slurm":
        sl = b.get("slurm") or {}
        mods = "\n".join(f"module load {m}" for m in (sl.get("modules") or []))
        conda = (f'source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate {sl["conda"]} || echo "conda activate {sl["conda"]} failed"') if sl.get("conda") else ""
        jname = re.sub(r"[^A-Za-z0-9_.-]", "", str(st.get("project", {}).get("title", "")))[:12] or "t2p"
        sb = f"""#!/usr/bin/env bash
#SBATCH -J {jname}
#SBATCH -p {sl.get('partition', 'gpu')}
#SBATCH --gres={sl.get('gres', 'gpu:1')}
#SBATCH -t {sl.get('time', '12:00:00')}
#SBATCH --mem={sl.get('mem', '32G')}
#SBATCH -c {sl.get('cpus', 8)}
#SBATCH --array=0-{len(rows)-1}%{sl.get('max_parallel', 4)}
#SBATCH -o slurm_%A_%a.out
# one array task = one matrix.csv row. Finished runs (eval.json present) exit at once, so re-submitting after a
# partial failure only runs what is missing; failures are appended to failed.txt. Dry-run without a cluster:
#   SBATCH="bash sbatch_local.sh" bash run_all.sh
set -uo pipefail
{mods}
{conda}
cd "$SLURM_SUBMIT_DIR"
PYBIN="${{PYTHON:-python}}"
LINE=$("$PYBIN" -c 'import csv, sys; r = list(csv.DictReader(open("matrix.csv", encoding="utf-8")))[int(sys.argv[1])]; print(r["run_id"], r["args"])' "$SLURM_ARRAY_TASK_ID")
RUN=${{LINE%% *}}; ARGS=${{LINE#* }}
if [ -f "{cdn}/runs/$RUN/eval.json" ]; then echo "skip $RUN (eval.json present)"; exit 0; fi
"$PYBIN" check_env.py || {{ echo "FAILED $RUN (check_env on $(hostname))" >> failed.txt; exit 1; }}
echo "task $SLURM_ARRAY_TASK_ID -> $RUN :: $ARGS"
bash run_one.sh "$RUN" $ARGS || {{ echo "FAILED $RUN" >> failed.txt; exit 1; }}
"""
        io.open(os.path.join(out, "jobs.sbatch"), "w", encoding="utf-8", newline="\n").write(sb)
        io.open(os.path.join(out, "run_all.sh"), "w", encoding="utf-8", newline="\n").write(
            '#!/usr/bin/env bash\n# submit the whole matrix as one array job. Login nodes have no GPU, so the pre-flight here skips the CUDA check;\n'
            '# every array task runs the full check_env.py on its compute node before training.\n'
            'cd "$(dirname "$0")"\n"${PYTHON:-python}" check_env.py --no-gpu || exit 1\n${SBATCH:-sbatch} jobs.sbatch\n')
        io.open(os.path.join(out, "sbatch_local.sh"), "w", encoding="utf-8", newline="\n").write("""#!/usr/bin/env bash
# Serial emulator of `sbatch` for an array job: runs every task of jobs.sbatch one after another in this shell, with the
# SLURM_* variables the script reads, and writes slurm_<job>_<task>.out like the real thing. For dry runs on a workstation
# and for the regression suite; it is NOT Slurm (no partition, no GPU allocation, no time limit).
#   SBATCH="bash sbatch_local.sh" bash run_all.sh
set -u
S="${1:?usage: sbatch_local.sh jobs.sbatch}"
RANGE=$(grep -m1 -oE '^#SBATCH --array=[0-9]+-[0-9]+' "$S" | grep -oE '[0-9]+-[0-9]+$')
A=${RANGE%-*}; B=${RANGE#*-}
export SLURM_SUBMIT_DIR="$(pwd)" SLURM_ARRAY_JOB_ID=$$
echo "Submitted batch job $$ (local emulation: tasks $A-$B run serially)"
for i in $(seq "$A" "$B"); do
  SLURM_ARRAY_TASK_ID=$i SLURM_JOB_ID="${SLURM_ARRAY_JOB_ID}_$i" bash "$S" > "slurm_${SLURM_ARRAY_JOB_ID}_${i}.out" 2>&1 || echo "task $i exited non-zero (slurm_${SLURM_ARRAY_JOB_ID}_${i}.out)"
done
echo "all $((B-A+1)) tasks finished"
""")
    else:
        lines = ["#!/usr/bin/env bash", "# full matrix, sequential. Already-finished runs (eval.json present) are skipped so this is restartable.", "set -uo pipefail", 'cd "$(dirname "$0")"', '"${PYTHON:-python}" check_env.py || exit 1']
        for r in rows:
            lines.append(f'[ -f {cdn}/runs/{r["run_id"]}/eval.json ] && echo "skip {r["run_id"]}" || bash run_one.sh {r["run_id"]} {r["args"]} || echo "FAILED {r["run_id"]}" >> failed.txt')
        lines.append('echo "ALL DONE — run collect.sh"')
        io.open(os.path.join(out, "run_all.sh"), "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    # collect.sh
    col = f"""#!/usr/bin/env bash
# pack everything the gates need, no checkpoints. Send results_<date>.tar.gz back; `bundle.py ingest <tar>` unpacks it into the project.
cd "$(dirname "$0")"
D=results_$(date +%Y%m%d_%H%M)
FILES=()
for f in manifest.json matrix.csv smoke_report.txt failed.txt slurm_*.out; do [ -e "$f" ] && FILES+=("$f"); done
while IFS= read -r f; do FILES+=("$f"); done < <(find {cdn}/runs -maxdepth 2 \\( -name args.json -o -name log.json -o -name eval.json -o -name hardware.json -o -name manifest.json -o -name stats.npz -o -name stats.json -o -name train.log -o -name eval.log -o -name 'split*' \\) 2>/dev/null)
while IFS= read -r f; do FILES+=("$f"); done < <(find {cdn}/runs -maxdepth 2 -type d -name preds 2>/dev/null)
tar czf "$D.tar.gz" "${{FILES[@]}}"
ls -la "$D.tar.gz"; echo "send $D.tar.gz back ($(find {cdn}/runs -maxdepth 2 -name eval.json 2>/dev/null | wc -l) runs with eval.json)"
"""
    io.open(os.path.join(out, "collect.sh"), "w", encoding="utf-8", newline="\n").write(col)
    # README
    env = b.get("env", "requirements.txt")
    rd = f'''# 实验包 — {st.get('project', {}).get('title', '')}  （生成 {man['created']}，prereg sha {man.get('prereg_sha256', '')[:12]}）

上传整个目录（含 `{cdn}/`）到服务器，数据放在：
{chr(10).join(f"- {d.get('name')}: `{d.get('remote')}`" for d in data) or '- （state.bundle.data 未填）'}

按顺序：
1. 建环境：`pip install -r {cdn}/{env}`（或 conda env create -f）；`python` 不是 3 的机器先 `export PYTHON=python3`
2. `python check_env.py{' --no-gpu' if sched == 'slurm' else ''}` —— 任何 MISS 都不要往下跑，把输出发回来{'（登录节点无 GPU，--no-gpu 跳过显卡项；作业内会再查）' if sched == 'slurm' else ''}
3. {'`srun -p ' + str((b.get('slurm') or {}).get('partition', 'gpu')) + ' --gres=' + str((b.get('slurm') or {}).get('gres', 'gpu:1')) + ' --pty bash smoke.sh`（要在计算节点上跑）' if sched == 'slurm' else '`bash smoke.sh`'} —— 几分钟；把 `smoke_report.txt` 发回来，我确认后再跑全量
4. `bash run_all.sh` —— {len(rows)} 个 run（{'sbatch 数组作业，一个 task 一个 run；`squeue -u $USER` 看进度，`slurm_*.out` 看日志；中途失败就再跑一次 run_all.sh，已完成的 run 自动跳过，失败的在 failed.txt' if sched == 'slurm' else '顺序跑，可中断重跑，已完成的 run 自动跳过，失败的在 failed.txt'}）
5. `bash collect.sh` —— 把生成的 `results_*.tar.gz` 发回来（不含 checkpoint）；回来后我跑 `bundle.py ingest` + `tables`

矩阵（matrix.csv）：ref {sum(1 for r in rows if r['role']=='ref')} / baselines {sum(1 for r in rows if r['role']=='baseline')} / ablations {sum(1 for r in rows if r['role']=='ablation')} / extra {sum(1 for r in rows if r['role']=='extra')}，seeds {(b.get('matrix') or {}).get('seeds')}
每个 run 产出 runs/<run_id>/{{args,log,eval,hardware,manifest}}.json；hardware.json 是主表"同一硬件"规则的证据。
不要改 `{cdn}/` 里的任何文件——manifest.json 记录了 sha256，回收时核对，不一致的结果不进表。
'''
    io.open(os.path.join(out, "README.md"), "w", encoding="utf-8").write(rd)
    # copy code (without runs/ and caches)
    import shutil
    dst = os.path.join(out, cdn)
    if os.path.abspath(dst) != os.path.abspath(code_dir):
        if os.path.exists(dst): shutil.rmtree(dst)
        shutil.copytree(code_dir, dst, ignore=shutil.ignore_patterns("runs", "__pycache__", "*.pt", "*.pth", "_*", "*.npz", "*.npy"))
    n_files = sum(len(fs) for _, _, fs in os.walk(out))
    print(f"bundle -> {out}: {len(rows)} runs in matrix.csv, {len(man['files'])} code files in manifest, {n_files} files total ({sched})")
    for r in rows[:6]: print(f"  {r['run_id']:24s} {r['role']:9s} {r['args']}")
    if len(rows) > 6: print(f"  … {len(rows)-6} more")

# ------------------------------------------------------------------ check
def check(a):
    st = load_state(a.state); b = st.get("bundle") or {}; root = os.path.dirname(os.path.abspath(a.state))
    if not b: say("FAIL", "bundle", "state 无 bundle: 段"); sys.exit(1)
    rows = build_matrix(b); names = [r["name"] for r in rows]
    aud = st.get("audits") or {}; res = st.get("results") or {}
    # entry/eval/post/env 都相对 code_dir（run_one.sh 先 cd 进去），写成 "code/train.py" 会变成 code/code/train.py
    cd = (b.get("code_dir") or "code").strip("/\\")
    bad_rel = [k for k in ("entry", "eval", "post", "env") if re.search(r"(?<![\w./])" + re.escape(cd) + r"/", str(b.get(k) or ""))]
    if bad_rel:
        say("FAIL", "paths", f"bundle 的 {bad_rel} 里带了 '{cd}/' 前缀：这几项相对 code_dir，run_one.sh 会先 cd 进 {cd}/，"
                             f"结果变成 {cd}/{cd}/…。去掉前缀（例如 entry: \"python train.py --exp {{run}} {{args}}\"）")
    for k in ("entry", "eval"):
        v = str(b.get(k) or "")
        if k == "entry" and "{run}" not in v: say("FAIL", "paths", "bundle.entry 里必须有 {run}")
        if k == "eval" and v and "{runs}" not in v and "{run}" not in v: say("FAIL", "paths", "bundle.eval 里必须有 {runs} 或 {run}")
    pr = os.path.join(root, "prereg.md"); md = io.open(pr, encoding="utf-8").read() if os.path.exists(pr) else ""
    if md:
        base = table_first_col(section(md, "baselines")); abl = table_first_col(section(md, "ablations"))
        ref = (b.get("matrix") or {}).get("ref", {}).get("name", "")
        aliases = res.get("aliases") or {}; waiver = res.get("coverage_waiver") or {}
        def covered(x, pool):   # prereg row x is covered by a matrix name directly, or through results.aliases {name: "<substring of the prereg row>"}
            return fuzzy_in(x, pool) or any(n in pool and norm(sub) and norm(sub) in norm(x) for n, sub in aliases.items())
        def waived(x): return next((f"{k}: {v}" for k, v in waiver.items() if norm(k) and norm(k) in norm(x)), "")
        mb = [x for x in base if not covered(x, names + [ref]) and not waived(x)]; ma = [x for x in abl if not covered(x, names) and not waived(x)]
        wv = [waived(x) for x in base + abl if waived(x) and not covered(x, names + [ref])]
        if wv: say("WARN", "coverage", f"{len(wv)} 项 prereg 基线/消融在本阶段不跑（results.coverage_waiver）: {wv[:3]} —— 主表前必须补上或在 convention_changes 写明")
        if mb: say("FAIL", "coverage", f"prereg §5 基线不在矩阵里: {mb}（matrix.baselines 加上；名字对不上用 results.aliases {{矩阵名: prereg 行子串}}；本阶段不跑的写 results.coverage_waiver）")
        else: say("PASS", "coverage", f"prereg §5 的 {len(base)} 个基线全部在矩阵或已豁免")
        if ma: say("FAIL", "coverage", f"prereg §6 消融不在矩阵里: {ma}")
        else: say("PASS", "coverage", f"prereg §6 的 {len(abl)} 项消融全部在矩阵或已豁免")
    else: say("WARN", "coverage", "无 prereg.md，跳过覆盖核对")
    seeds = (b.get("matrix") or {}).get("seeds") or [0]; ms = int(res.get("min_seeds", 3)); seeded = set((b.get("matrix") or {}).get("seeded") or [])
    refn = (b.get("matrix") or {}).get("ref", {}).get("name", "")
    if len(seeds) < ms and not res.get("seed_waiver"): say("FAIL", "seeds", f"matrix.seeds 只有 {len(seeds)} 个（results.min_seeds={ms}），无 seed_waiver")
    else: say("PASS", "seeds", f"seeds {seeds}；多 seed 的方法: {sorted(seeded) or [refn]}")
    if refn and refn not in seeded and len(seeds) > 1: say("FAIL", "seeds", f"参照方法 {refn} 不在 matrix.seeded 里 —— 消融分辨率 σ_ref 需要参照 ≥2 seeds")
    leaks = aud.get("leak_flags") or []
    hit = [(r["run_id"], f) for r in rows for f in leaks if re.search(r"--" + re.escape(f) + r"(\s+[1-9]|\s*=\s*[1-9]|\s+true)", r["args"], re.I)]
    if hit: say("FAIL", "leak", f"矩阵里有 run 打开了泄漏开关: {hit[:4]}")
    elif leaks: say("PASS", "leak", f"矩阵无 run 打开 {leaks}")
    crit = aud.get("critical_params") or {}
    for p in crit:
        # value may be a number (--beta 0.1) or a word (--cond srf); "off" = 0 / 0.0 / none / false / off / no  (RS_nowcast 2026-10-12: --cond is a string)
        nz = r"--" + re.escape(p) + r"(?:\s+|=)(?!(?:0(?:\.0+)?|none|null|false|off|no)(?![\w.]))[\w.\-]+"
        anyv = r"--" + re.escape(p) + r"(?:\s+|=)[\w.\-]+"
        off = [r["run_id"] for r in rows if r["role"] == "baseline" and re.search(nz, r["args"])]
        if off: say("WARN", "critical", f"基线 run 显式给了 {p}≠0: {off[:4]} —— 若基线代码里该项不生效，args 会撒谎（G3 有效配置关口会抓，但最好在矩阵里就写 0）")
        # 2026-10-11 全新项目端到端实测：ref 只写 "--model ours"，train.py 的 --beta 默认 0，于是"本文方法"按基线配置跑完了全部 seeds，
        # 而 G3 有效配置审计因 args=0、日志=0 自洽而放行。本文方法与消融行必须把每个关键超参写在 args 里，不许靠默认值。
        implicit = [r["run_id"] for r in rows if r["role"] in ("ref", "ablation") and not re.search(anyv, r["args"])]
        if implicit: say("FAIL", "critical", f"{p} 没有显式写进这些 run 的 args: {implicit[:5]} —— 本文方法与消融行必须写 `--{p} <值>`（去掉就写 0），不能靠 train.py 的默认值：默认值是 0 时本文方法会静默按基线跑")
        ref_rows = [r for r in rows if r["role"] == "ref"]
        if ref_rows and not any(re.search(nz, r["args"]) for r in ref_rows): say("FAIL", "critical", f"参照方法的 args 里 {p} 为 0 或缺失：{ref_rows[0]['args']!r} —— 本文方法的关键超参必须非零")
    if crit and not FAILS: say("PASS", "critical", f"ref 与消融行都显式给了 {list(crit)}")
    inputs = aud.get("inputs") or []; data = b.get("data") or []
    if not data: say("FAIL", "data", "bundle.data 为空：check_env 不知道去哪查输入")
    else:
        for d in data:
            if not d.get("remote"): say("FAIL", "data", f"data {d.get('name')} 无 remote 路径")
            cov = d.get("inputs") or inputs
            if not cov: say("WARN", "data", f"data {d.get('name')} 无 inputs 列表，check_env 只查目录存在")
            else: say("PASS", "data", f"{d.get('name')}: check_env 将核对 {cov}")
    if not b.get("eval"): say("WARN", "eval", "bundle.eval 未配置：run_one 不会产出 eval.json，G4 无法溯源")
    dup = [n for n in set(r["run_id"] for r in rows) if sum(1 for r in rows if r["run_id"] == n) > 1]
    if dup: say("FAIL", "matrix", f"run_id 重复: {dup}")
    say("INFO", "matrix", f"{len(rows)} runs: " + ", ".join(f"{k}={sum(1 for r in rows if r['role']==k)}" for k in ("ref", "baseline", "ablation", "extra")))
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL")); sys.exit(0 if FAILS == 0 else 1)

# ------------------------------------------------------------------ tables
def get_path(o, path):
    for part in path.split("."):
        o = o[int(part)] if isinstance(o, list) else o[part]
    return o

def tables(a):
    st = load_state(a.state); b = st.get("bundle") or {}; res = st.get("results") or {}; root = os.path.dirname(os.path.abspath(a.state))
    runs_dir = os.path.join(root, a.runs or res.get("runs_dir", "runs")); mm = res.get("metric_map") or {}
    if not mm: say("FAIL", "tables", "state.results.metric_map 为空：不知道 eval.json 的哪个字段进哪列"); sys.exit(1)
    mx = os.path.join(root, a.matrix) if a.matrix else os.path.join(root, "bundle", "matrix.csv")
    rows = list(csv.DictReader(open(mx, encoding="utf-8"))) if os.path.exists(mx) else [{"run_id": d, "role": "?", "name": d, "seed": ""} for d in sorted(os.listdir(runs_dir))]
    man_p = os.path.join(root, "bundle", "manifest.json"); man = json.load(open(man_p)) if os.path.exists(man_p) else None
    main, abl, skipped = [], [], []
    for r in rows:
        d = os.path.join(runs_dir, r["run_id"]); ev = os.path.join(d, "eval.json")
        if not os.path.exists(ev): skipped.append((r["run_id"], "no eval.json")); continue
        e = json.load(open(ev, encoding="utf-8"))
        if e.get("_tainted"): skipped.append((r["run_id"], "_tainted")); continue
        if man and os.path.exists(os.path.join(d, "manifest.json")):
            rm = json.load(open(os.path.join(d, "manifest.json")))
            if rm.get("files") != man.get("files"): skipped.append((r["run_id"], "manifest differs: code changed between bundle and run")); continue
        hw = ""
        hp = os.path.join(d, "hardware.json")
        if os.path.exists(hp): hw = json.load(open(hp)).get("hardware", "")
        if not hw:
            ap_ = os.path.join(d, "args.json"); hw = json.load(open(ap_)).get(res.get("hardware_key", "hardware"), "") if os.path.exists(ap_) else ""
        seed = r.get("seed", "")
        if seed == "" and os.path.exists(os.path.join(d, "args.json")): seed = json.load(open(os.path.join(d, "args.json"))).get("seed", "")
        row = {"run_id": r["run_id"], "seed": seed, "hardware": re.sub(r"^NVIDIA\s+|\s+\d+GB$", "", str(hw))}
        bad = []
        for col, path in mm.items():
            try: row[col] = round(float(get_path(e, path)), a.decimals)
            except Exception: bad.append(col)
        if bad: skipped.append((r["run_id"], f"missing {bad}")); continue
        if r.get("role") == "ablation": abl.append({"ablation": r["name"], **row})
        else: main.append({res.get("group_key", "method"): r["name"], **row, "table": "main"})
    os.makedirs(os.path.join(root, "results"), exist_ok=True)
    gk = res.get("group_key", "method")
    if main:
        p = os.path.join(root, res.get("main_table", "results/main.csv"))
        with open(p, "w", newline="", encoding="utf-8") as f:
            cols = ["run_id", gk, "seed", "table", "hardware"] + list(mm.keys()); w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(main)
        print(f"{p}: {len(main)} rows")
        # convention note next to the table: results_check reads <main>.md for the prereg §3/§4 markers (|F| ≥ 0.1 N, contact-window, …).
        # Written from prereg verbatim so the convention on the table is the locked one, not a re-typed paraphrase.
        pr = os.path.join(root, "prereg.md"); md = io.open(pr, encoding="utf-8").read() if os.path.exists(pr) else ""
        note_p = os.path.splitext(p)[0] + ".md"
        if md and not os.path.exists(note_p):
            den = section(md, "denominator").strip(); win = section(md, "inclusion_window").strip()
            io.open(note_p, "w", encoding="utf-8").write(
                f"# {os.path.relpath(p, root).replace(chr(92), '/')} — convention note (bundle.py tables, from prereg.md §3/§4)\n\n"
                f"## denominator\n{den or '(prereg §3 empty)'}\n\n## inclusion_window\n{win or '(prereg §4 empty)'}\n\n"
                f"metric columns {list(mm.keys())} are read from runs/<run_id>/{res.get('eval_file', 'eval.json')} via state.results.metric_map {mm}; hardware from hardware.json.\n")
            print(f"{note_p}: convention note written from prereg §3/§4")
    if abl:
        p = os.path.join(root, res.get("ablation_table", "results/ablation.csv"))
        with open(p, "w", newline="", encoding="utf-8") as f:
            cols = ["ablation", "run_id", "seed", "hardware"] + list(mm.keys()); w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(abl)
        print(f"{p}: {len(abl)} rows")
    hws = {r["hardware"] for r in main + abl}
    if len(hws) > 1: say("WARN", "tables", f"多种硬件混在一起 {hws} —— results_check 会 FAIL，另立 repro 表")
    for rid, why in skipped: print(f"  skipped {rid}: {why}")
    print(f"{len(main)+len(abl)} rows written, {len(skipped)} skipped; 下一步 results_check.py")
    if skipped and not (main or abl): sys.exit(1)

# ------------------------------------------------------------------ ingest
def ingest(a):
    """Unpack what collect.sh produced: <code>/runs/<run>/<file> -> <project>/runs/<run>/<file>; bundle-level files -> bundle/returned_<stamp>/.
    Refuses paths that would escape the project (tar from an untrusted machine is still a tar)."""
    st = load_state(a.state); root = os.path.dirname(os.path.abspath(a.state)); res = st.get("results") or {}
    runs_dir = os.path.join(root, a.runs or res.get("runs_dir", "runs")); os.makedirs(runs_dir, exist_ok=True)
    if not os.path.exists(a.tar): say("FAIL", "ingest", f"{a.tar} 不存在"); sys.exit(1)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); side = os.path.join(root, "bundle", f"returned_{stamp}"); os.makedirs(side, exist_ok=True)
    n_run, n_side, runs_seen, smoke_seen, refused = 0, 0, set(), set(), []
    with tarfile.open(a.tar, "r:*") as tf:
        for m in tf.getmembers():
            if not m.isfile(): continue
            parts = [x for x in m.name.replace("\\", "/").split("/") if x not in ("", ".")]
            if any(x == ".." for x in parts) or m.name.startswith("/"): refused.append(m.name); continue
            if "runs" in parts and parts.index("runs") + 2 < len(parts):          # <anything>/runs/<run_id>/<rest...>
                i = parts.index("runs"); rid = parts[i + 1]; rest = parts[i + 2:]
                if rid.startswith(("_", ".")):                                     # _smoke_* and the like: evidence, not a run
                    dst = os.path.join(side, "runs", rid, *rest); smoke_seen.add(rid); n_side += 1
                else:
                    dst = os.path.join(runs_dir, rid, *rest); runs_seen.add(rid); n_run += 1
            else:
                dst = os.path.join(side, *parts); n_side += 1
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with tf.extractfile(m) as src, open(dst, "wb") as out:
                out.write(src.read())
    if refused: say("FAIL", "ingest", f"tar 里有越界路径，已拒绝: {refused[:3]}")
    with_eval = sorted(r for r in runs_seen if os.path.exists(os.path.join(runs_dir, r, res.get("eval_file", "eval.json"))))
    without = sorted(runs_seen - set(with_eval))
    say("PASS" if with_eval else "FAIL", "ingest", f"{len(runs_seen)} 个 run 的 {n_run} 个文件 -> {os.path.relpath(runs_dir, root)}/；{len(with_eval)} 个有 eval.json" + (f"，无 eval.json: {without[:6]}" if without else ""))
    fp = os.path.join(side, "failed.txt")
    if os.path.exists(fp):
        lines = [l.strip() for l in io.open(fp, encoding="utf-8", errors="replace") if l.strip()]
        say("WARN", "ingest", f"failed.txt 有 {len(lines)} 条: {lines[:4]} —— 这些 run 不会进表；修了再补跑，补跑前先在 findings.md 记一条")
    print(f"{n_side} 个包级文件 -> {os.path.relpath(side, root)}/（smoke_report / failed.txt / slurm_*.out / matrix.csv" + (f"；烟测 run {sorted(smoke_seen)} 也放这里，不进 runs/" if smoke_seen else "") + "）")
    man_p = os.path.join(root, "bundle", "manifest.json"); got_p = os.path.join(side, "manifest.json")
    if os.path.exists(man_p) and os.path.exists(got_p):
        same = json.load(open(man_p)).get("files") == json.load(open(got_p)).get("files")
        say("PASS" if same else "FAIL", "ingest", "返回的 manifest.json 与本地实验包一致" if same else "返回的 manifest.json 与本地实验包不一致：服务器上改过代码，tables 会拒绝每个 run")
    print("\n" + ("ALL PASS" if FAILS == 0 else f"{FAILS} FAIL") + "；下一步 `bundle.py tables`"); sys.exit(0 if FAILS == 0 else 1)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("make", "check", "tables", "ingest"):
        p = sub.add_parser(n); p.add_argument("--state", default="research-state.yaml")
        if n == "make": p.add_argument("--out", default="bundle")
        if n == "tables": p.add_argument("--runs", default=""); p.add_argument("--matrix", default=""); p.add_argument("--decimals", type=int, default=3)
        if n == "ingest": p.add_argument("tar", help="results_*.tar.gz produced by collect.sh"); p.add_argument("--runs", default="")
    a = ap.parse_args(); {"make": make, "check": check, "tables": tables, "ingest": ingest}[a.cmd](a)

if __name__ == "__main__":
    main()
