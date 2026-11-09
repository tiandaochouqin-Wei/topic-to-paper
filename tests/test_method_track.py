# -*- coding: utf-8 -*-
"""Method track (scripts/method_track.py): G1c headroom, G2m dev log + freeze, G4m confirmation.

The project under test is generated here (no fixture directory): a toy benchmark with a baseline x3, an oracle x3, two cheap fixes x3,
four logged iterations (I01-I04), two ablations of I04 and, after the freeze, confirm runs. Metric `ap` (higher is better), read from
runs/<id>/eval.json at metrics.ap. The base project is built once per module through the real CLI (`init`, `log add`, `freeze`) and
copied per test; every test then makes ONE change and asserts the gate that owns it. research-state.yaml is written here with its own
`method:` block (flow style, as in the template), so these tests do not depend on templates/research-state.yaml."""
import hashlib
import json
import os
import shutil
import sys

import pytest
import yaml

from conftest import SCRIPTS, edit, read, run, touch, write

sys.path.insert(0, str(SCRIPTS))
import method_track as mt  # noqa: E402

STATE = """\
branch: research
project: {paper_type: method}
audits: {code_dirs: [code]}
results:
  runs_dir: runs
  eval_file: eval.json
  metric_map: {ap: metrics.ap}
  primary_metric: ap
  primary_direction: higher
  min_seeds: 3
gates:
  G2: {status: pending, evidence: "", prereg_sha256: ""}

method:                                   # 方法轨道
  primary_metric: ""                      # 默认 results.primary_metric
  min_effect: 1.0                         # 最小提升
  min_effect_basis: "近两年同基准上 SOTA 逐篇提升的中位数 1.2 AP"
  benchmark: {name: ToyBench, split_source: "official split v2", metric_source: "toybench/eval.py"}
  baseline: {name: BaseNet, code: "github.com/x/basenet", published: {value: 50.2, source: "BaseNet Table 2"}, tol: null}
  splits:
    dev:     {tag: dev,     files: [data/dev/a.txt, data/dev/b.txt]}
    confirm: {tag: confirm, files: [data/confirm/c.txt], sha256: ""}   # sha256 由 init 写
  headroom:
    k_sd: 3
    oracle: {desc: "GT routing", run_glob: "runs/oracle_dev_s*", key: ""}
    cheap_fixes:
      - {name: augmentation, run_glob: "runs/aug_dev_s*", key: ""}
      - {name: longer_training, run_glob: "runs/long_dev_s*", key: ""}
  budget: {max_iters: 30, stall: 5, iter_hours: 2}
  files: {bottleneck: method/bottleneck.md, ideas: method/ideas.csv, iterations: method/iterations.csv, tuning: method/baseline_tuning.csv}
  components:
    - {name: module_A, ablation_glob: "runs/i04_noA_s*"}
    - {name: module_B, ablation_glob: "runs/i04_noB_s*"}
  mechanism: {desc: "gate fires on the degraded slice", file: results/mech.json, key: corr, expect: ">=0.3"}
  freeze: {}
  confirm: {registered_looks: 1, looks: []}
  outcome: ""
"""

BOTTLENECK = """\
# 方法轨道：瓶颈说明

## 瞄准的瓶颈
小目标在夜间场景漏检。

## 证据文件
results/failure_slices.md

## 占基线误差的比例
41%（failure_slices.md 第 3 节）
"""


# ------------------------------------------------------------------ builders
def mkrun(p, name, split, role, method, seed, value, iteration=None, extra=None, code=None, delta=0.0):
    d = p / "runs" / name
    d.mkdir(parents=True, exist_ok=True)
    a = {"eval_split": split, "role": role, "method": method, "seed": seed}
    if iteration:
        a["iteration"] = iteration
    if code:
        a["code_sha256"] = code
    a.update(extra or {})
    write(d / "args.json", json.dumps(a))
    write(d / "eval.json", json.dumps({"metrics": {"ap": value}}))
    touch(d / "eval.json", delta)


def mkgroup(p, prefix, mean, split="dev", role="ours", method="ours", iteration=None, n=3, d=0.5, extra=None, code=None, delta=0.0):
    """n runs `<prefix>0..n-1`, values symmetric around `mean` with s.d. d for n = 3"""
    for i in range(n):
        off = (i - (n - 1) / 2) * 2 * d / max(n - 1, 1)
        mkrun(p, f"{prefix}{i}", split, role, method, i, mean + off, iteration, extra, code, delta)


def state(p):
    return yaml.safe_load(read(p / "research-state.yaml"))


def mut(p, fn):
    st = state(p)
    fn(st)
    write(p / "research-state.yaml", yaml.safe_dump(st, allow_unicode=True, sort_keys=False, width=10**6))


def M(p, *args):
    return run("method_track.py", *args, cwd=p)


def log_add(p, i, runs, decision=None, hyp="假设", change="改动"):
    a = ["log", "add", "--id", i, "--hypothesis", hyp, "--change", change, "--runs", runs]
    if decision:
        a += ["--decision", decision]
    r = M(p, *a)
    assert r.fails == 0 and not r.crashed, r.out
    return r


def code_sha(p):
    return mt.code_sha(str(p), state(p))


def lock_prereg(p, text=None):
    fz = state(p)["method"]["freeze"]
    text = text if text is not None else f"# prereg\n§1 冻结的方法 freeze: {fz['code_sha256'][:8]}\n§7 验证集上评测一次\n"
    write(p / "prereg.md", text)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    mut(p, lambda st: st["gates"]["G2"].__setitem__("prereg_sha256", sha))


def add_confirm(p, ours=52.5, base=50.0, code=None, n=3, ours_extra=None, base_extra=None, delta=5.0):
    code = code or state(p)["method"]["freeze"]["code_sha256"]
    mkgroup(p, "cf_ours_s", ours, split="confirm", role="ours", method="ours", n=n, code=code, extra={"lr": 1e-4, **(ours_extra or {})}, delta=delta)
    mkgroup(p, "cf_base_s", base, split="confirm", role="baseline", method="BaseNet", n=n, code=code, extra={"lr": 1e-3, **(base_extra or {})}, delta=delta)


@pytest.fixture(scope="module")
def base_dir(tmp_path_factory):
    p = tmp_path_factory.mktemp("method") / "proj"
    p.mkdir()
    write(p / "research-state.yaml", STATE)
    write(p / "code" / "model.py", "def forward(x):\n    return x\n")
    write(p / "data" / "dev" / "a.txt", "dev a\n")
    write(p / "data" / "dev" / "b.txt", "dev b\n")
    write(p / "data" / "confirm" / "c.txt", "confirm c\n")
    write(p / "results" / "failure_slices.md", "# failure slices\n")
    write(p / "results" / "mech.json", json.dumps({"corr": 0.6}))
    mkgroup(p, "base_dev_s", 50.0, role="baseline", method="BaseNet")
    mkgroup(p, "oracle_dev_s", 58.0, role="oracle", method="oracle")
    mkgroup(p, "aug_dev_s", 51.5, role="cheap_fix", method="aug")
    mkgroup(p, "long_dev_s", 53.0, role="cheap_fix", method="long")
    for i, (m_, dec) in enumerate([(50.5, "drop"), (52.0, "revise"), (51.5, "drop"), (54.0, "keep")], 1):
        mkgroup(p, f"i0{i}_s", m_, iteration=f"I0{i}")
    mkgroup(p, "i04_noA_s", 52.0, role="ablation", method="ours-noA", iteration="I04")
    mkgroup(p, "i04_noB_s", 52.0, role="ablation", method="ours-noB", iteration="I04")
    r = M(p, "init")
    assert r.fails == 0 and not r.crashed, r.out
    write(p / "method" / "bottleneck.md", BOTTLENECK)
    write(p / "method" / "baseline_tuning.csv",
          "method,trial,config,dev_metric\nBaseNet,published_config,default,49.8\n" + "".join(f"BaseNet,{k},cfg{k},{49.5 + k * 0.1:.1f}\n" for k in range(1, 7)))
    write(p / "method" / "ideas.csv",
          "id,type,mechanism,predicted_effect,cheapest_test,kill_result,status\n" + "".join(
              f"N{k},{t},m,+1,1 seed,<0.2,open\n" for k, t in enumerate(["data", "objective", "architecture", "inference", "training"], 1)))
    for i, dec in enumerate(["drop", "revise", "drop", "keep"], 1):
        log_add(p, f"I0{i}", f"runs/i0{i}_s*", dec)
    return p


@pytest.fixture(scope="module")
def frozen_dir(tmp_path_factory, base_dir):
    p = tmp_path_factory.mktemp("method_frozen") / "proj"
    shutil.copytree(base_dir, p)
    r = M(p, "freeze", "--iteration", "I04")
    assert r.fails == 0 and not r.crashed, r.out
    lock_prereg(p)
    return p


@pytest.fixture
def proj(tmp_path, base_dir):
    p = tmp_path / "proj"
    shutil.copytree(base_dir, p)
    return p


@pytest.fixture
def fro(tmp_path, frozen_dir):
    p = tmp_path / "proj"
    shutil.copytree(frozen_dir, p)
    return p


def ok(r, needle=None):
    assert r.fails == 0 and not r.crashed, r.out
    if needle:
        assert needle in r.out, r.out


def bad(r, needle):
    assert r.fails >= 1 and not r.crashed and needle in r.out, r.out


def rm(p, pat):
    for d in (p / "runs").glob(pat):
        shutil.rmtree(d)


# ------------------------------------------------------------------ G1c
def test_g1c_go(proj):
    r = M(proj, "headroom")
    ok(r, "[PASS] G1c: GO (headroom H = 8.0000")
    assert "residual after cheap fixes R = 5.0000" in r.out and "noise sd_b = 0.5000" in r.out and "min_effect = 1" in r.out
    assert "基线复现 50.0000 vs 论文 50.2000" in r.out
    assert "占提升空间 38%" in r.out and "占提升空间 19%" in r.out


@pytest.mark.parametrize("field,mutation", [
    ("benchmark.name", lambda m: m["benchmark"].__setitem__("name", "")),
    ("benchmark.split_source", lambda m: m["benchmark"].__setitem__("split_source", "")),
    ("benchmark.metric_source", lambda m: m["benchmark"].__setitem__("metric_source", "")),
    ("baseline.name", lambda m: m["baseline"].__setitem__("name", "")),
    ("baseline.code", lambda m: m["baseline"].__setitem__("code", "")),
    ("min_effect_basis", lambda m: m.__setitem__("min_effect_basis", "")),
])
def test_g1c_required_fields(proj, field, mutation):
    mut(proj, lambda st: mutation(st["method"]))
    r = M(proj, "headroom")
    bad(r, f"method.{field} 为空")
    assert "NO-GO" in r.out


def test_g1c_baseline_needs_three_runs(proj):
    rm(proj, "base_dev_s2")
    bad(M(proj, "headroom"), "基线在 dev 上只有 2 个 run")


def test_g1c_baseline_seed_waiver_is_a_warning(proj):
    rm(proj, "base_dev_s2")
    mut(proj, lambda st: st["results"].__setitem__("seed_waiver", "single GPU week"))
    r = M(proj, "headroom")
    assert "[WARN] G1c: 基线 dev 只有 2 个 run" in r.out and "seed_waiver" in r.out, r.out


def test_g1c_baseline_not_reproduced(proj):
    mut(proj, lambda st: st["method"]["baseline"]["published"].__setitem__("value", 53.0))
    r = M(proj, "headroom")
    bad(r, "基线没复现到论文数字，先查实现（G3b）")
    assert "复现 50.0000 vs 论文 53.0000" in r.out


def test_g1c_no_published_number_is_a_warning(proj):
    mut(proj, lambda st: st["method"]["baseline"]["published"].__setitem__("value", None))
    r = M(proj, "headroom")
    assert r.fails == 0 and "[WARN] G1c: 没有可对账的已发表数字" in r.out, r.out


def test_g1c_baseline_explicit_tol(proj):
    mut(proj, lambda st: (st["method"]["baseline"]["published"].__setitem__("value", 50.6), st["method"]["baseline"].__setitem__("tol", 0.3)))
    bad(M(proj, "headroom"), "|Δ| = 0.6000 > tol 0.3000")


def test_g1c_no_oracle_runs(proj):
    rm(proj, "oracle_dev_s*")
    bad(M(proj, "headroom"), "没有 oracle dev run")


def test_g1c_oracle_with_wrong_role_does_not_count(proj):
    for d in (proj / "runs").glob("oracle_dev_s*"):
        a = json.loads(read(d / "args.json")); a["role"] = "ours"; write(d / "args.json", json.dumps(a))
    bad(M(proj, "headroom"), "没有 oracle dev run")


def test_g1c_no_headroom(proj):
    rm(proj, "oracle_dev_s*")
    mkgroup(proj, "oracle_dev_s", 50.8, role="oracle", method="oracle")
    r = M(proj, "headroom")
    bad(r, "瞄准的瓶颈没有提升空间（oracle 只比基线好 H = 0.8000")
    assert "这个方向做不出方法论文，改瓶颈或转分析" in r.out and "NO-GO" in r.out


def test_g1c_oracle_worse_than_baseline(proj):
    rm(proj, "oracle_dev_s*")
    mkgroup(proj, "oracle_dev_s", 48.0, role="oracle", method="oracle")
    r = M(proj, "headroom")
    bad(r, "理想地解决它反而更差")
    assert "瞄准的瓶颈判断错了" in r.out and "H = -2.0000" in r.out


def test_g1c_two_seed_oracle_and_cheap_fix_warn(proj):
    # cvpr2027_fusion replay: the oracle-gate variant had only 2 seeds while the headroom is judged against seed noise
    rm(proj, "oracle_dev_s*")
    mkgroup(proj, "oracle_dev_s", 56.0, role="oracle", method="oracle", n=2)
    r = M(proj, "headroom")
    assert "[WARN] G1c: oracle 只有 2 个 seed" in r.out and "便宜做法" in r.out, r.out
    assert "只有 2 个 seed，补到" not in r.out          # the fixture's cheap fixes have 3 seeds: no cheap-fix warning


def test_g1c_noise_scaled_threshold(proj):
    # H = 2 clears min_effect = 1, but not k_sd x sd_b = 3 x 0.5 = 1.5? it does; widen the baseline noise so that it does not
    rm(proj, "base_dev_s*")
    mkgroup(proj, "base_dev_s", 50.0, role="baseline", method="BaseNet", d=1.5)
    rm(proj, "oracle_dev_s*")
    mkgroup(proj, "oracle_dev_s", 53.0, role="oracle", method="oracle")
    bad(M(proj, "headroom"), "H = 3.0000 < max(min_effect 1, 3×sd_b 1.5000) = 4.5000")


def test_g1c_cheap_fix_takes_the_headroom(proj):
    rm(proj, "aug_dev_s*")
    mkgroup(proj, "aug_dev_s", 57.0, role="cheap_fix", method="aug")
    r = M(proj, "headroom")
    bad(r, "便宜做法 augmentation 已经拿走 88% 的提升空间，剩 R = 1.0000")
    assert "方法没有立足点" in r.out


def test_g1c_needs_two_cheap_fixes(proj):
    mut(proj, lambda st: st["method"]["headroom"].__setitem__("cheap_fixes", st["method"]["headroom"]["cheap_fixes"][:1]))
    bad(M(proj, "headroom"), "便宜做法只登记了 1 个")


def test_g1c_cheap_fix_without_runs(proj):
    rm(proj, "long_dev_s*")
    bad(M(proj, "headroom"), "便宜做法 longer_training: 没有 dev run")


def test_g1c_lower_is_better_metric(proj):
    # same project with an error metric: oracle LOWER than the baseline is the headroom
    mut(proj, lambda st: st["results"].__setitem__("primary_direction", "lower"))
    r = M(proj, "headroom")
    bad(r, "理想地解决它反而更差")   # higher numbers are now worse


def test_g1c_unknown_direction(proj):
    def f(st):
        st["results"]["primary_metric"] = "score"; st["results"]["primary_direction"] = ""; st["results"]["metric_map"] = {"score": "metrics.ap"}
    mut(proj, f)
    bad(M(proj, "headroom"), "方向猜不出")


def test_g1c_split_overlap(proj):
    mut(proj, lambda st: st["method"]["splits"]["dev"]["files"].append("data/confirm/c.txt"))
    bad(M(proj, "headroom"), "dev 与 confirm 有重叠文件")


def test_g1c_confirm_files_changed_after_init(proj):
    write(proj / "data" / "confirm" / "c.txt", "tampered\n")
    bad(M(proj, "headroom"), "验证集文件和登记的 sha256 不一致")


def test_g1c_confirm_sha_not_registered(proj):
    mut(proj, lambda st: st["method"]["splits"]["confirm"].__setitem__("sha256", ""))
    bad(M(proj, "headroom"), "splits.confirm.sha256 为空")


def test_g1c_empty_split_lists(proj):
    mut(proj, lambda st: st["method"]["splits"]["dev"].__setitem__("files", []))
    bad(M(proj, "headroom"), "files 不能为空")


def test_g1c_confirm_evaluated_before_freeze(proj):
    mkrun(proj, "peek", "confirm", "ours", "ours", 0, 60.0)
    bad(M(proj, "headroom"), "冻结前评测了验证集（run runs/peek）")


def test_g1c_iter_hours_missing_is_a_warning(proj):
    mut(proj, lambda st: st["method"]["budget"].__setitem__("iter_hours", None))
    r = M(proj, "headroom")
    assert r.fails == 0 and "[WARN] G1c: budget.iter_hours 未填" in r.out, r.out


def test_g1c_budget_in_gpu_hours(proj):
    assert "dev 预算 = 2 h/轮 × 30 轮 = 60 GPU-小时" in M(proj, "headroom").out


def test_g1c_bottleneck_template(proj):
    shutil.copy(os.path.join(mt.SKILL, "templates", "method", "bottleneck.md"), proj / "method" / "bottleneck.md")
    bad(M(proj, "headroom"), "没有写出瞄准的瓶颈")


def test_g1c_bottleneck_missing(proj):
    (proj / "method" / "bottleneck.md").unlink()
    bad(M(proj, "headroom"), "method/bottleneck.md 不存在")


def test_g1c_bottleneck_evidence_file_must_exist(proj):
    edit(proj / "method" / "bottleneck.md", "results/failure_slices.md", "results/nowhere.md")
    bad(M(proj, "headroom"), "证据文件（failure_slice / 误差分解的输出）不存在")


def test_g1c_bottleneck_share_must_be_a_number(proj):
    edit(proj / "method" / "bottleneck.md", "41%（failure_slices.md 第 3 节）", "很大一部分")
    bad(M(proj, "headroom"), "没有占基线误差的比例（数）")


def test_g1c_without_method_block(proj):
    mut(proj, lambda st: st.pop("method"))
    bad(M(proj, "headroom"), "state 无 method: 段")


# ------------------------------------------------------------------ init / state writing
def test_init_creates_templates_and_registers_the_hash(tmp_path, base_dir):
    p = tmp_path / "p"
    p.mkdir()
    write(p / "research-state.yaml", STATE)
    write(p / "data" / "confirm" / "c.txt", "confirm c\n")
    write(p / "data" / "confirm" / "d.txt", "x")
    mut(p, lambda st: st["method"]["splits"]["confirm"].__setitem__("files", ["data/confirm"]))   # a directory expands to its files
    r = M(p, "init")
    ok(r, "splits.confirm.sha256 =")
    for fn in ("bottleneck.md", "ideas.csv", "iterations.csv", "baseline_tuning.csv"):
        assert (p / "method" / fn).exists()
    exp = hashlib.sha256(b"confirm c\n" + b"x").hexdigest()
    assert state(p)["method"]["splits"]["confirm"]["sha256"] == exp


def test_init_refuses_to_overwrite_a_changed_confirm_set(proj):
    write(proj / "data" / "confirm" / "c.txt", "tampered\n")
    bad(M(proj, "init"), "验证集被改过")
    ok(M(proj, "init", "--force"))


def test_init_needs_confirm_files(proj):
    mut(proj, lambda st: st["method"]["splits"]["confirm"].__setitem__("files", []))
    bad(M(proj, "init"), "splits.confirm.files 为空")


def test_state_set_inline_keeps_comments_and_other_blocks(tmp_path):
    p = tmp_path / "s.yaml"
    write(p, STATE)
    assert mt.state_set(str(p), ["freeze"], {"date": "2026-11-10T10:00:00", "iteration": "I04", "code_sha256": "ab" * 32}) == "inline"
    assert mt.state_set(str(p), ["splits", "confirm", "sha256"], "ff" * 32) == "inline"
    assert mt.state_set(str(p), ["confirm", "looks"], [{"id": "ours:abcd1234"}]) == "inline"
    assert mt.state_set(str(p), ["outcome"], "confirmed") == "inline"
    s = read(p)
    assert "# 方法轨道" in s and "# sha256 由 init 写" in s and "# 最小提升" in s     # comments survive
    d = yaml.safe_load(s)["method"]
    assert d["freeze"]["iteration"] == "I04" and d["splits"]["confirm"]["sha256"] == "ff" * 32
    assert d["confirm"]["looks"] == [{"id": "ours:abcd1234"}] and d["confirm"]["registered_looks"] == 1 and d["outcome"] == "confirmed"
    assert yaml.safe_load(s)["results"]["min_seeds"] == 3 and d["splits"]["dev"]["files"] == ["data/dev/a.txt", "data/dev/b.txt"]


def test_state_set_block_style_falls_back_to_a_full_dump(tmp_path):
    p = tmp_path / "s.yaml"
    write(p, yaml.safe_dump(yaml.safe_load(STATE), allow_unicode=True, sort_keys=False))
    mt.state_set(str(p), ["freeze"], {"iteration": "I04"})
    mt.state_set(str(p), ["splits", "confirm", "sha256"], "ee" * 32)
    mt.state_set(str(p), ["confirm", "looks"], [{"id": "x"}])
    d = yaml.safe_load(read(p))["method"]
    assert d["freeze"] == {"iteration": "I04"} and d["splits"]["confirm"]["sha256"] == "ee" * 32 and d["confirm"]["looks"] == [{"id": "x"}]


def test_code_sha_ignores_line_endings_and_pycache(proj):
    a = code_sha(proj)
    write(proj / "code" / "model.py", "def forward(x):\r\n    return x\r\n")
    (proj / "code" / "__pycache__").mkdir()
    write(proj / "code" / "__pycache__" / "x.py", "junk")
    assert code_sha(proj) == a
    write(proj / "code" / "model.py", "def forward(x):\n    return x + 1\n")
    assert code_sha(proj) != a
    r = M(proj, "code-sha")
    assert r.out.strip() == code_sha(proj)


# ------------------------------------------------------------------ ideas
def test_ideas_pass(proj):
    r = M(proj, "ideas-check")
    ok(r, "[PASS] G2m: ideas.csv：5 个想法、5 类")


def test_ideas_warn_few_and_one_type(proj):
    write(proj / "method" / "ideas.csv", "id,type,mechanism,predicted_effect,cheapest_test,kill_result,status\nN1,data,m,+1,t,k,open\n")
    r = M(proj, "ideas-check")
    assert r.returncode == 0 and "[WARN] G2m: ideas.csv 只有 1 个想法" in r.out and "只覆盖 1 类" in r.out and r.fails == 0, r.out


def test_ideas_warn_missing_kill_result(proj):
    edit(proj / "method" / "ideas.csv", "N1,data,m,+1,1 seed,<0.2,open", "N1,data,m,+1,1 seed,,open")
    r = M(proj, "ideas-check")
    assert r.returncode == 0 and "想法 N1: 缺 kill_result" in r.out, r.out


def test_ideas_missing_file_is_a_warning(proj):
    (proj / "method" / "ideas.csv").unlink()
    r = M(proj, "ideas-check")
    assert r.returncode == 0 and "[WARN] G2m: method/ideas.csv 不存在" in r.out


# ------------------------------------------------------------------ log add
def test_log_add_computes_the_numbers_from_the_runs(proj):
    rows = list(__import__("csv").DictReader(open(proj / "method" / "iterations.csv", encoding="utf-8")))
    assert [r["id"] for r in rows] == ["I01", "I02", "I03", "I04"]
    r4 = rows[3]
    assert r4["n_seeds"] == "3" and float(r4["dev_mean"]) == pytest.approx(54.0) and float(r4["dev_sd"]) == pytest.approx(0.5)
    assert float(r4["baseline_mean"]) == pytest.approx(50.0) and float(r4["gain"]) == pytest.approx(4.0)
    assert float(r4["se_gain"]) == pytest.approx((0.25 / 3 + 0.25 / 3) ** 0.5)
    assert [float(r["best_so_far"]) for r in rows] == pytest.approx([0.5, 2.0, 2.0, 4.0])
    assert r4["code_sha256"] == code_sha(proj) and r4["decision"] == "keep"


def test_log_add_updates_an_existing_row_and_recomputes(proj):
    mkgroup(proj, "i03_s", 56.0, iteration="I03")      # I03 gets better than I04
    r = log_add(proj, "I03", "runs/i03_s*")
    assert "更新了已有行" in r.out
    rows = list(__import__("csv").DictReader(open(proj / "method" / "iterations.csv", encoding="utf-8")))
    assert len(rows) == 4 and rows[2]["decision"] == "drop"               # decision kept when not passed
    assert [float(r["best_so_far"]) for r in rows] == pytest.approx([0.5, 2.0, 6.0, 6.0])


def test_log_add_refuses_a_glob_without_runs(proj):
    r = M(proj, "log", "add", "--id", "I09", "--hypothesis", "h", "--change", "c", "--runs", "runs/nothing_*")
    bad(r, "匹配不到 role=ours, eval_split=dev 的 run")
    assert len(list(__import__("csv").DictReader(open(proj / "method" / "iterations.csv", encoding="utf-8")))) == 4


def test_log_add_ignores_confirm_runs(proj):
    mkgroup(proj, "i09_s", 99.0, split="confirm")
    bad(M(proj, "log", "add", "--id", "I09", "--hypothesis", "h", "--change", "c", "--runs", "runs/i09_s*"), "匹配不到")


def test_log_add_records_the_code_hash(proj):
    write(proj / "code" / "model.py", "def forward(x):\n    return 2 * x\n")
    mkgroup(proj, "i05_s", 53.0, iteration="I05")
    log_add(proj, "I05", "runs/i05_s*", "drop")
    rows = list(__import__("csv").DictReader(open(proj / "method" / "iterations.csv", encoding="utf-8")))
    assert rows[-1]["code_sha256"] == code_sha(proj) != rows[0]["code_sha256"]


# ------------------------------------------------------------------ G2m before the freeze
def test_g2m_pass_before_freeze(proj):
    r = M(proj, "dev-check")
    ok(r, "尚未 freeze")
    assert "[PASS] G2m: 所有 dev 的 ours/ablation run 都属于某个迭代行（4 轮）" in r.out
    assert "冻结前没有任何 confirm 评测" in r.out and "迭代 4 轮，预算 30 轮" in r.out


def test_g2m_unlogged_dev_run(proj):
    mkgroup(proj, "secret_s", 58.0, iteration=None)
    r = M(proj, "dev-check")
    bad(r, "未登记的 dev 实验 runs/secret_s0")
    assert "每次尝试都要记" in r.out


def test_g2m_unlogged_run_with_a_logged_iteration_tag_is_accepted(proj):
    mkgroup(proj, "extra_s", 54.0, iteration="I04", role="ablation", method="ours-noC")
    ok(M(proj, "dev-check"))


def test_g2m_untagged_run(proj):
    d = proj / "runs" / "mystery"
    d.mkdir()
    write(d / "eval.json", json.dumps({"metrics": {"ap": 61.0}}))
    bad(M(proj, "dev-check"), "run 没有 eval_split/role")


def test_g2m_run_with_args_but_no_role(proj):
    d = proj / "runs" / "half"
    d.mkdir()
    write(d / "args.json", json.dumps({"seed": 0, "eval_split": "dev"}))
    bad(M(proj, "dev-check"), "run 没有 eval_split/role")


def _rewrite_iter(p, fn):
    import csv
    path = p / "method" / "iterations.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    fn(rows)
    mt.write_csv_rows(str(path), mt.ITER_COLS, rows)


def test_g2m_row_without_hypothesis(proj):
    _rewrite_iter(proj, lambda rows: rows[1].__setitem__("hypothesis", ""))
    bad(M(proj, "dev-check"), "迭代 I02: 缺 hypothesis")


def test_g2m_row_whose_runs_match_nothing(proj):
    _rewrite_iter(proj, lambda rows: rows[0].__setitem__("runs", "runs/gone_*"))
    bad(M(proj, "dev-check"), "迭代 I01: runs = runs/gone_* 匹配不到任何 run 目录")


def test_g2m_missing_decision_with_a_later_iteration_is_a_warning(proj):
    _rewrite_iter(proj, lambda rows: rows[0].__setitem__("decision", ""))
    r = M(proj, "dev-check")
    assert r.fails == 0 and "[WARN] G2m: 迭代 I01: 已有后续迭代但没有 decision" in r.out, r.out


def test_g2m_confirm_evaluated_before_the_freeze(proj):
    mkrun(proj, "early", "confirm", "ours", "ours", 0, 61.0)
    bad(M(proj, "dev-check"), "冻结前评测了验证集（run runs/early）")


def test_g2m_budget_warn_fail_and_extension(proj):
    mut(proj, lambda st: st["method"]["budget"].__setitem__("max_iters", 3))
    r = M(proj, "dev-check")
    assert r.fails == 0 and "[WARN] G2m: 迭代 4 轮，超过 budget.max_iters = 3" in r.out, r.out
    mut(proj, lambda st: st["method"]["budget"].__setitem__("max_iters", 2))
    bad(M(proj, "dev-check"), "（>1.5 倍）")
    mut(proj, lambda st: st["method"]["budget"].__setitem__("extension", "reviewer-driven second benchmark"))
    r = M(proj, "dev-check")
    ok(r, "已有 extension")


def test_g2m_stall_warning(proj):
    mut(proj, lambda st: st["method"]["budget"].__setitem__("stall", 2))
    for k in (5, 6):
        mkgroup(proj, f"i0{k}_s", 50.0, iteration=f"I0{k}")
        log_add(proj, f"I0{k}", f"runs/i0{k}_s*", "drop")
    r = M(proj, "dev-check")
    assert r.fails == 0 and "[WARN] G2m: 连续 2 轮没有超过噪声的提升" in r.out and "停下来换假设或收手" in r.out, r.out


def test_g2m_no_stall_warning_while_still_improving(proj):
    mut(proj, lambda st: st["method"]["budget"].__setitem__("stall", 2))
    assert "连续" not in M(proj, "dev-check").out


# ------------------------------------------------------------------ freeze
def test_freeze_writes_the_state_and_prints_the_prereg_lines(proj):
    r = M(proj, "freeze", "--iteration", "I04")
    ok(r, "freeze: " + code_sha(proj)[:8])
    fz = state(proj)["method"]["freeze"]
    assert fz["iteration"] == "I04" and fz["code_sha256"] == code_sha(proj) and fz["k_iters"] == 4
    assert fz["dev_gain"] == pytest.approx(4.0) and fz["bias"] == pytest.approx((0.5 / 3) ** 0.5 * (2 * 1.386294) ** 0.5, abs=2e-3)
    assert fz["gain_adj"] == pytest.approx(fz["dev_gain"] - fz["bias"], abs=1e-5) and fz["date"]
    assert "§7 成功标准" in r.out and "code_sha256 = " + fz["code_sha256"] in r.out
    s = read(proj / "research-state.yaml")
    assert "# 方法轨道" in s and "# sha256 由 init 写" in s                     # written in place, comments kept


def test_freeze_refuses_when_dev_check_fails(proj):
    mkgroup(proj, "secret_s", 58.0)
    r = M(proj, "freeze", "--iteration", "I04")
    bad(r, "拒绝 freeze")
    assert "未登记的 dev 实验" in r.out and state(proj)["method"]["freeze"] == {}


def test_freeze_refuses_unknown_iteration(proj):
    bad(M(proj, "freeze", "--iteration", "I99"), "不在 method/iterations.csv")


def test_freeze_requires_decision_keep(proj):
    bad(M(proj, "freeze", "--iteration", "I02"), "decision 不是 keep")


def test_freeze_refused_once_the_confirm_set_was_evaluated(fro):
    add_confirm(fro)
    bad(M(fro, "freeze", "--iteration", "I04"), "已经有 confirm run")


def test_refreeze_before_any_confirm_run_is_allowed(fro):
    write(fro / "code" / "model.py", "def forward(x):\n    return x * 3\n")
    mkgroup(fro, "i05_s", 54.5, iteration="I05")
    log_add(fro, "I05", "runs/i05_s*", "keep")
    ok(M(fro, "freeze", "--iteration", "I05"))
    assert state(fro)["method"]["freeze"]["iteration"] == "I05"


# ------------------------------------------------------------------ G2m after the freeze
def test_g2m_frozen_pass(fro):
    r = M(fro, "dev-check")
    ok(r, "冻结的迭代 I04：decision = keep，3 个 seed")
    assert "扣掉挑选偏差后仍达标" in r.out and "K = 4" in r.out and "gain_adj" in r.out
    assert "组件 module_A: 去掉后掉 +2.0000" in r.out and "机制检验" in r.out and "基线 BaseNet 调参 6 次（含 published_config）" in r.out
    assert "代码与冻结时一致" in r.out


def test_g2m_frozen_iteration_not_keep(fro):
    _rewrite_iter(fro, lambda rows: rows[3].__setitem__("decision", "revise"))
    bad(M(fro, "dev-check"), "冻结的迭代 I04 的 decision 不是 keep")


def test_g2m_frozen_iteration_too_few_seeds(fro):
    rm(fro, "i04_s2")
    bad(M(fro, "dev-check"), "冻结的迭代 I04 只有 2 个 seed")


def test_g2m_winners_curse_fail(tmp_path, proj):
    # freeze I01 (gain 0.5): after the selection bias of K = 4 attempts nothing is left
    log_add(proj, "I01", "runs/i01_s*", "keep")
    ok(M(proj, "freeze", "--iteration", "I01"))
    r = M(proj, "dev-check")
    bad(r, "dev 上的提升不超过挑选噪声")
    assert "bias = se×√(2 ln K)" in r.out and "K = 4" in r.out


def test_g2m_winners_curse_warn(proj):
    log_add(proj, "I03", "runs/i03_s*", "keep")          # gain 1.5, se 0.41 -> bias 0.68 -> gain_adj 0.82 < min_effect 1
    ok(M(proj, "freeze", "--iteration", "I03"))
    r = M(proj, "dev-check")
    assert "[WARN] G2m: 扣掉从 4 次尝试里挑最好的偏差后只剩 gain_adj = +0.8" in r.out, r.out
    assert "加 dev seeds 或继续迭代" in r.out


def test_g2m_single_attempt_has_no_selection_bias(tmp_path):
    p = tmp_path / "one"
    p.mkdir()
    write(p / "research-state.yaml", STATE)
    write(p / "code" / "model.py", "x = 1\n")
    write(p / "data" / "confirm" / "c.txt", "c")
    mkgroup(p, "base_dev_s", 50.0, role="baseline", method="BaseNet")
    mkgroup(p, "i01_s", 53.0, iteration="I01")
    ok(M(p, "init"))
    log_add(p, "I01", "runs/i01_s*", "keep")
    ok(M(p, "freeze", "--iteration", "I01"))
    assert state(p)["method"]["freeze"]["bias"] == 0


def test_g2m_component_inside_noise(fro):
    rm(fro, "i04_noB_s*")
    mkgroup(fro, "i04_noB_s", 53.9, role="ablation", method="ours-noB", iteration="I04")
    r = M(fro, "dev-check")
    bad(r, "组件 module_B 在 dev 上去掉不掉点")
    assert "删掉它再冻结（方法越简单越好）" in r.out


def test_g2m_component_without_ablation_runs(fro):
    rm(fro, "i04_noA_s*")
    bad(M(fro, "dev-check"), "组件 module_A: 没有 dev 消融 run")


def test_g2m_no_components_registered_is_a_warning(fro):
    mut(fro, lambda st: st["method"].__setitem__("components", []))
    r = M(fro, "dev-check")
    assert r.fails == 0 and "[WARN] G2m: method.components 为空" in r.out, r.out


def test_g2m_mechanism_contradicted(fro):
    write(fro / "results" / "mech.json", json.dumps({"corr": 0.05}))
    r = M(fro, "dev-check")
    bad(r, "提升不是因为你说的原因")


def test_g2m_mechanism_missing_is_a_warning(fro):
    mut(fro, lambda st: st["method"].__setitem__("mechanism", {}))
    r = M(fro, "dev-check")
    assert r.fails == 0 and "[WARN] G2m: method.mechanism 未登记" in r.out, r.out


def test_g2m_mechanism_from_runs_and_sign(fro):
    mut(fro, lambda st: st["method"].__setitem__("mechanism", {"desc": "gate opens on bad frames", "run_glob": "runs/i04_s*", "key": "metrics.ap", "expect": "+"}))
    ok(M(fro, "dev-check"))
    mut(fro, lambda st: st["method"]["mechanism"].__setitem__("expect", "-"))
    bad(M(fro, "dev-check"), "预期 -")


def test_g2m_mechanism_data_missing(fro):
    (fro / "results" / "mech.json").unlink()
    bad(M(fro, "dev-check"), "读不到 corr")


def test_g2m_baseline_tuning_parity(fro):
    write(fro / "method" / "baseline_tuning.csv", "method,trial,config,dev_metric\nBaseNet,1,cfg,49.9\nBaseNet,2,cfg,50.0\n")
    bad(M(fro, "dev-check"), "基线没有得到同等调参预算：BaseNet 只调了 2 次")


def test_g2m_baseline_tuning_published_config_plus_five_is_enough(fro):
    write(fro / "method" / "baseline_tuning.csv", "method,trial,config,dev_metric\nBaseNet,published_config,d,49.8\n" + "".join(f"BaseNet,{k},c,49.9\n" for k in range(1, 6)))
    ok(M(fro, "dev-check"))


def test_g2m_baseline_tuning_file_missing(fro):
    (fro / "method" / "baseline_tuning.csv").unlink()
    bad(M(fro, "dev-check"), "baseline_tuning.csv 不存在")


def test_g2m_baseline_tuning_better_config_than_the_runs_is_a_warning(fro):
    write(fro / "method" / "baseline_tuning.csv", "method,trial,config,dev_metric\nBaseNet,published_config,d,49.8\n" + "".join(f"BaseNet,{k},c,{49.9 + k}\n" for k in range(1, 7)))
    r = M(fro, "dev-check")
    assert r.fails == 0 and "调参表里有比基线 runs 更好的 dev 配置" in r.out, r.out


def test_g2m_code_changed_after_freeze(fro):
    write(fro / "code" / "model.py", "def forward(x):\n    return x - 1\n")
    r = M(fro, "dev-check")
    bad(r, "冻结后代码改过")
    assert "重新登记一轮迭代并重新 freeze" in r.out


# ------------------------------------------------------------------ G4m
def test_g4m_confirmed(fro):
    add_confirm(fro)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "confirmed"))
    r = M(fro, "confirm-check")
    ok(r, "[PASS] G4m: confirmed：confirm gain +2.5000")
    assert "prereg 已锁定且含 freeze:" in r.out and "验证集看了 1 次，登记 1 次" in r.out
    assert "收缩：dev 提升 +4.0000" in r.out and "保留 62%" in r.out
    assert state(fro)["method"]["confirm"]["looks"][0]["id"].startswith("ours:")      # the look is on the register


def test_g4m_not_confirmed_is_a_legitimate_outcome(fro):
    add_confirm(fro, ours=50.4)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "not_confirmed"))
    r = M(fro, "confirm-check")
    ok(r, "[PASS] G4m: not_confirmed：confirm gain +0.4000")
    assert "两个诚实的出口" in r.out and "paper_type 改成 analysis" in r.out and "新的验证集" in r.out


def test_g4m_outcome_empty(fro):
    add_confirm(fro)
    bad(M(fro, "confirm-check"), "method.outcome 为空：数字说 confirmed")


def test_g4m_outcome_contradicts_the_numbers(fro):
    add_confirm(fro, ours=50.4)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "confirmed"))
    bad(M(fro, "confirm-check"), "method.outcome = confirmed，但数字说 not_confirmed")


def test_g4m_gain_above_min_effect_but_inside_noise(fro):
    add_confirm(fro, ours=51.5, ours_extra={}, base=50.0)
    rm(fro, "cf_ours_s*")
    mkgroup(fro, "cf_ours_s", 51.5, split="confirm", role="ours", method="ours", d=3.0, code=state(fro)["method"]["freeze"]["code_sha256"], extra={"lr": 1e-4}, delta=5.0)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "confirmed"))
    bad(M(fro, "confirm-check"), "但数字说 not_confirmed")


def test_g4m_too_few_confirm_seeds(fro):
    add_confirm(fro, n=2)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "confirmed"))
    bad(M(fro, "confirm-check"), "验证集上 ours 2 个、基线 2 个 run")


def test_g4m_no_confirm_runs(fro):
    bad(M(fro, "confirm-check"), "没有 eval_split=confirm 的 run")


def test_g4m_confirm_without_freeze(proj):
    add_confirm(proj, code="a" * 64)
    bad(M(proj, "confirm-check"), "还没有 method.freeze")


def test_g4m_prereg_not_locked(fro):
    add_confirm(fro)
    mut(fro, lambda st: (st["gates"]["G2"].__setitem__("prereg_sha256", ""), st["method"].__setitem__("outcome", "confirmed")))
    bad(M(fro, "confirm-check"), "prereg.md 没有锁定")


def test_g4m_prereg_lacks_the_freeze_hash(fro):
    add_confirm(fro)
    lock_prereg(fro, "# prereg\n§1 没写冻结的方法\n")
    bad(M(fro, "confirm-check"), "预注册没有写入冻结的方法")


def test_g4m_prereg_edited_after_the_lock(fro):
    add_confirm(fro)
    with open(fro / "prereg.md", "a", encoding="utf-8") as fh:
        fh.write("§8 事后补充\n")
    bad(M(fro, "confirm-check"), "锁后被改过")


def test_g4m_prereg_older_than_the_freeze(fro):
    add_confirm(fro)
    touch(fro / "prereg.md", -3600)
    bad(M(fro, "confirm-check"), "预注册在冻结之前锁的")


def test_g4m_confirm_run_evaluated_before_the_freeze(fro):
    add_confirm(fro, delta=-3600)
    bad(M(fro, "confirm-check"), "评测早于 freeze")


def test_g4m_confirm_run_with_other_code(fro):
    add_confirm(fro, code="0" * 64)
    r = M(fro, "confirm-check")
    bad(r, "confirm run runs/cf_ours_s0: code_sha256 00000000 ≠ 冻结的")


def test_g4m_confirm_run_without_code_hash(fro):
    add_confirm(fro)
    a = json.loads(read(fro / "runs" / "cf_ours_s1" / "args.json"))
    a.pop("code_sha256")
    write(fro / "runs" / "cf_ours_s1" / "args.json", json.dumps(a))
    bad(M(fro, "confirm-check"), "args.json 没有 code_sha256")


def test_g4m_code_changed_after_the_freeze(fro):
    add_confirm(fro)
    write(fro / "code" / "model.py", "def forward(x):\n    return x - 2\n")
    bad(M(fro, "confirm-check"), "验证集结果不是冻结代码产生的")


def test_g4m_two_looks_at_the_confirm_set(fro):
    add_confirm(fro)
    mkgroup(fro, "cf_ours_b_s", 52.6, split="confirm", role="ours", method="ours", code=state(fro)["method"]["freeze"]["code_sha256"], extra={"lr": 5e-5}, delta=5.0)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "confirmed"))
    r = M(fro, "confirm-check")
    bad(r, "验证集看了 2 次（登记 1 次）")
    assert "换新的验证集或如实报告" in r.out


def test_g4m_looks_register_survives_deleted_runs(fro):
    add_confirm(fro)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "confirmed"))
    ok(M(fro, "confirm-check"))
    rm(fro, "cf_ours_s*")
    mkgroup(fro, "cf_ours_b_s", 52.6, split="confirm", role="ours", method="ours", code=state(fro)["method"]["freeze"]["code_sha256"], extra={"lr": 5e-5}, delta=5.0)
    bad(M(fro, "confirm-check"), "验证集看了 2 次（登记 1 次）")      # the first look is remembered although its runs are gone


def test_g4m_seeds_of_one_variant_are_one_look(fro):
    add_confirm(fro, n=4)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "confirmed"))
    ok(M(fro, "confirm-check"), "验证集看了 1 次")


def test_g4m_baseline_with_several_configs_is_a_warning(fro):
    add_confirm(fro)
    mkgroup(fro, "cf_base_b_s", 50.5, split="confirm", role="baseline", method="BaseNet", code=state(fro)["method"]["freeze"]["code_sha256"], extra={"lr": 5e-4}, delta=5.0)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "confirmed"))
    r = M(fro, "confirm-check")
    assert "[WARN] G4m: 基线 BaseNet 在验证集上有 2 种配置" in r.out, r.out


# ------------------------------------------------------------------ status / wiring
def test_status_one_screen(fro):
    r = M(fro, "status")
    assert r.returncode == 0 and not r.crashed, r.out
    for s in ("G1c        GO (headroom H = 8.0000", "K = 4", "冻结       I04", "confirm run 0 个", "结论       （未定）"):
        assert s in r.out, r.out


def test_exit_code_is_nonzero_on_fail(proj):
    mut(proj, lambda st: st["method"]["benchmark"].__setitem__("name", ""))
    assert M(proj, "headroom").returncode == 1
    assert M(proj.parent / "proj", "dev-check").returncode == 0


def test_every_subcommand_answers_help_under_a_gbk_console():
    from conftest import GBK_ENV
    import subprocess
    r = subprocess.run([sys.executable, str(SCRIPTS / "method_track.py"), "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=GBK_ENV)
    assert r.returncode == 0 and "headroom" in r.stdout
