# -*- coding: utf-8 -*-
"""P3 → P4 → P5 end to end on a FRESH project, through the scripts bundle.py generates — not on hand-written run files.

README's stated limit before this test: "P4 from the first run to the main table has been validated on a one-epoch smoke
run and on a finished 22-run project, not yet end-to-end on a fresh project; the Slurm branch of the bundle is untested."

What runs for real here (CPU, seconds): t2p.py init → prereg locked → bundle.py check (G3 before any run) → bundle.py make →
bash check_env.py / smoke.sh / run_all.sh / collect.sh (the generated scripts, under Git Bash or any bash) → bundle.py ingest
→ bundle.py tables → results_check.py + ablation_plan.py resolve (G4) → make_figure.py main|ablation (G5 input) → t2p.py check.
The Slurm branch runs the same matrix through jobs.sbatch with sbatch_local.sh standing in for sbatch (SLURM_ARRAY_TASK_ID
loop, slurm_*.out files, restart-skips-finished-runs), which is what a cluster does minus the scheduler.

Needs bash on PATH (Git Bash on Windows). The fixture code is tests/fixtures/e2e_code, data tests/fixtures/e2e_data."""
import json, os, re, shutil, subprocess, sys

import pytest
import yaml

from conftest import ENV, FIXTURES, PY, SCRIPTS, SKILL, edit, lock, read, run, write

BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(not BASH, reason="needs bash (Git Bash on Windows) to run the generated bundle scripts")


def sh(script, *args, cwd, env=None):
    """run a generated bash script inside the bundle dir; returns CompletedProcess with .out"""
    r = subprocess.run([BASH, str(script), *map(str, args)], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env or ENV)
    r.out = r.stdout + r.stderr
    return r


def fresh_project(tmp_path, scheduler="bash"):
    """t2p.py init + the fixture's prereg/state/gap_map/transfer_scan/problem_table, runnable code, local data. runs/ holds only the template."""
    proj = tmp_path / "proj"
    r = run("t2p.py", "init", "--project", str(proj), "--venue", "Engineering Applications of Artificial Intelligence", "--field", "cv", cwd=tmp_path)
    assert r.returncode == 0, r.out
    src = FIXTURES / "research_min"
    for rel in ("prereg.md", "research-state.yaml", "literature/gap_map.md", "literature/transfer_scan.md", "literature/problem_table.csv",
                "submission/guide.txt", "splits/train.txt", "splits/test.txt", "paper/refs.bib"):
        os.makedirs(os.path.dirname(proj / rel), exist_ok=True); shutil.copy(src / rel, proj / rel)
    shutil.copytree(FIXTURES / "e2e_code", proj / "code")
    shutil.copytree(FIXTURES / "e2e_data", proj / "data")
    # state: fresh project (phase P2, every gate pending), data path absolute for check_env, scheduler, no GPU required
    sp = proj / "research-state.yaml"; s = read(sp)
    s = re.sub(r"(?m)^  current: P8", "  current: P2", s)
    s = re.sub(r"(?m)^(  G[1-8]\w*: \{status: )pass", r"\1pending", s)              # every gate pending; G2 keeps its prereg_sha256 key
    data_remote = str(proj / "data" / "E1").replace("\\", "/")
    s = s.replace("    - {name: E1, remote: /data/E1, inputs: [frames], clip_glob: \"*\"}", f"    - {{name: E1, remote: {data_remote}, inputs: [frames], clip_glob: \"*\"}}")
    s = s.replace("  scheduler: bash", f"  scheduler: {scheduler}\n  require_gpu: false")
    s = s.replace("  import_check: [numpy]", "  import_check: [json]")
    s = s.replace("  min_vram_gb: 8", "  min_vram_gb: 0").replace("  min_disk_gb: 10", "  min_disk_gb: 1")
    s = s.replace("    seeded: [ours, baseA, baseB, no_dom, no_cons]", "    seeded: [ours, baseA, baseB]")   # ablations single-run, as prereg §6 / Table 2 say
    s = s.split("\ninstruments:")[0] + "\n"                             # the e2e code loads no pretrained component: G3b passes with "无预训练组件"
    write(sp, s)
    assert "prereg_sha256" in read(sp)
    lock(proj, "prereg.md", "prereg_sha256")
    return proj


def _board(proj, *extra):
    r = run("t2p.py", "check", "--project", ".", "--no-write", *extra, cwd=proj)
    return r, {m.group(2): m.group(1) for m in re.finditer(r"^\[(\w+(?:/\w+)?)\] (G[\w-]+):", r.out, re.M)}


def drive(proj, scheduler):
    """P3 + P4 through the generated scripts; returns the bundle dir"""
    # ---- P3: G3 before any run = bundle check; runs/ has only the template so the audit branch must not be taken
    r, g = _board(proj)
    assert g["G2"] == "PASS" and g["G3"] == "PASS", r.out
    assert "bundle check" in r.out and "runs/ 尚空" in r.out, r.out
    assert g["G4"] == "PENDING" and g["G5"] == "PENDING"
    r = run("bundle.py", "make", "--out", "bundle", cwd=proj); assert r.returncode == 0, r.out
    b = proj / "bundle"
    for f in ("README.md", "check_env.py", "run_one.sh", "smoke.sh", "run_all.sh", "collect.sh", "matrix.csv", "manifest.json", "code/train.py", "code/eval.py"):
        assert (b / f).exists(), f
    assert "\r" not in open(b / "matrix.csv", "rb").read().decode(), "matrix.csv must be LF-only: the Slurm job reads it on Linux"
    # ---- remote side: pre-flight, smoke, full matrix, collect — the user's four commands, in order
    env = {**ENV, "PYTHON": PY}
    r = subprocess.run([PY, "check_env.py"] + (["--no-gpu"] if scheduler == "slurm" else []), cwd=str(b), capture_output=True, text=True, encoding="utf-8", env=env); assert r.returncode == 0 and "ENV OK" in r.stdout, r.stdout + r.stderr
    r = sh(b / "smoke.sh", cwd=b, env=env); assert r.returncode == 0 and "SMOKE DONE" in r.out, r.out
    assert (b / "smoke_report.txt").exists() and (b / "code" / "runs" / "_smoke_ours" / "eval.json").exists(), r.out
    if scheduler == "slurm":
        assert (b / "jobs.sbatch").exists() and (b / "sbatch_local.sh").exists()
        r = sh(b / "run_all.sh", cwd=b, env={**env, "SBATCH": f"{BASH} sbatch_local.sh"}); assert r.returncode == 0 and "Submitted batch job" in r.out, r.out
        outs = sorted(b.glob("slurm_*_*.out")); assert len(outs) == 11, [o.name for o in outs]
        assert all("== done" in read(o) for o in outs), [(o.name, read(o)[-300:]) for o in outs if "== done" not in read(o)]
        assert not (b / "failed.txt").exists(), read(b / "failed.txt")
        # restart: every task must skip at once
        r = sh(b / "run_all.sh", cwd=b, env={**env, "SBATCH": f"{BASH} sbatch_local.sh"}); assert r.returncode == 0
        assert sum("skip " in read(o) for o in b.glob("slurm_*_*.out")) >= 11, "re-submission must skip finished runs"
    else:
        r = sh(b / "run_all.sh", cwd=b, env=env); assert r.returncode == 0 and "ALL DONE" in r.out, r.out
        assert not (b / "failed.txt").exists(), read(b / "failed.txt")
        r = sh(b / "run_all.sh", cwd=b, env=env); assert r.out.count("skip ") == 11, r.out      # restartable
    runs = sorted(d.name for d in (b / "code" / "runs").iterdir() if not d.name.startswith("_"))
    assert runs == sorted(["ours_s0", "ours_s1", "ours_s2", "baseA_s0", "baseA_s1", "baseA_s2", "baseB_s0", "baseB_s1", "baseB_s2", "no_dom", "no_cons"]), runs
    for rid in runs:
        for f in ("args.json", "log.json", "eval.json", "hardware.json", "manifest.json"):
            assert (b / "code" / "runs" / rid / f).exists(), f"{rid}/{f}"
    r = sh(b / "collect.sh", cwd=b, env=env); assert r.returncode == 0, r.out
    tars = list(b.glob("results_*.tar.gz")); assert len(tars) == 1, r.out
    # ---- back home: ingest + tables
    r = run("bundle.py", "ingest", str(tars[0]), cwd=proj); assert r.returncode == 0 and "11 个 run" in r.out, r.out
    assert (proj / "runs" / "ours_s1" / "eval.json").exists() and (proj / "runs" / "no_dom" / "hardware.json").exists()
    assert list((proj / "bundle").glob("returned_*/smoke_report.txt")), "bundle-level files go to bundle/returned_<stamp>/"
    r = run("bundle.py", "tables", cwd=proj); assert r.returncode == 0 and "11 rows written, 0 skipped" in r.out, r.out
    assert (proj / "results" / "main.md").exists(), "convention note must be written from prereg §3/§4"
    main = read(proj / "results" / "main.csv"); abl = read(proj / "results" / "ablation.csv")
    assert main.count("\n") == 10 and abl.count("\n") == 3, (main, abl)
    assert "ours,0,A2000" not in main                    # hardware comes from hardware.json (cpu here), never hand-typed
    return b


@pytest.mark.parametrize("scheduler", ["bash", "slurm"])
def test_fresh_project_p3_to_p5_through_the_bundle(tmp_path, scheduler):
    proj = fresh_project(tmp_path, scheduler)
    drive(proj, scheduler)
    # ---- G3 now takes the audit branch on the real runs, and G4 is green on the generated tables
    r, g = _board(proj)
    assert "audit_check" in r.out and "bundle check" not in r.out, r.out
    assert g["G3"] == "PASS" and g["G4"] == "PASS", r.out
    a = run("ablation_plan.py", "resolve", cwd=proj)
    assert a.fails == 0 and "可解读格 2/4" in a.out, a.out            # no_dom resolvable on both metrics, no_cons inside seed noise
    rc = run("results_check.py", cwd=proj)
    assert "与预测 + 一致" in rc.out and "口径标记" in rc.out and rc.fails == 0, rc.out
    # ---- P5: figures from the generated tables; G5 = dpi gate
    for kind, out in (("main", "figures/fig_main.png"), ("ablation", "figures/fig_abl.png")):
        r = run("make_figure.py", kind, "--project", ".", "--out", out, cwd=proj); assert r.returncode == 0, r.out
    edit(proj / "figures.csv", ",no,", ",yes,")
    r, g = _board(proj)
    assert g["G5"] == "PASS", r.out
    assert g["G6"] == "PENDING"                                         # next station is writing
    assert "下一步：修 G6" in r.out, r.out


def test_unfinished_run_is_refused_by_the_tables(tmp_path):
    """A run whose log is shorter than epochs gets eval.json with _tainted: tables must skip it and results_check must FAIL on it."""
    proj = fresh_project(tmp_path, "bash")
    drive(proj, "bash")
    rd = proj / "runs" / "baseA_s2"
    log = json.loads(read(rd / "log.json")); write(rd / "log.json", json.dumps(log[:1]))
    ev = json.loads(read(rd / "eval.json")); ev["_tainted"] = "evaluated before training finished"; write(rd / "eval.json", json.dumps(ev))
    r = run("bundle.py", "tables", cwd=proj); assert "skipped baseA_s2: _tainted" in r.out and "10 rows written" in r.out, r.out
    r = run("results_check.py", cwd=proj); assert r.fails >= 1 and "baseA" in r.out and "seed" in r.out, r.out     # baseA now has 2 seeds


def test_code_changed_on_the_server_is_refused(tmp_path):
    proj = fresh_project(tmp_path, "bash")
    b = drive(proj, "bash")
    man = json.loads(read(proj / "runs" / "ours_s0" / "manifest.json")); man["files"]["train.py"] = "0" * 64
    write(proj / "runs" / "ours_s0" / "manifest.json", json.dumps(man))
    r = run("bundle.py", "tables", cwd=proj)
    assert "skipped ours_s0: manifest differs" in r.out and "10 rows written" in r.out, r.out


def test_missing_input_is_caught_by_check_env_not_by_the_trainer(tmp_path):
    proj = fresh_project(tmp_path, "bash")
    shutil.rmtree(proj / "data" / "E1" / "clip02" / "frames")
    assert run("bundle.py", "make", "--out", "bundle", cwd=proj).returncode == 0
    r = subprocess.run([PY, "check_env.py"], cwd=str(proj / "bundle"), capture_output=True, text=True, encoding="utf-8", env={**ENV, "PYTHON": PY})
    assert r.returncode != 0 and "MISSING" in r.stdout and "clip02" in r.stdout, r.stdout


def test_ingest_refuses_paths_that_escape_the_project(tmp_path):
    import tarfile
    proj = fresh_project(tmp_path, "bash")
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tf:
        p = tmp_path / "x.json"; write(p, "{}")
        tf.add(p, arcname="../../outside.json"); tf.add(p, arcname="code/runs/ok_run/eval.json")
    r = run("bundle.py", "ingest", str(evil), cwd=proj)
    assert r.fails >= 1 and "越界" in r.out and not (tmp_path / "outside.json").exists(), r.out
    assert (proj / "runs" / "ok_run" / "eval.json").exists()
