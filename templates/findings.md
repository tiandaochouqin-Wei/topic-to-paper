# findings — 反常记录（P4；results_check 的反常触发器要求先有这里的条目再动配置）

每条一个块，字段固定。`cause` 按 [references/anomaly-triage.md](../.claude/skills/topic-to-paper/references/anomaly-triage.md) 的顺序排查，排到哪一步写哪一步；排完四步都不是，才写 `real`。

```
## F1 <日期> <方法> <指标>
what: <一句话：观测到什么，与预期/报告值差多少>
metric: <指标列名>   method: <方法名>   runs: <run_id 列表>
checked:
  - convention: <口径/分母/窗口是否与报告一致；证据文件>   -> 排除 | 命中
  - data: <划分/预处理/版本是否一致；证据>                 -> 排除 | 命中
  - leak: <泄漏开关、统计量来源；audit_check 结果>          -> 排除 | 命中
  - impl: <关键超参是否生效、ckpt 是否训完；证据列>          -> 排除 | 命中
cause: convention | data | leak | impl | real | open
action: <命中前四项之一 → 修并重跑哪些 run；real → 进 claims.csv 作为发现，写进 prereg 的 convention_changes 或新主张；open → 补什么实验>
```
