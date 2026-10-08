# 反常分诊（P4）

触发：`results_check.py` 报 predictions 反号或 reproductions 超差；或任一 run 的指标与同配置历史 run 差 > 2σ。
原则：先记录（findings.md 一条，含方法名与指标名），再按下面顺序排查，**排查完才许改配置**。每步有判据和证据文件；一步命中就停，写 cause 与 action。

| 步 | 问题 | 判据（机械能查的） | 证据 | 命中后 |
|---|---|---|---|---|
| 1 convention | 口径是不是同一个？ | 分母、纳入窗口、阈值、单位与报告值的口径逐项比对（prereg §3/§4 vs 论文原文的 metric 定义） | results/main.md 口径注释；对方论文的 metric 段原句 | 不是反常，是口径差；在 main.md 写明两种口径的数值，不改模型 |
| 2 data | 数据是不是同一份？ | 划分文件 hash、样本数、预处理版本、数据版本号与报告一致；`audit_check` split 核对 | split_files、datasets.csv 的 n、frames/ 等输入存在性 | 修数据后重跑该 run；不改模型 |
| 3 leak | 有没有标签泄漏或目标域统计量？ | leak_flags 全 0；标准化统计量只来自源域训练集；`audit_check` 泄漏项全绿 | audit 输出、compute_stats 调用处 | 该 run 作废，主表撤行，重跑 |
| 4 impl | 配置真的生效了吗？训完了吗？ | critical_params 的日志证据列非零；log 条数 ≥ epochs；硬件一致；seed 固定 | `audit_check` 有效配置/完成度项 | 修代码或补训，重跑 |
| 5 real | 上面都排除 | 复现在 ≥2 seeds 上稳定（符号一致）；换一个无关实现细节（bs/lr 微调）仍在 | 新增的 2 个 run | **这是发现**：进 claims.csv 一行，prereg.convention_changes 记"新主张来源 finding F#"，写进正文（Results 或 Discussion），不是删掉 |

写不进第 5 步的（单 seed、没复现）填 `open`，action 写要补的 run；open 状态的 finding 不得进正文主张。

三个来自真实项目的例子：
- 力估计：全量口径 vs 接触窗口口径让三类结论反转 → 步 1 命中（口径）。
- 力估计：基线 args 写 beta=0.1 但从未生效 → 步 4 命中（impl）。
- 基因：ESM-2 邻居只比随机好 0.012 → 步 1–4 全排除，两种假象也排除 → real，成了论文的核心否定结果。
