# -*- coding: utf-8 -*-
"""G3b instrument calibration (instrument_check.py) and the experiment-substance checks that go with it:
audit_check stochastic_keys / narrowed audit set, results_check empty reproductions / self-certified triage.

Evidence: cvpr2027_medical fed four pretrained encoders an SPL array where the official layout is RAS (found after 7 days and 10 review
rounds); its first 'orientation test' scored 0.562 vs 0.581 and could not fail. cvpr2027_fusion: persistent workers never saw ds.epoch,
augmentation identical every epoch. med2: 146 FAIL turned PASS by narrowing main_table_runs. `reproductions: []` in every real project."""
import json
import re

import yaml

from conftest import SKILL, edit, read, run, touch, write

INS = "results/instruments/backbone.json"
BRK = "results/instruments/backbone_broken.json"


def _state(p):
    return yaml.safe_load(read(p / "research-state.yaml"))


def _mut(p, fn):
    """load research-state.yaml, apply fn(dict), dump it back (comments are not needed by these tests)"""
    st = _state(p); fn(st)
    write(p / "research-state.yaml", yaml.safe_dump(st, allow_unicode=True, sort_keys=False, width=10**6))


def _ins(p, **kw):
    def f(st):
        st["instruments"][0].update(kw)
    _mut(p, f)


def _jset(path, fn):
    d = json.loads(read(path)); fn(d); write(path, json.dumps(d))


def _g3b(p):
    return run("instrument_check.py", cwd=p)


def _fail(r, needle):
    assert r.fails >= 1 and needle in r.out, r.out


# ------------------------------------------------------------------ pass / scan
def test_g3b_pass(research):
    r = _g3b(research)
    assert r.fails == 0 and "ALL PASS" in r.out, r.out
    assert "[PASS] instrument: backbone: 破坏对照" in r.out


def test_g3b_uncovered_loader(research):
    write(research / "code" / "extra.py", "from transformers import AutoModel\nm = AutoModel.from_pretrained('x/y')\n")
    r = _g3b(research)
    _fail(r, "未校准的仪器 code/extra.py:2")


def test_g3b_loader_with_no_instruments_at_all(research):
    _mut(research, lambda st: st.pop("instruments"))
    _fail(_g3b(research), "未校准的仪器 code/backbone.py:6")


def test_g3b_waiver_is_a_warning_with_the_reason(research):
    write(research / "code" / "extra.py", "def f(net, args):\n    net.load_state_dict(torch.load(args.resume))\n")
    _mut(research, lambda st: st.__setitem__("instruments_waiver", [{"match": "resume|runs/", "reason": "own checkpoint"}]))
    r = _g3b(research)
    assert r.fails == 0 and re.search(r"\[WARN\] instrument: 1 处加载按 instruments_waiver 豁免（own checkpoint）", r.out), r.out


def test_g3b_no_pretrained_components_passes(research):
    _mut(research, lambda st: st.pop("instruments"))
    (research / "code" / "backbone.py").unlink()
    r = _g3b(research)
    assert r.fails == 0 and "无预训练组件/外部框架" in r.out, r.out


def test_g3b_commented_loader_is_not_a_hit(research):
    _mut(research, lambda st: st.pop("instruments"))
    write(research / "code" / "backbone.py", "# net.load_state_dict(state)   # disabled\n")
    r = _g3b(research)
    assert r.fails == 0 and "无预训练组件" in r.out, r.out


def test_g3b_tests_and_underscore_files_are_not_scanned(research):
    _mut(research, lambda st: st.pop("instruments"))
    (research / "code" / "backbone.py").unlink()
    write(research / "code" / "tests" / "t.py", "m = AutoModel.from_pretrained('x')\n")
    write(research / "code" / "_scratch.py", "m = AutoModel.from_pretrained('x')\n")
    r = _g3b(research)
    assert r.fails == 0 and "无预训练组件" in r.out, r.out


def test_g3b_scans_experiment_code_outside_code_dirs(research):
    # cvpr2028_gcv: code_dirs = [code] while the experiments lived in ma_p3/ and killtest_*/ -> the scan saw nothing and passed
    write(research / "killtest_A" / "models.py", "m = VGGT.from_pretrained('facebook/VGGT-1B')\n")
    _fail(_g3b(research), "未校准的仪器 killtest_A/models.py:1")


def test_g3b_artefact_dirs_are_not_scanned(research):
    write(research / "literature" / "mined" / "repo" / "x.py", "m = AutoModel.from_pretrained('x')\n")
    assert _g3b(research).fails == 0


def test_g3b_class_name_ending_in_yolo_is_not_a_loader(research):
    write(research / "code" / "fusion.py", "class DualYOLO(nn.Module):\n    pass\n")
    assert _g3b(research).fails == 0
    write(research / "code" / "ref.py", "YOLO('weights/yolo11n.pt').train(data='d.yaml')\n")
    _fail(_g3b(research), "未校准的仪器 code/ref.py:1")


def test_g3b_optimizer_and_ema_restores_are_not_instruments(research):
    write(research / "code" / "resume.py", "opt.load_state_dict(ck['opt']); scaler.load_state_dict(ck['scaler'])\n"
          "ema.ema.load_state_dict(ck['ema']); scheduler.load_state_dict(ck['sched'])\n")
    assert _g3b(research).fails == 0


def test_g3b_one_fail_per_file(research):
    write(research / "code" / "enc.py", "".join(f"m{i}.load_state_dict(sd{i})\n" for i in range(12)))
    r = _g3b(research)
    assert r.fails == 1 and "code/enc.py:1,2,3,4,5,6,7,8 …" in r.out, r.out


# ------------------------------------------------------------------ per-instrument checks
def test_g3b_calibration_not_run(research):
    (research / INS).unlink()
    _fail(_g3b(research), "backbone: 未跑校准（cmd: python code/calib_backbone.py")


def test_g3b_stale_calibration(research):
    touch(research / "code" / "backbone.py", +30)           # code changed after the calibration output
    _fail(_g3b(research), "代码改过、校准未重跑")


def test_g3b_value_outside_tolerance(research):
    _jset(research / INS, lambda d: d["dice"].__setitem__("liver", 0.60))
    r = _g3b(research)
    _fail(r, "仪器读数 0.6 vs 已知 0.95±0.05")
    assert "修好前任何用到它的结果都不能进表" in r.out


def test_g3b_no_known_answer(research):
    _ins(research, check={**_state(research)["instruments"][0]["check"], "expected": None, "tol": None})
    _fail(_g3b(research), "无已知答案")


def test_g3b_min_max_band_is_accepted(research):
    chk = {k: v for k, v in _state(research)["instruments"][0]["check"].items() if k not in ("expected", "tol")}
    _ins(research, check={**chk, "min": 0.9})
    r = _g3b(research)
    assert r.fails == 0, r.out


def test_g3b_missing_broken_control(research):
    _mut(research, lambda st: st["instruments"][0].pop("broken"))
    _fail(_g3b(research), "没有破坏对照：一个不会失败的校验等于没校验")


def test_g3b_broken_output_not_run(research):
    (research / BRK).unlink()
    _fail(_g3b(research), "破坏版没跑")


def test_g3b_vacuous_broken_control(research):
    """the 0.562-vs-0.581 orientation test: the 'broken' input scores like the right one, so the test cannot fail"""
    _jset(research / BRK, lambda d: d["dice"].__setitem__("liver", 0.93))
    _fail(_g3b(research), "校验区分不了正确与破坏的输入（axes reversed (LPS): 0.93 vs 0.94）")


# ------------------------------------------------------------------ contract and first-batch dump
def test_g3b_contract_mismatch_in_calibration_json(research):
    _jset(research / INS, lambda d: d["applied_contract"].__setitem__("axcodes", "LPS"))
    r = _g3b(research)
    _fail(r, "校准脚本实际用的输入约定与登记不符")
    assert "axcodes" in r.out


def test_g3b_contract_list_compared_elementwise(research):
    _jset(research / INS, lambda d: d["applied_contract"].__setitem__("spacing", [1.0, 1.0, 1.0]))
    _fail(_g3b(research), "spacing")


def test_g3b_contract_case_insensitive_strings(research):
    _jset(research / INS, lambda d: d["applied_contract"].__setitem__("axcodes", " ras "))
    assert _g3b(research).fails == 0


def test_g3b_no_applied_contract_is_a_warning(research):
    _jset(research / INS, lambda d: d.pop("applied_contract"))
    r = _g3b(research)
    assert r.fails == 0 and "校准脚本没写 applied_contract" in r.out, r.out


def test_g3b_contract_without_source_is_a_warning(research):
    def f(st):
        st["instruments"][0]["contract"].pop("source")
    _mut(research, f)
    r = _g3b(research)
    assert r.fails == 0 and "contract 没有 source" in r.out, r.out


def test_g3b_contract_mismatch_in_run_args(research):
    _jset(research / "runs" / "ours_s0" / "args.json", lambda d: d["contracts"]["backbone"].__setitem__("axcodes", "SPL"))
    _fail(_g3b(research), "run ours_s0 实际用的约定与登记不符")


def test_g3b_no_run_logs_contracts_is_a_warning(research):
    _jset(research / "runs" / "ours_s0" / "args.json", lambda d: d.pop("contracts"))
    r = _g3b(research)
    assert r.fails == 0 and "没有任何 run 的 args.json 记录 contracts" in r.out, r.out


def test_g3b_missing_dump(research):
    (research / "figures" / "instruments" / "backbone_first_batch.png").unlink()
    _fail(_g3b(research), "缺首批输入图 dump")


def test_g3b_uninspected_dump(research):
    _ins(research, inspected=False)
    _fail(_g3b(research), "首批输入图未目测")


def test_g3b_dump_not_required_without_axcodes_or_channels(research):
    def f(st):
        st["instruments"][0]["contract"] = {"intensity": "z-score", "source": "x"}
        st["instruments"][0].pop("dump")
    _mut(research, f)
    _jset(research / INS, lambda d: d.pop("applied_contract"))
    _jset(research / "runs" / "ours_s0" / "args.json", lambda d: d.pop("contracts"))
    r = _g3b(research)
    assert r.fails == 0 and "缺首批输入图" not in r.out, r.out


# ------------------------------------------------------------------ train_loop
def _loop(p, **ref):
    base = {"output": "results/instruments/ref_trainer.json", "key": "ap", "expected": 32.3, "tol": 1.0, "source": "Ultralytics official trainer, same split"}
    write(p / base["output"], json.dumps({"ap": 32.0}))
    touch(p / base["output"], +5)
    ent = {"name": "loop", "kind": "train_loop", "match": "train\\.py", "reference": {**base, **ref}}
    _mut(p, lambda st: st["instruments"].append(ent))
    return ent


def test_g3b_train_loop_reference_passes(research):
    _loop(research)
    r = _g3b(research)
    assert r.fails == 0 and "loop: 参考实现 读数 32 在已知答案 32.3±1.0 内" in r.out, r.out
    assert "[WARN] instrument: loop: 没有破坏对照" in r.out


def test_g3b_train_loop_without_reference(research):
    _loop(research)
    _mut(research, lambda st: st["instruments"][1].pop("reference"))
    _fail(_g3b(research), "loop: train_loop 需要 reference")


def test_g3b_train_loop_reference_off(research):
    """fusion: own loop 29.5 AP vs the Ultralytics reference 32.3"""
    _loop(research)
    write(research / "results/instruments/ref_trainer.json", json.dumps({"ap": 29.5}))
    touch(research / "results/instruments/ref_trainer.json", +5)
    _fail(_g3b(research), "仪器读数 29.5 vs 已知 32.3±1.0")


def test_g3b_train_loop_reference_output_missing(research):
    _loop(research)
    (research / "results/instruments/ref_trainer.json").unlink()
    _fail(_g3b(research), "loop: 未跑参考实现")


def test_g3b_invalid_kind_and_regex(research):
    _ins(research, kind="magic", match="(")
    r = _g3b(research)
    _fail(r, "kind 必须是")
    assert "不是合法正则" in r.out


# ------------------------------------------------------------------ t2p wiring
def test_g3b_on_the_board(research):
    run("draft_plan.py", "plan", "--project", ".", cwd=research)
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=research)
    assert "[PASS] G3b:" in r.out, r.out
    (research / INS).unlink()
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=research)
    assert "[FAIL] G3b:" in r.out and r.returncode >= 1, r.out


def test_g3b_pending_without_code(research):
    import shutil
    shutil.rmtree(research / "code")
    r = run("t2p.py", "check", "--project", ".", "--no-write", cwd=research)
    assert "[PENDING] G3b:" in r.out, r.out


def test_g3b_na_for_have_draft_and_hidden_for_survey(tmp_path, survey):
    proj = tmp_path / "draft"
    run("t2p.py", "init", "--project", str(proj), "--venue", "TPAMI", "--entry", "have_draft", cwd=tmp_path)
    c = run("t2p.py", "check", "--project", ".", "--no-write", cwd=proj)
    assert "[N/A] G3b:" in c.out, c.out
    assert "G3b" in _state(proj)["gates"]                                   # init writes it
    c = run("t2p.py", "check", "--project", ".", "--no-write", cwd=survey)
    assert "] G3b:" not in c.out, c.out


def test_g3b_check_writes_gate_back_for_old_projects(research):
    assert "G3b" not in _state(research)["gates"]                           # the fixture predates G3b
    run("draft_plan.py", "plan", "--project", ".", cwd=research)
    run("t2p.py", "check", "--project", ".", cwd=research)
    assert _state(research)["gates"]["G3b"]["status"] == "pass"


def test_g3b_documented(research):
    g = read(SKILL / "references" / "gates.md")
    assert re.search(r"(?m)^## G3b\b", g)
    assert "G3b" in read(SKILL / "references" / "phases" / "P3.md") and "G3b" in read(SKILL / "SKILL.md")
    assert "SPL" in read(SKILL / "references" / "lessons.md")
    tpl = yaml.safe_load(read(SKILL / "templates" / "research-state.yaml"))
    assert "G3b" in tpl["gates"] and "stochastic_keys" in tpl["audits"] and "instruments_waiver" in tpl


# ------------------------------------------------------------------ A2 stochastic_keys (audit_check)
def _log_key(p, key, fn):
    """add `key` to every epoch entry of every run; fn(epoch) -> value, or None to leave the key out"""
    for lg in p.glob("runs/*/log.json"):
        d = json.loads(read(lg))
        for e in d:
            if fn is not None: e[key] = fn(e["epoch"])
        write(lg, json.dumps(d))
        touch(lg, -10)


def _keys(p, keys):
    _mut(p, lambda st: st["audits"].__setitem__("stochastic_keys", keys))


def test_stochastic_varying_key_passes(research):
    _log_key(research, "aug_seed", lambda ep: 1000 + ep)
    _keys(research, ["aug_seed"])
    r = run("audit_check.py", cwd=research)
    assert r.fails == 0 and "核对了 11 个 run × ['aug_seed']" in r.out, r.out


def test_stochastic_constant_key_fails(research):
    _log_key(research, "aug_seed", lambda ep: 1000)
    _keys(research, ["aug_seed"])
    r = run("audit_check.py", cwd=research)
    _fail(r, "ours_s0: aug_seed 全程同一值 —— 随机增强/采样每 epoch 相同")


def test_stochastic_key_absent_from_log_fails(research):
    _keys(research, ["aug_hash"])
    _fail(run("audit_check.py", cwd=research), "ours_s0: 日志无证据列 aug_hash")


def test_stochastic_warns_on_persistent_workers_without_keys(research):
    write(research / "code" / "loader.py", "from torch.utils.data import DataLoader\ndl = DataLoader(ds, num_workers=4, persistent_workers=True)\n")
    r = run("audit_check.py", cwd=research)
    assert r.fails == 0 and "code/loader.py:2 有多进程数据增强但没登记 audits.stochastic_keys" in r.out, r.out
    write(research / "code" / "loader.py", "dl = DataLoader(ds, worker_init_fn=seed_worker)\n")
    assert "有多进程数据增强但没登记" in run("audit_check.py", cwd=research).out


# ------------------------------------------------------------------ A3 narrowing the audited set
def _narrow(p):
    runs = sorted(x.name for x in (p / "runs").iterdir() if x.is_dir() and x.name != "abl_no_cons")
    _mut(p, lambda st: st["audits"].__setitem__("main_table_runs", runs))


def test_narrowed_audit_set_warns(research):
    _narrow(research)
    r = run("audit_check.py", cwd=research)
    assert r.fails == 0 and re.search(r"\[WARN\] runs: main_table_runs 把 1 个 run 排在审计之外 \['abl_no_cons'\]", r.out), r.out


def test_narrowed_audit_set_logged_in_convention_changes_passes(research):
    _narrow(research)
    _mut(research, lambda st: st["experiments"].__setitem__("convention_changes", [{"date": "2026-10-22", "what": "main_table_runs excludes ablation runs", "why": "ablations are not in the main table"}]))
    r = run("audit_check.py", cwd=research)
    assert r.fails == 0 and "[PASS] runs: main_table_runs 排除了 1 个 run，experiments.convention_changes 已登记" in r.out, r.out
    assert "排在审计之外" not in r.out


def test_full_audit_set_has_no_narrowing_message(research):
    r = run("audit_check.py", cwd=research)
    assert "排在审计之外" not in r.out and "排除了" not in r.out


# ------------------------------------------------------------------ A4 results_check
def test_empty_reproductions_warns(research):
    r = run("results_check.py", cwd=research)
    assert r.fails == 0 and "[WARN] reproductions: reproductions 为空：至少把一个基线复现到其论文数字" in r.out, r.out


def test_filled_reproductions_do_not_warn(research):
    _mut(research, lambda st: st["results"].__setitem__("reproductions", [{"method": "baseA", "metric": "rmse_E1", "reported": 0.30, "tol": 0.2}]))
    r = run("results_check.py", cwd=research)
    assert "reproductions 为空" not in r.out and r.fails == 0, r.out


def _finding(p, body, name="F1"):
    write(p / "findings.md", f"# findings\n\n## {name} 2026-10-22 ours rmse_E1\nwhat: ours is worse than baseA on rmse_E1\n{body}\n")


def test_finding_verdict_without_evidence_fails(research):
    _finding(research, "checked:\n  impl: excluded\ncause: impl\n")
    r = run("results_check.py", cwd=research)
    _fail(r, "F1: 分诊结论没有证据文件（命令输出）——自由文本不算排查")


def test_finding_verdict_with_chinese_exclusion_needs_evidence(research):
    _finding(research, "impl: 排除\n")
    _fail(run("results_check.py", cwd=research), "F1: 分诊结论没有证据文件")


def test_finding_evidence_pointing_nowhere_fails(research):
    _finding(research, "cause: data\nevidence: results/triage/nope.txt\n")
    _fail(run("results_check.py", cwd=research), "F1: 分诊结论没有证据文件")


def test_finding_with_existing_evidence_passes(research):
    write(research / "results" / "triage_f1.txt", "log rows 3/3 ; beta column nonzero\n")
    _finding(research, "impl: excluded\nevidence: results/triage_f1.txt, runs/ours_s0/log.json\ncause: impl\n")
    r = run("results_check.py", cwd=research)
    assert r.fails == 0 and "1 条已结案的 finding 都带存在的证据文件" in r.out, r.out


def test_finding_cause_real_without_control_warns(research):
    write(research / "results" / "triage_f1.txt", "ok\n")
    _finding(research, "cause: real\nevidence: results/triage_f1.txt\n")
    r = run("results_check.py", cwd=research)
    assert r.fails == 0 and "F1: cause: real 没有 control: 行" in r.out, r.out
    _finding(research, "cause: real\nevidence: results/triage_f1.txt\ncontrol: known-answer input reproduces 0.95 (results/triage_f1.txt)\n")
    assert "没有 control" not in run("results_check.py", cwd=research).out


def test_open_finding_needs_no_evidence(research):
    _finding(research, "cause: open\naction: run two more seeds\n")
    r = run("results_check.py", cwd=research)
    assert r.fails == 0 and "== findings ==" not in r.out, r.out


def test_findings_template_format_block_is_not_a_finding(research):
    write(research / "findings.md", read(SKILL / "templates" / "findings.md"))
    r = run("results_check.py", cwd=research)
    assert r.fails == 0 and "分诊结论没有证据文件" not in r.out, r.out
    assert "evidence:" in read(SKILL / "templates" / "findings.md") and "control:" in read(SKILL / "templates" / "findings.md")
    assert "evidence:" in read(SKILL / "references" / "anomaly-triage.md")
