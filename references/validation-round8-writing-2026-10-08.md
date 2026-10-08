# 验证轮 8：补齐写作生成、图生成、审稿闭环、反常分诊（2026-10-08）

起因：用户问"距离给主题直接出高水平论文还差什么"，列出的流程缺口里本轮补四项；"P4 在真项目走完"和 Slurm 要等数据与服务器。

## 加了什么

| 缺口 | 实现 | 关口 |
|---|---|---|
| 写作生成薄 | `draft_plan.py plan` 从 gap_map / prereg / claims.csv / results 生成各节必写清单（引言 9 类、方法 3 类、结果 7 类、局限 2 类），`check` 逐项在对应章节核对（name 词边界 / numbers 精确 / number_pm1 允许 ±1 / regex 措辞 / tokens 重合 ≥60%），自动勾选 draft_plan.md | G6b（t2p.py check 新行） |
| 数据图手画 | `make_figure.py main|ablation|seeds` 从 state.results 的表直接出图：main 分组柱 + 多 seed mean±s.d. 与逐 seed 点、ours 红；ablation Δ vs 参照 + ±2σ√2 灰带、带内格灰色、索引行在轴下；seeds 指定方法的 mean±s.d.。每张出 png/pdf/source.csv，登记 figures.csv（inspected=no，目测后改 yes，否则 G5 FAIL） | G5 |
| 第二轮审稿没规定 | `review_check.py`：每条 [major]/[minor] 有处置（同行、后两行、或 Phase 2 综合表按 R1-3 编号）；major 必须在 `## Re-review` 节关闭；state.review.round ≥1；gate_report 新于正文；处置提到的 §/Table 在正文存在 | G7（替换原来只 grep "major" 的判法） |
| 反常后做什么没规定 | `references/anomaly-triage.md` 五步分诊：口径→数据→泄漏→实现→真发现，每步机械判据与证据文件；`templates/findings.md` 块格式（checked/cause/action），open 状态不得进正文 | results_check 触发器引用 |

## 验证
- **draft_plan**（EAAI 稿，17 348 词）：20 项 17 过，3 项是单字母基线名 S/V/VS 降 WARN 要人工确认。植入：把消融节的 "resolution limit / seed-to-seed / noise / within" 全改掉 → RES18 FAIL，其余不变。RS_nowcast 无正文：plan 出 38 项（引言 9：重要性、6 篇关键论文失效点、邻域默认假设、§1 主张；方法 6：5 项消融组件 + DOFA 失效点；结果 20；局限 3），可直接当写作提纲。
- **make_figure**（EAAI）：三张图 342–374 dpi@印刷宽；主图 ours 与 RCNN 四 seed 的误差棒和散点正确；消融图 30 格全灰（与 resolve 的 0/30 一致）。两轮目测修了索引数字压在柱上、y 轴显示列名两处。
- **review_check**（EAAI 真实 review_log，7 条）：第一版把 R2-2/R2-3/R3-2 三条报成无处置——它们的处置写在 Phase 2 编辑综合表里按编号列出，不在同行；加"编号出现在综合表 = 已处置"后 ALL PASS。植入一条无处置 major → 2 FAIL；追加 Re-review 节按编号关闭 → ALL PASS。
- **状态板**：EAAI G6b PASS、G7 PASS；G5 三张新图未目测 FAIL（目测后改 yes 通过）；G6 numbers 的 86 个未登记数字是 Table 5–7 现场算的旧问题，不属本轮。

## 坑
- 表格 header 行被当成消融组件（"去掉/替换"）：改为按下一行是否分隔线判定 header。
- 正文里 `>` 开头的编辑日志行含 run 名，让 no_drop 等"出现在结果节"误过：核对前剔除。
- review_check 用前 14 字做 major 的 key 时含序号 "1. "，Re-review 里写法不同就匹配不上：改为优先按 R4-1 编号，退化为去掉序号和标签的前 12 字。
- figures.csv 的列名是 source_data 不是 source，make_figure 第一次写入抛 DictWriter 错：按模板表头写。

## 仍不机械的
清单只能查"提没提"和"提在哪一节"，提得对不对由 G6 numbers/scope 查，提得好不好没有关口。
