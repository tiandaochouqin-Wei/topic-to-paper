# -*- coding: utf-8 -*-
"""G4 protocol-mixing audit: results_check.py refuses a main table whose compared rows were produced under different input size / split /
checkpoint rule / class map / evaluator, as far as the runs logged those keys."""
import json

from conftest import edit, read, run, write

METHODS = {"ours": ("ours_s0", "ours_s1", "ours_s2"), "baseA": ("baseA_s0", "baseA_s1", "baseA_s2"), "baseB": ("baseB_s0", "baseB_s1", "baseB_s2")}
ALL = [r for rs in METHODS.values() for r in rs]
KEYS = ["input_size", "split", "checkpoint_rule", "class_map", "evaluator"]


def _set(research, runs, key, val, fname="args.json"):
    for rid in runs:
        p = research / "runs" / rid / fname
        o = json.loads(read(p)) if p.exists() else {}; o[key] = val; write(p, json.dumps(o))


def _log_all(research, **kw):
    for k, v in kw.items(): _set(research, ALL, k, v)


def _out(research):
    r = run("results_check.py", cwd=research)
    assert not r.crashed, r.out
    return r


def test_unlogged_keys_give_info_and_do_not_fail(research):
    r = _out(research)
    assert r.fails == 0 and all(f"[INFO] protocol: {k} 未登记" in r.out for k in KEYS), r.out


def test_consistent_protocol_passes(research):
    _log_all(research, input_size=640, split="official-val", checkpoint_rule="last", class_map="coco80", evaluator="pycocotools")
    r = _out(research)
    assert r.fails == 0 and "[PASS] protocol: 5 项口径" in r.out and "[INFO] protocol" not in r.out, r.out


def test_mixed_input_size_fails_and_names_the_runs(research):
    _log_all(research, input_size=640)
    _set(research, METHODS["baseB"], "input_size", 1280)
    r = _out(research)
    assert r.fails == 1, r.out
    assert "[FAIL] protocol: 混用了不同口径：input_size" in r.out and "640" in r.out and "1280" in r.out and "baseB_s0" in r.out and "ours_s0" in r.out, r.out
    assert "另立表或在 results.protocol_waiver 里写明理由" in r.out


def test_mixed_split_fails(research):
    _log_all(research, split="val-A")
    _set(research, METHODS["baseA"], "split", "val-B")
    r = _out(research)
    assert r.fails == 1 and "混用了不同口径：split" in r.out, r.out


def test_one_failure_per_mixed_key(research):
    _log_all(research, input_size=640, evaluator="e1")
    _set(research, ["ours_s0"], "input_size", 800); _set(research, ["baseA_s1"], "evaluator", "e2")
    r = _out(research)
    assert r.fails == 2 and "混用了不同口径：input_size" in r.out and "混用了不同口径：evaluator" in r.out, r.out


def test_seed_level_mix_inside_one_method_also_fails(research):
    _log_all(research, checkpoint_rule="last")
    _set(research, ["ours_s2"], "checkpoint_rule", "best-on-test")
    r = _out(research)
    assert r.fails == 1 and "checkpoint_rule" in r.out and "best-on-test" in r.out, r.out


def test_waiver_turns_the_fail_into_a_warning_with_the_reason(research):
    _log_all(research, input_size=640)
    _set(research, METHODS["baseB"], "input_size", 1280)
    edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n  protocol_waiver: {input_size: \"baseB 官方权重只发 1280\"}\n")
    r = _out(research)
    assert r.fails == 0 and "[WARN] protocol: input_size 混用" in r.out and "baseB 官方权重只发 1280" in r.out and "正文须说明" in r.out, r.out


def test_waiver_is_per_key(research):
    _log_all(research, input_size=640, split="a")
    _set(research, ["baseB_s0"], "input_size", 1280); _set(research, ["baseB_s0"], "split", "b")
    edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n  protocol_waiver: {input_size: \"官方权重\"}\n")
    r = _out(research)
    assert r.fails == 1 and "混用了不同口径：split" in r.out and "[WARN] protocol: input_size" in r.out, r.out


def test_empty_waiver_reason_does_not_waive(research):
    _log_all(research, input_size=640); _set(research, ["baseB_s0"], "input_size", 1280)
    edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n  protocol_waiver: {input_size: \"\"}\n")
    r = _out(research)
    assert r.fails == 1 and "混用了不同口径：input_size" in r.out, r.out


def test_key_logged_by_only_some_runs_warns(research):
    _set(research, ["ours_s0", "ours_s1", "ours_s2"], "evaluator", "e1")
    r = _out(research)
    assert r.fails == 0 and "[WARN] protocol: evaluator 只有部分 run 登记了" in r.out and "baseA_s0" in r.out, r.out


def test_partially_logged_and_different_still_fails(research):
    _set(research, METHODS["ours"], "evaluator", "e1"); _set(research, ["baseA_s0"], "evaluator", "e2")
    r = _out(research)
    assert r.fails == 1 and "[WARN] protocol: evaluator 只有部分" in r.out and "混用了不同口径：evaluator" in r.out, r.out


def test_reads_eval_json_and_protocol_json_when_args_lack_the_key(research):
    _set(research, ALL, "split", "val", fname="eval.json")
    _set(research, ALL, "evaluator", "e1", fname="protocol.json")
    _set(research, ["baseA_s0"], "evaluator", "e2", fname="protocol.json")
    r = _out(research)
    assert r.fails == 1 and "混用了不同口径：evaluator" in r.out and "混用了不同口径：split" not in r.out, r.out
    assert "[INFO] protocol: split" not in r.out and "[PASS] protocol: 1 项口径" in r.out and "split" in r.out.split("[PASS] protocol")[1].splitlines()[0]


def test_args_json_wins_over_eval_json(research):
    _log_all(research, split="A")
    _set(research, ["baseB_s0"], "split", "B", fname="eval.json")          # shadowed by args.json
    assert _out(research).fails == 0


def test_custom_protocol_keys_replace_the_default_list(research):
    _log_all(research, input_size=640, tta="off"); _set(research, ["baseB_s0"], "tta", "on")
    edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n  protocol_keys: [tta, input_size]\n")
    r = _out(research)
    assert r.fails == 1 and "混用了不同口径：tta" in r.out and "split 未登记" not in r.out, r.out


def test_dataset_column_splits_the_comparison_sets(research):
    """different input sizes on different datasets are not a mix; the same dataset still is"""
    p = research / "results" / "main.csv"
    rows = read(p).splitlines()
    out = [rows[0].replace("run_id,", "run_id,dataset,", 1)] + [r.replace(",", ",D2,", 1) if r.startswith("baseB") else r.replace(",", ",D1,", 1) for r in rows[1:]]
    write(p, "\n".join(out) + "\n")
    edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n")
    _set(research, METHODS["ours"] + METHODS["baseA"], "input_size", 640); _set(research, METHODS["baseB"], "input_size", 1280)
    r = _out(research)
    assert "[FAIL] protocol" not in r.out and "[PASS] protocol" in r.out, r.out
    _set(research, ["ours_s1"], "input_size", 800)
    r = _out(research)
    assert r.fails == 1 and "（dataset=D1）" in r.out, r.out


def test_reproduced_baseline_is_not_exempt_without_a_waiver(research):
    _log_all(research, input_size=640); _set(research, METHODS["baseA"], "input_size", 1280)
    edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n  reproductions:\n    - {method: baseA, metric: rmse_E1, reported: 0.25, tol: 0.05}\n")
    r = _out(research)
    assert r.fails == 1 and "reproductions 里" in r.out and "protocol_waiver" in r.out, r.out
    edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n  protocol_waiver: {input_size: \"复现 baseA 按其论文 1280\"}\n")
    r = _out(research)
    assert r.fails == 0 and "复现 baseA 按其论文 1280" in r.out, r.out


def test_nested_values_compare_as_values(research):
    _log_all(research, input_size=[640, 640]); _set(research, ["baseB_s0"], "input_size", [1280, 1280])
    r = _out(research)
    assert r.fails == 1 and "[640, 640]" in r.out, r.out


def test_dotted_key_reads_nested_args(research):
    _set(research, ALL, "eval", {"nms": "iou0.6"}); _set(research, ["baseA_s1"], "eval", {"nms": "iou0.7"})
    edit(research / "research-state.yaml", "  findings: findings.md\n", "  findings: findings.md\n  protocol_keys: [eval.nms]\n")
    r = _out(research)
    assert r.fails == 1 and "eval.nms" in r.out and "iou0.7" in r.out, r.out
