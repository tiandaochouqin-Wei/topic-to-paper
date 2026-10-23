# findings — 反常记录（P4；results_check 的反常触发器要求先有这里的条目再动配置）

每条一个块，字段固定。`cause` 按 [references/anomaly-triage.md](../.claude/skills/topic-to-paper/references/anomaly-triage.md) 的顺序排查，排到哪一步写哪一步；排完四步都不是，才写 `real`。

```
## F1 <日期> <方法> <指标>
what: <一句话：观测到什么，与预期/报告值差多少>
metric: <指标列名>   method: <方法名>   runs: <run_id 列表>
checked:
  convention: excluded | hit   # 口径/分母/窗口是否与报告一致（一句话说明）
  data: excluded | hit         # 划分/预处理/版本是否一致
  leak: excluded | hit         # 泄漏开关、统计量来源；audit_check 结果
  impl: excluded | hit         # 关键超参是否生效、ckpt 是否训完；证据列
cause: convention | data | leak | impl | real | open
evidence: <文件路径，空格或逗号分隔：命令输出/日志/脚本结果，至少一个真实存在的文件>
control: <cause: real 时必填：阳性或阴性对照——同一管线下已知答案的输入得到已知结果（见 G3b），或故意破坏输入得到预期的坏结果>
action: <命中前四项之一 → 修并重跑哪些 run；real → 进 claims.csv 作为发现，写进 prereg 的 convention_changes 或新主张；open → 补什么实验>
```

**格式（results_check 机械检查）**：块的标题行以 `## F1` / `### F1` 开头。块里只要写了结案结论——`cause: convention|data|leak|impl|real`，或某一步写 `excluded`/`排除`——就必须有 `evidence:` 行，指向项目里至少一个存在的文件（排查时跑的命令的输出、日志、统计脚本的结果），否则 FAIL：自由文本"impl: 排除"不算排查（那是自己给自己结案）。`cause: real` 还要有 `control:` 行，否则 WARN。`open` 不结案，不需要证据。上面围栏里的示例不会被当作 finding。
