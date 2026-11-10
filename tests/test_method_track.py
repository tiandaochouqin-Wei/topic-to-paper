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
    oracle: {desc: "GT routing", run_glob: "runs/oracle_dev_s*", key: "", applied: "train+test", sanity: {setting: "night failures injected on dev, oracle told where", why: "the injected failure is the only limiting factor", baseline_glob: "runs/san_base_s*", oracle_glob: "runs/san_orc_s*", key: ""}}
    cheap_fixes:
      - {name: augmentation, run_glob: "runs/aug_dev_s*", key: ""}
      - {name: longer_training, run_glob: "runs/long_dev_s*", key: ""}
  budget: {max_iters: 30, stall: 5, iter_hours: 2}
  prior_art: {min_queries: 3, min_works: 3, independent_waiver: ""}
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


def log_add(p, i, runs, decision=None, hyp="假设", change="改动", idea=None):
    a = ["log", "add", "--id", i, "--hypothesis", hyp, "--change", change, "--runs", runs]
    if decision:
        a += ["--decision", decision]
    if idea:
        a += ["--idea", idea]
    r = M(p, *a)
    assert r.fails == 0 and not r.crashed, r.out
    return r


# ---- prior-art record ("查撞车"): ideas N1 (differs) and N2..N4 (clear) carry a full record; N5 is still open and has none
def prior_rows(idea, base, closest_first=False):
    rows = []
    for k, (q, s) in enumerate([("mechanism words", "arXiv"), ("goal words", "Google Scholar"), ("other field words", "arXiv")]):
        rows.append(dict(idea=idea, query=f"{idea} {q}", source=s, date="2026-11-10", work=f"Prior work {idea}-{k}", year="2024",
                         ref=f"2301.{base * 10 + k:05d}", overlap="related", difference="", searched_by="independent" if k == 2 else "self"))
    if closest_first:
        rows[0].update(overlap="same_goal", difference="uses a fixed gate instead of a learned one")
    return rows


def write_ideas(p, verdicts=None):
    verdicts = verdicts or {"N1": ("differs", "2301.00010"), "N2": ("clear", ""), "N3": ("clear", ""), "N4": ("clear", ""), "N5": ("", "")}
    rows = [dict(id=f"N{k}", type=t, mechanism="m", predicted_effect="+1", cheapest_test="1 seed", kill_result="<0.2", status="open",
                 prior_art=verdicts[f"N{k}"][0], closest_work=verdicts[f"N{k}"][1])
            for k, t in enumerate(["data", "objective", "architecture", "inference", "training"], 1)]
    mt.write_csv_rows(str(p / "method" / "ideas.csv"), mt.IDEA_COLS, rows)


def write_prior(p):
    rows = prior_rows("N1", 1, closest_first=True) + prior_rows("N2", 2) + prior_rows("N3", 3) + prior_rows("N4", 4)
    mt.write_csv_rows(str(p / "method" / "prior_art.csv"), mt.PRIOR_COLS, rows)


def edit_csv(p, name, cols, fn):
    path = str(p / "method" / name)
    rows, _ = mt.read_csv_rows(path)
    fn(rows)
    mt.write_csv_rows(path, cols, rows)


def edit_ideas(p, fn):
    edit_csv(p, "ideas.csv", mt.IDEA_COLS, fn)


def edit_prior(p, fn):
    edit_csv(p, "prior_art.csv", mt.PRIOR_COLS, fn)


def n1_rows(rows):
    return [r for r in rows if r["idea"] == "N1"]


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
    mkgroup(p, "san_base_s", 50.0, split="sanity", role="baseline", method="BaseNet")      # oracle self-check: known-answer case, the oracle must win
    mkgroup(p, "san_orc_s", 55.0, split="sanity", role="oracle", method="oracle")
    for i, (m_, dec) in enumerate([(50.5, "drop"), (52.0, "revise"), (51.5, "drop"), (54.0, "keep")], 1):
        mkgroup(p, f"i0{i}_s", m_, iteration=f"I0{i}")
    mkgroup(p, "i04_noA_s", 52.0, role="ablation", method="ours-noA", iteration="I04")
    mkgroup(p, "i04_noB_s", 52.0, role="ablation", method="ours-noB", iteration="I04")
    r = M(p, "init")
    assert r.fails == 0 and not r.crashed, r.out
    write(p / "method" / "bottleneck.md", BOTTLENECK)
    write(p / "method" / "baseline_tuning.csv",
          "method,trial,config,dev_metric\nBaseNet,published_config,default,49.8\n" + "".join(f"BaseNet,{k},cfg{k},{49.5 + k * 0.1:.1f}\n" for k in range(1, 7)))
    write_ideas(p)
    write_prior(p)
    for i, (dec, idea) in enumerate([("drop", "N2"), ("revise", "N3"), ("drop", "N4"), ("keep", "N1")], 1):
        log_add(p, f"I0{i}", f"runs/i0{i}_s*", dec, idea=idea)
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
    rm(proj, "san_orc_s*")
    mkgroup(proj, "san_orc_s", 45.0, split="sanity", role="oracle", method="oracle")        # on the known-answer case the oracle is LOWER = better
    r = M(proj, "headroom")
    bad(r, "理想地解决它反而更差")   # higher numbers are now worse
    assert "oracle 自检通过" in r.out and "NO-GO" in r.out


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
    for fn in ("bottleneck.md", "ideas.csv", "iterations.csv", "baseline_tuning.csv", "prior_art.csv"):
        assert (p / "method" / fn).exists()
    assert read(p / "method" / "prior_art.csv").splitlines()[0] == ",".join(mt.PRIOR_COLS)
    assert mt.read_csv_rows(str(p / "method" / "prior_art.csv"))[0] == []      # only the commented example row: no records yet
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
    edit_ideas(proj, lambda rows: rows[0].__setitem__("kill_result", ""))
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
    log_add(fro, "I05", "runs/i05_s*", "keep", idea="N1")
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
    write_ideas(p)
    write_prior(p)
    log_add(p, "I01", "runs/i01_s*", "keep", idea="N1")
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


def test_status_has_a_prior_art_line(proj):
    r = M(proj, "status")
    assert "查撞车     4 / 5 个想法有结论，其中 done 0 个" in r.out, r.out
    edit_ideas(proj, lambda rows: rows[1].__setitem__("prior_art", "done"))
    assert "其中 done 1 个" in M(proj, "status").out


def test_exit_code_is_nonzero_on_fail(proj):
    mut(proj, lambda st: st["method"]["benchmark"].__setitem__("name", ""))
    assert M(proj, "headroom").returncode == 1
    assert M(proj.parent / "proj", "dev-check").returncode == 0


def test_every_subcommand_answers_help_under_a_gbk_console():
    from conftest import GBK_ENV
    import subprocess
    r = subprocess.run([sys.executable, str(SCRIPTS / "method_track.py"), "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=GBK_ENV)
    assert r.returncode == 0 and "headroom" in r.stdout


# ------------------------------------------------------------------ prior art ("查撞车"): the record of one idea
def freeze_i04(p):
    return M(p, "freeze", "--iteration", "I04")


def refused(r, needle):
    bad(r, needle)
    assert "拒绝 freeze" in r.out and "冻结之前查撞车" in r.out, r.out


def test_prior_clean_record_passes_everywhere(proj):
    ctx = mt.Ctx(str(proj))
    assert all(mt.prior_findings(ctx, f"N{k}") == [] for k in (1, 2, 3, 4))
    r = M(proj, "ideas-check")
    ok(r, "[PASS] G2m: 查撞车：4 个进入 dev 循环的想法")
    assert "先查撞车" not in r.out
    ok(freeze_i04(proj))
    assert state(proj)["method"]["freeze"]["iteration"] == "I04"


def test_prior_too_few_queries(proj):
    edit_prior(proj, lambda rows: [r.__setitem__("query", "same words") for r in n1_rows(rows)])
    refused(freeze_i04(proj), "不同的查询 1/3")
    assert state(proj)["method"]["freeze"] == {}


def test_prior_query_dedup_ignores_case_and_spaces(proj):
    def f(rows):
        for r, q in zip(n1_rows(rows), ["Mechanism  Words", "mechanism words", " MECHANISM words "]):
            r["query"] = q
    edit_prior(proj, f)
    refused(freeze_i04(proj), "不同的查询 1/3")


def test_prior_one_source_only(proj):
    edit_prior(proj, lambda rows: [r.__setitem__("source", "arXiv") for r in n1_rows(rows)])
    refused(freeze_i04(proj), "不同的来源 1/2")


def test_prior_three_queries_message_names_the_three_kinds(proj):
    edit_prior(proj, lambda rows: [r.__setitem__("query", "x") for r in n1_rows(rows)])
    r = freeze_i04(proj)
    assert "「机制的词」「目标问题的词」「别的领域会怎么叫它」" in r.out, r.out


def test_prior_fewer_than_three_valid_refs(proj):
    def f(rows):
        for r in n1_rows(rows)[1:]:
            r["work"] = r["ref"] = ""            # a query that found nothing: one row with an empty work
    edit_prior(proj, f)
    r = freeze_i04(proj)
    refused(r, "只有 1 个带有效 ref 的相近工作（要求 ≥3）")
    assert "搜不到相近工作通常说明搜得不对，不说明没人做过" in r.out


def test_prior_duplicate_refs_count_once(proj):
    def f(rows):
        for r, ref in zip(n1_rows(rows), ["2301.00010", "arXiv:2301.00010", "2301.00010v2"]):
            r["ref"] = ref
    edit_prior(proj, f)
    refused(freeze_i04(proj), "只有 1 个带有效 ref")


@pytest.mark.parametrize("ref", ["", "see my notes", "arXiv:23.1", "doi:10.1/x", "10.12/short"])
def test_prior_invalid_ref_is_named(proj, ref):
    edit_prior(proj, lambda rows: n1_rows(rows)[1].__setitem__("ref", ref))
    r = freeze_i04(proj)
    refused(r, "ref 缺失或格式不对")
    assert "Prior work N1-1" in r.out, r.out


@pytest.mark.parametrize("ref", ["10.1109/CVPR.2024.01234", "arXiv:2301.01234", "2301.01234", "2301.01234v3", "https://openreview.net/forum?id=abc"])
def test_prior_valid_ref_forms(proj, ref):
    edit_prior(proj, lambda rows: n1_rows(rows)[1].__setitem__("ref", ref))
    ok(freeze_i04(proj))


def test_prior_invalid_ref_is_reported_even_when_three_others_are_valid(proj):
    edit_prior(proj, lambda rows: rows.append(dict(idea="N1", query="N1 more", source="arXiv", work="Broken entry", ref="", overlap="related", searched_by="self")))
    r = freeze_i04(proj)
    refused(r, "ref 缺失或格式不对")
    assert "Broken entry" in r.out


@pytest.mark.parametrize("ov", ["same_mechanism", "same_goal"])
def test_prior_overlap_without_difference(proj, ov):
    edit_prior(proj, lambda rows: n1_rows(rows)[1].update(overlap=ov, difference=""))
    refused(freeze_i04(proj), "必须写 difference")


def test_prior_unknown_overlap_value_is_reported(proj):
    edit_prior(proj, lambda rows: n1_rows(rows)[1].__setitem__("overlap", "kind_of_similar"))
    refused(freeze_i04(proj), "overlap 只能是 same_mechanism | same_goal | related | none")


def test_prior_verdict_missing(proj):
    edit_ideas(proj, lambda rows: rows[0].__setitem__("prior_art", ""))
    refused(freeze_i04(proj), "prior_art 还没有结论")


def test_prior_verdict_not_in_vocabulary(proj):
    edit_ideas(proj, lambda rows: rows[0].__setitem__("prior_art", "probably fine"))
    refused(freeze_i04(proj), "只能是 clear | differs | done")


def test_prior_same_mechanism_work_and_verdict_clear(proj):
    edit_prior(proj, lambda rows: [r.update(overlap="same_mechanism", difference="uses a gate") for r in rows if r["idea"] == "N2"][:1])
    r = M(proj, "ideas-check")
    assert r.fails == 0 and r.returncode == 0 and "[WARN] G2m: 先查撞车再花算力：想法 N2: 有同机制的已有工作，结论不能是 clear" in r.out, r.out
    assert "查撞车：4 个进入" not in r.out


def test_prior_verdict_done_while_the_idea_is_not_abandoned(proj):
    edit_ideas(proj, lambda rows: rows[1].__setitem__("prior_art", "done"))
    r = M(proj, "ideas-check")
    assert r.fails == 0 and "想法 N2: 已有工作做过：放弃这个想法，或把那篇工作复现成基线（它就是最强基线的候选）" in r.out, r.out


@pytest.mark.parametrize("status", ["dropped", "Killed", "drop", "KILL"])
def test_prior_verdict_done_and_abandoned_is_fine(proj, status):
    edit_ideas(proj, lambda rows: rows[1].update(prior_art="done", status=status))
    r = M(proj, "ideas-check")
    assert r.fails == 0 and "已有工作做过" not in r.out and "[PASS] G2m: 查撞车：4 个进入" in r.out, r.out


@pytest.mark.parametrize("status", ["dropped", "killed"])
def test_freeze_refuses_an_idea_that_was_abandoned_as_done(proj, status):
    edit_ideas(proj, lambda rows: rows[0].update(prior_art="done", status=status))
    refused(freeze_i04(proj), "不能冻结成你的方法")


def test_prior_differs_needs_closest_work(proj):
    edit_ideas(proj, lambda rows: rows[0].__setitem__("closest_work", ""))
    refused(freeze_i04(proj), "结论是 differs 就要在 closest_work 写最接近那篇工作的 ref")


def test_prior_closest_work_must_be_a_ref_of_the_record(proj):
    edit_ideas(proj, lambda rows: rows[0].__setitem__("closest_work", "2301.99999"))
    refused(freeze_i04(proj), "closest_work = 2301.99999 不是 prior_art.csv 里这个想法任何一行的 ref")
    edit_ideas(proj, lambda rows: rows[0].__setitem__("closest_work", "arXiv:2301.00011v2"))      # another row, other spelling of the same id
    ok(freeze_i04(proj))


def test_prior_unknown_idea_code(proj):
    assert [c for c, _ in mt.prior_findings(mt.Ctx(str(proj)), "N9")] == ["unknown"]


def test_prior_self_only_fails_at_freeze(proj):
    edit_prior(proj, lambda rows: [r.__setitem__("searched_by", "self") for r in rows])
    r = freeze_i04(proj)
    refused(r, "只有自己查的记录：让一个新上下文的子代理只拿机制一句话和任务名再查一遍")
    assert [c for c, _ in mt.prior_findings(mt.Ctx(str(proj)), "N1")] == ["self_only"]


def test_prior_self_only_is_a_warning_with_a_waiver(proj):
    edit_prior(proj, lambda rows: [r.__setitem__("searched_by", "self") for r in rows])
    mut(proj, lambda st: st["method"]["prior_art"].__setitem__("independent_waiver", "no subagent budget this week, reviewer will search"))
    r = freeze_i04(proj)
    ok(r)
    assert "[WARN] G2m: 冻结之前查撞车：想法 N1: 只有自己查的记录" in r.out and "no subagent budget this week" in r.out, r.out
    assert state(proj)["method"]["freeze"]["iteration"] == "I04"


def test_prior_waiver_does_not_excuse_other_findings(proj):
    edit_prior(proj, lambda rows: [r.update(searched_by="self", source="arXiv") for r in n1_rows(rows)])
    mut(proj, lambda st: st["method"]["prior_art"].__setitem__("independent_waiver", "no subagent"))
    refused(freeze_i04(proj), "不同的来源 1/2")


def test_prior_thresholds_come_from_the_state(proj):
    mut(proj, lambda st: st["method"]["prior_art"].update(min_queries=4))
    refused(freeze_i04(proj), "不同的查询 3/4")
    mut(proj, lambda st: st["method"]["prior_art"].update(min_queries=2, min_works=2))
    edit_prior(proj, lambda rows: [r.__setitem__("query", "q") for r in n1_rows(rows)[2:]])
    ok(freeze_i04(proj))


def test_prior_missing_file_is_a_failure_at_freeze(proj):
    (proj / "method" / "prior_art.csv").unlink()
    refused(freeze_i04(proj), "不同的查询 0/3")


def test_prior_default_path_when_the_state_has_no_files_entry():
    d = mt.mfiles({"files": {"ideas": "x/ideas.csv"}})
    assert d["prior_art"] == "method/prior_art.csv" and d["ideas"] == "x/ideas.csv" and mt.mfiles({})["prior_art"] == "method/prior_art.csv"
    assert mt.mfiles({"files": {"prior_art": "pa/records.csv"}})["prior_art"] == "pa/records.csv"


def test_prior_custom_path_is_honoured(proj):
    shutil.move(str(proj / "method" / "prior_art.csv"), str(proj / "method" / "records.csv"))
    mut(proj, lambda st: st["method"]["files"].__setitem__("prior_art", "method/records.csv"))
    ok(freeze_i04(proj))


# ---- where it is called
def test_prior_freeze_refuses_an_iteration_without_idea(proj):
    mkgroup(proj, "i05_s", 55.0, iteration="I05")
    log_add(proj, "I05", "runs/i05_s*", "keep")
    r = M(proj, "freeze", "--iteration", "I05")
    bad(r, "迭代 I05 没有 idea")
    assert "冻结之前查撞车" in r.out and state(proj)["method"]["freeze"] == {}


def test_prior_freeze_refuses_an_idea_missing_from_ideas_csv(proj):
    _rewrite_iter(proj, lambda rows: rows[3].__setitem__("idea", "N9"))
    refused(freeze_i04(proj), "想法 N9 不在 method/ideas.csv 里")


def test_prior_log_add_without_idea_warns_and_logs(proj):
    mkgroup(proj, "i05_s", 53.0, iteration="I05")
    r = M(proj, "log", "add", "--id", "I05", "--hypothesis", "h", "--change", "c", "--runs", "runs/i05_s*")
    assert r.fails == 0 and r.returncode == 0 and not r.crashed, r.out
    assert "[WARN] G2m: 这一轮在试 ideas.csv 里的哪个想法？加 --idea" in r.out, r.out
    rows = mt.read_csv_rows(str(proj / "method" / "iterations.csv"))[0]
    assert len(rows) == 5 and rows[-1]["id"] == "I05" and rows[-1]["idea"] == ""


def test_prior_log_add_with_unknown_idea_refuses(proj):
    mkgroup(proj, "i05_s", 53.0, iteration="I05")
    r = M(proj, "log", "add", "--id", "I05", "--idea", "N9", "--hypothesis", "h", "--change", "c", "--runs", "runs/i05_s*")
    bad(r, "想法 N9 不在 method/ideas.csv 里")
    assert len(mt.read_csv_rows(str(proj / "method" / "iterations.csv"))[0]) == 4


def test_prior_log_add_with_findings_warns_but_logs(proj):
    mkgroup(proj, "i05_s", 53.0, iteration="I05")
    r = M(proj, "log", "add", "--id", "I05", "--idea", "N5", "--hypothesis", "h", "--change", "c", "--runs", "runs/i05_s*")
    assert r.fails == 0 and r.returncode == 0 and not r.crashed, r.out
    assert "[WARN] G2m: 先查撞车再花算力：想法 N5: 查撞车记录不够" in r.out and "还没有结论" in r.out and "只有自己查的记录" in r.out, r.out
    rows = mt.read_csv_rows(str(proj / "method" / "iterations.csv"))[0]
    assert len(rows) == 5 and rows[-1]["idea"] == "N5"


def test_prior_log_add_with_a_clean_idea_prints_no_prior_art_warning(proj):
    mkgroup(proj, "i05_s", 53.0, iteration="I05")
    r = log_add(proj, "I05", "runs/i05_s*", "drop", idea="N2")
    assert "先查撞车" not in r.out and "加 --idea" not in r.out, r.out


def test_prior_log_update_keeps_the_idea_of_the_row(proj):
    r = log_add(proj, "I04", "runs/i04_s*", "keep")
    assert "加 --idea" not in r.out
    assert mt.read_csv_rows(str(proj / "method" / "iterations.csv"))[0][3]["idea"] == "N1"
    log_add(proj, "I04", "runs/i04_s*", "keep", idea="N2")           # --idea on an update replaces it
    assert mt.read_csv_rows(str(proj / "method" / "iterations.csv"))[0][3]["idea"] == "N2"


def test_prior_ideas_check_ignores_open_ideas_without_iterations(proj):
    r = M(proj, "ideas-check")
    assert "N5" not in r.out, r.out


def test_prior_ideas_check_checks_ideas_that_are_running(proj):
    edit_ideas(proj, lambda rows: rows[4].__setitem__("status", "running"))
    r = M(proj, "ideas-check")
    assert r.fails == 0 and "[WARN] G2m: 先查撞车再花算力：想法 N5: 查撞车记录不够" in r.out, r.out


def test_prior_ideas_check_checks_ideas_referenced_by_an_iteration(proj):
    edit_prior(proj, lambda rows: [r.__setitem__("searched_by", "self") for r in n1_rows(rows)])
    r = M(proj, "ideas-check")
    assert r.returncode == 0 and "想法 N1: 只有自己查的记录" in r.out and "想法 N2" not in r.out, r.out


def test_prior_ideas_check_with_nothing_started_is_an_info_line(proj):
    mt.write_csv_rows(str(proj / "method" / "iterations.csv"), mt.ITER_COLS, [])
    r = M(proj, "ideas-check")
    assert r.returncode == 0 and "[INFO] G2m: 查撞车：还没有想法进入 dev 循环" in r.out, r.out


def test_prior_dev_check_before_freeze_warns_for_keep_rows(proj):
    edit_prior(proj, lambda rows: [r.__setitem__("searched_by", "self") for r in n1_rows(rows)])
    r = M(proj, "dev-check")
    assert r.fails == 0 and "[WARN] G2m: 迭代 I04 冻结前先查撞车：想法 N1: 只有自己查的记录" in r.out, r.out
    edit_prior(proj, lambda rows: [r.__setitem__("searched_by", "self") for r in rows if r["idea"] == "N2"])
    assert "想法 N2" not in M(proj, "dev-check").out                    # I01 (N2) is not a keep row: only keep rows are looked at


def test_prior_dev_check_before_freeze_warns_for_a_keep_row_without_idea(proj):
    mkgroup(proj, "i05_s", 55.0, iteration="I05")
    log_add(proj, "I05", "runs/i05_s*", "keep")
    r = M(proj, "dev-check")
    assert r.fails == 0 and "[WARN] G2m: 迭代 I05 是 keep 但没有 idea" in r.out, r.out


def test_prior_dev_check_after_freeze_passes_and_lists_the_overlapping_works(fro):
    r = M(fro, "dev-check")
    ok(r, "[PASS] G2m: 查撞车：想法 N1 的记录齐全")
    assert "[INFO] G2m: 论文的相关工作与对比表要正面交代：Prior work N1-0 (2301.00010)" in r.out, r.out


def test_prior_dev_check_after_freeze_reports_a_record_broken_later(fro):
    edit_prior(fro, lambda rows: [r.__setitem__("searched_by", "self") for r in n1_rows(rows)])
    r = M(fro, "dev-check")
    bad(r, "冻结的迭代 I04（想法 N1）查撞车：想法 N1: 只有自己查的记录")
    assert "论文的相关工作与对比表要正面交代" in r.out


def test_prior_dev_check_after_freeze_honours_the_waiver(fro):
    edit_prior(fro, lambda rows: [r.__setitem__("searched_by", "self") for r in n1_rows(rows)])
    mut(fro, lambda st: st["method"]["prior_art"].__setitem__("independent_waiver", "no subagent"))
    r = M(fro, "dev-check")
    ok(r, "[WARN] G2m: 冻结的迭代 I04（想法 N1）查撞车：想法 N1: 只有自己查的记录")


def test_prior_dev_check_after_freeze_fails_when_the_frozen_iteration_lost_its_idea(fro):
    _rewrite_iter(fro, lambda rows: rows[3].__setitem__("idea", ""))
    bad(M(fro, "dev-check"), "冻结的迭代 I04 没有 idea")


def test_prior_old_iterations_csv_without_the_idea_column_still_loads(proj):
    edit_csv(proj, "iterations.csv", [c for c in mt.ITER_COLS if c != "idea"], lambda rows: None)
    assert "idea" not in read(proj / "method" / "iterations.csv").splitlines()[0].split(",")
    r = M(proj, "dev-check")
    assert r.fails == 0 and "[WARN] G2m: 迭代 I04 是 keep 但没有 idea" in r.out, r.out
    mkgroup(proj, "i05_s", 53.0, iteration="I05")
    log_add(proj, "I05", "runs/i05_s*", "drop", idea="N5")
    rows = mt.read_csv_rows(str(proj / "method" / "iterations.csv"))[0]
    assert "idea" in read(proj / "method" / "iterations.csv").splitlines()[0].split(",")
    assert [r["id"] for r in rows] == ["I01", "I02", "I03", "I04", "I05"] and [r["idea"] for r in rows] == ["", "", "", "", "N5"]
    assert rows[3]["decision"] == "keep" and float(rows[3]["gain"]) == pytest.approx(4.0)


def test_prior_old_ideas_csv_without_the_new_columns_still_loads(proj):
    write(proj / "method" / "ideas.csv", "id,type,mechanism,predicted_effect,cheapest_test,kill_result,status\n" + "".join(
        f"N{k},{t},m,+1,1 seed,<0.2,open\n" for k, t in enumerate(["data", "objective", "architecture", "inference", "training"], 1)))
    r = M(proj, "ideas-check")
    assert r.fails == 0 and r.returncode == 0 and not r.crashed and "prior_art 还没有结论" in r.out, r.out


def test_prior_commented_example_row_is_not_a_record(tmp_path):
    p = tmp_path / "p"
    p.mkdir()
    shutil.copy(os.path.join(mt.SKILL, "templates", "method", "prior_art.csv"), p / "x.csv")
    assert mt.read_csv_rows(str(p / "x.csv"))[0] == []


# ------------------------------------------------------------------ oracle self-check and the third verdict
def set_oracle(p, mean, n=3):
    rm(p, "oracle_dev_s*")
    mkgroup(p, "oracle_dev_s", mean, role="oracle", method="oracle", n=n)


def set_sanity(p, oracle_mean=None, base_mean=None, n_o=3, n_b=3):
    if oracle_mean is not None:
        rm(p, "san_orc_s*")
        mkgroup(p, "san_orc_s", oracle_mean, split="sanity", role="oracle", method="oracle", n=n_o)
    if base_mean is not None:
        rm(p, "san_base_s*")
        mkgroup(p, "san_base_s", base_mean, split="sanity", role="baseline", method="BaseNet", n=n_b)


def no_sanity(p):
    mut(p, lambda st: st["method"]["headroom"]["oracle"].__setitem__("sanity", {}))


def invalid(r):
    assert r.returncode == 1 and not r.crashed, r.out
    assert "[FAIL] G1c: INVALID (" in r.out and "NO-GO" not in r.out and "G1c: GO" not in r.out, r.out
    assert "oracle 未通过自检或未自检，结论不能读成\"瓶颈没有提升空间\"：修好 oracle 再跑 headroom)" in r.out, r.out
    assert r.out.rstrip().splitlines()[-1].startswith("[FAIL] G1c: INVALID (")             # the verdict is the last line


def test_oracle_sanity_pass_keeps_go_without_a_warning(proj):
    r = M(proj, "headroom")
    ok(r, "[PASS] G1c: GO (headroom H = 8.0000")
    assert "oracle sanity = pass" in r.out and "oracle 没做过自检" not in r.out and "[WARN]" not in r.out, r.out
    assert "[PASS] G1c: oracle 自检通过：在已知答案的情形（night failures injected on dev, oracle t）里 oracle 比基线好 G_s = 5.0000 ≥ 1.5000" in r.out, r.out


def test_oracle_sanity_missing_with_large_h_is_go_with_a_warning(proj):
    no_sanity(proj)
    r = M(proj, "headroom")
    ok(r, "[PASS] G1c: GO (")
    assert "oracle sanity = missing" in r.out and "[WARN] G1c: oracle 没做过自检：H 是正的所以影响小，仍建议补 headroom.oracle.sanity" in r.out, r.out


def test_oracle_sanity_block_absent_is_missing(proj):
    mut(proj, lambda st: st["method"]["headroom"]["oracle"].pop("sanity"))
    ok(M(proj, "headroom"), "oracle sanity = missing")


def test_oracle_no_sanity_and_worse_than_baseline_is_invalid(proj):
    no_sanity(proj)
    set_oracle(proj, 48.0)
    r = M(proj, "headroom")
    invalid(r)
    assert "oracle 比基线差（oracle 48.0000 vs 基线 50.0000，H = -2.0000），但 oracle 没做过自检：分不清是瓶颈判断错了还是 oracle 构造错了" in r.out, r.out
    assert "先在已知答案的情形里证明这个 oracle 会赢（headroom.oracle.sanity），再读这个 H" in r.out
    assert "理想地解决它反而更差" not in r.out and "只在推理时加" not in r.out and "oracle sanity = missing" in r.out


def test_oracle_test_only_adds_the_most_common_cause(proj):
    no_sanity(proj)
    set_oracle(proj, 48.0)
    mut(proj, lambda st: st["method"]["headroom"]["oracle"].__setitem__("applied", "test_only"))
    r = M(proj, "headroom")
    invalid(r)
    assert "这个 oracle 只在推理时加、模型训练时没见过它，这是 oracle 不涨反跌最常见的原因：做一个训练时也给 oracle 信号的版本（applied: train+test）" in r.out, r.out


def test_oracle_no_sanity_and_small_headroom_is_invalid(proj):
    no_sanity(proj)
    set_oracle(proj, 50.8)
    r = M(proj, "headroom")
    invalid(r)
    assert "提升空间不足（H = 0.8000 < 1.5000），但 oracle 没做过自检" in r.out and "瞄准的瓶颈没有提升空间" not in r.out, r.out


def test_oracle_no_sanity_h_exactly_zero_is_still_invalid(proj):
    no_sanity(proj)
    set_oracle(proj, 50.0)
    invalid(M(proj, "headroom"))


def test_oracle_with_a_passing_sanity_keeps_the_old_messages_and_no_go(proj):
    set_oracle(proj, 48.0)
    r = M(proj, "headroom")
    bad(r, "瞄准的瓶颈判断错了：理想地解决它反而更差")
    assert "[FAIL] G1c: NO-GO (" in r.out and "INVALID" not in r.out and "oracle sanity = pass" in r.out, r.out
    set_oracle(proj, 50.8)
    r = M(proj, "headroom")
    bad(r, "瞄准的瓶颈没有提升空间（oracle 只比基线好 H = 0.8000")
    assert "[FAIL] G1c: NO-GO (" in r.out and "INVALID" not in r.out


def test_oracle_failed_sanity_is_invalid_even_with_a_large_headroom(proj):
    set_sanity(proj, oracle_mean=49.0)
    rm(proj, "aug_dev_s*")
    mkgroup(proj, "aug_dev_s", 57.0, role="cheap_fix", method="aug")             # would be "no foothold" if the residual were evaluated
    r = M(proj, "headroom")
    invalid(r)
    assert "[FAIL] G1c: oracle 自检没过：在本该赢的情形里也没赢（oracle 49.0000 vs 基线 50.0000，G_s = -1.0000 < 1.5000）" in r.out, r.out
    assert "oracle 的构造有问题（常见：模型训练时没见过 oracle 给的信号；oracle 信息接错了位置），先修 oracle，下面的 H 不能用" in r.out
    assert "[INFO] G1c: 提升空间：oracle 58.0000 vs 基线 50.0000，H = 8.0000 ≥ 1.5000" in r.out and "oracle 自检没过：不能当证据" in r.out
    assert "[PASS] G1c: 提升空间" not in r.out
    assert "oracle sanity = fail" in r.out


def test_oracle_failed_sanity_skips_the_cheap_fix_residual(proj):
    set_sanity(proj, oracle_mean=49.0)
    rm(proj, "aug_dev_s*")
    mkgroup(proj, "aug_dev_s", 57.0, role="cheap_fix", method="aug")
    r = M(proj, "headroom")
    assert "便宜做法 augmentation: 提升 +7.0000，占提升空间 88%" in r.out and "便宜做法 longer_training: 提升 +3.0000" in r.out      # the per-fix INFO lines stay
    assert "已经拿走" not in r.out and "方法没有立足点" not in r.out and "剩余空间 R" not in r.out, r.out
    assert "residual after cheap fixes R = nan" in r.out


def test_oracle_failed_sanity_with_a_negative_h_is_info_only(proj):
    set_sanity(proj, oracle_mean=49.0)
    set_oracle(proj, 48.0)
    r = M(proj, "headroom")
    invalid(r)
    assert "[INFO] G1c: H = -2.0000 不可用：oracle 自检没过" in r.out and "理想地解决它反而更差" not in r.out, r.out


def test_oracle_sanity_gain_below_the_threshold_fails(proj):
    set_sanity(proj, oracle_mean=51.0)                                           # G_s = 1.0 < max(min_effect 1, 3 x 0.5) = 1.5
    invalid(M(proj, "headroom"))


@pytest.mark.parametrize("field,needle", [("why", "oracle 自检的 why 为空"), ("setting", "oracle 自检的 setting 为空")])
def test_oracle_sanity_needs_setting_and_why(proj, field, needle):
    mut(proj, lambda st: st["method"]["headroom"]["oracle"]["sanity"].__setitem__(field, ""))
    r = M(proj, "headroom")
    assert needle in r.out, r.out
    invalid(r)


def test_oracle_sanity_one_seed_on_a_side_fails(proj):
    set_sanity(proj, oracle_mean=55.0, n_o=1)
    r = M(proj, "headroom")
    assert "[FAIL] G1c: oracle 自检每边至少 2 个 seed（现在基线 3 个、oracle 1 个" in r.out, r.out
    invalid(r)
    set_sanity(proj, oracle_mean=55.0, n_o=3, base_mean=50.0, n_b=1)
    assert "基线 1 个、oracle 3 个" in M(proj, "headroom").out


def test_oracle_sanity_two_seeds_is_a_warning(proj):
    set_sanity(proj, oracle_mean=55.0, n_o=2)
    r = M(proj, "headroom")
    ok(r, "[PASS] G1c: GO (")
    assert "[WARN] G1c: oracle 自检只有 2 个 seed 的一边（基线 3 个、oracle 2 个）：补到 ≥3 个" in r.out and "oracle sanity = pass" in r.out, r.out


def test_oracle_sanity_with_both_globs_empty_is_missing(proj):
    def f(st):
        st["method"]["headroom"]["oracle"]["sanity"].update(baseline_glob="", oracle_glob="")
    mut(proj, f)
    ok(M(proj, "headroom"), "oracle sanity = missing")


def test_oracle_sanity_with_one_glob_empty_fails(proj):
    mut(proj, lambda st: st["method"]["headroom"]["oracle"]["sanity"].__setitem__("oracle_glob", ""))
    r = M(proj, "headroom")
    assert "oracle 自检每边至少 2 个 seed" in r.out, r.out
    invalid(r)


def test_oracle_sanity_has_its_own_metric_key(proj):
    for d in (proj / "runs").glob("san_*"):
        write(d / "eval.json", json.dumps({"metrics": {"ap": 0.0}, "other": {"score": 55.0 if "orc" in d.name else 50.0}}))
    mut(proj, lambda st: st["method"]["headroom"]["oracle"]["sanity"].__setitem__("key", "other.score"))
    ok(M(proj, "headroom"), "oracle sanity = pass")


def test_oracle_applied_other_value_fails_and_empty_warns(proj):
    mut(proj, lambda st: st["method"]["headroom"]["oracle"].__setitem__("applied", "both"))
    bad(M(proj, "headroom"), "headroom.oracle.applied = 'both'：只能是 train+test | test_only")
    mut(proj, lambda st: st["method"]["headroom"]["oracle"].__setitem__("applied", ""))
    r = M(proj, "headroom")
    ok(r, "[PASS] G1c: GO (")
    assert "[WARN] G1c: headroom.oracle.applied 为空：写 train+test" in r.out and "test_only" in r.out, r.out


def test_oracle_sanity_runs_are_neither_dev_baselines_nor_confirm_runs(proj):
    mkgroup(proj, "san_base2_s", 10.0, split="sanity", role="baseline", method="BaseNet")     # not matched by baseline_glob, must not leak into the dev baseline
    r = M(proj, "headroom")
    ok(r, "H = 8.0000")
    assert "基线复现 50.0000" in r.out and "冻结前没有任何 confirm 评测" in r.out, r.out
    d = M(proj, "dev-check")
    ok(d, "所有 dev 的 ours/ablation run 都属于某个迭代行（4 轮），没有未标注的 run")
    assert "未登记" not in d.out and "没有 eval_split/role" not in d.out


def test_oracle_sanity_run_with_a_role_is_not_untagged_but_one_without_is(proj):
    d = proj / "runs" / "san_half"
    d.mkdir()
    write(d / "args.json", json.dumps({"eval_split": "sanity", "seed": 0}))
    write(d / "eval.json", json.dumps({"metrics": {"ap": 1.0}}))
    bad(M(proj, "dev-check"), "run 没有 eval_split/role")


def test_oracle_sanity_in_the_frozen_project_changes_nothing(fro):
    ok(M(fro, "dev-check"))
    add_confirm(fro)
    mut(fro, lambda st: st["method"].__setitem__("outcome", "confirmed"))
    ok(M(fro, "confirm-check"), "验证集看了 1 次，登记 1 次")


def test_oracle_lower_is_better_sanity_and_go(proj):
    mut(proj, lambda st: st["results"].__setitem__("primary_direction", "lower"))
    set_sanity(proj, oracle_mean=45.0)
    set_oracle(proj, 42.0)
    r = M(proj, "headroom")
    ok(r, "[PASS] G1c: GO (")
    assert "G_s = 5.0000" in r.out and "oracle sanity = pass" in r.out, r.out
    set_sanity(proj, oracle_mean=55.0)                                           # higher = worse now: the oracle loses on the known-answer case
    invalid(M(proj, "headroom"))


def test_oracle_invalid_shows_on_status(proj):
    no_sanity(proj)
    set_oracle(proj, 48.0)
    r = M(proj, "status")
    assert r.returncode == 0 and "G1c        INVALID (" in r.out, r.out


def test_oracle_invalid_comes_with_the_other_failures_but_is_the_verdict(proj):
    no_sanity(proj)
    set_oracle(proj, 48.0)
    mut(proj, lambda st: st["method"]["baseline"].__setitem__("code", ""))
    r = M(proj, "headroom")
    assert "method.baseline.code 为空" in r.out
    invalid(r)


def test_t2p_board_pattern_matches_all_three_verdicts():
    import re
    src = read(SCRIPTS / "t2p.py")
    m = re.search(r'm = re\.search\(r"(G1c: [^"]+)", out\)', src)
    assert m, "the verdict regex in t2p.py moved"
    pat = re.compile(m.group(1))
    for line, word in (("[PASS] G1c: GO (headroom H = 8.0000, oracle sanity = pass)", "GO"),
                       ("[FAIL] G1c: NO-GO (headroom H = 0.8000; 1 项未过)", "NO-GO"),
                       ("[FAIL] G1c: INVALID (headroom H = nan; oracle 未通过自检)", "INVALID")):
        mm = pat.search(line)
        assert mm and mm.group(0)[5:].startswith(word), line
