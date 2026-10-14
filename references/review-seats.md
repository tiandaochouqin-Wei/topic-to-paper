# 审稿席位（P7 / S6 的替代做法：`academic-paper-reviewer` 不在本机时，Claude 按此表在本会话内逐席审）

规则不变：每条意见先回结果文件复核再写进 `paper/review_log.md`；每条标 `[major]` / `[minor]` 并给处置（复核通过 / 已改 / rebut / partial）；修完加 `## Re-review` 小节逐条关闭 major；state.review.round 加 1；G6 重跑。`review_check.py` 只认这个格式。

## 研究稿五席

| 席位 | 只问这些问题 | 必须回到的文件 |
|---|---|---|
| R1 方法学 | 主张的作用域有没有越过数据集与口径？每个"更好"有没有 n、seeds、检验？消融格是否在 seed 噪声内却被解读？含命题的稿子：每条命题是否独立重推过证明（量词、期望还是概率、比值损失的分母）？正文里的"不可能/任何/从不"是否逐句对到某条命题？置信区间的重采样单位是否等于 prereg 写的单位？ | results/main.csv、ablation.csv、prereg.md §3/§4/§7、paper/theory_notes.md、分析脚本的重采样代码 |
| R2 领域专家 | 问题是否真实、是否已有人系统回答（gap_map 的饱和计数）、基线是否漏了邻域里被比最多的（mined/baselines.csv） | literature/gap_map.md、problem_table.csv、mined/ |
| R3 复现与泄漏 | 划分键、泄漏开关、关键超参是否生效、硬件是否混用、数字能否溯源 | audit_check / results_check 的输出、runs/*/args.json |
| R4 写作与形状 | 章节顺序与家族画像是否一致、引言是否点名每篇关键论文的失效点、缩略语与图表引用 | shape_check、draft_plan check、gate_check 的输出 |
| R5 编辑 | 一句话说得清贡献吗？局限节是否覆盖预注册的失败分支？投稿文件与正文一致吗？ | paper/claims.csv、prereg.md §8、submission/ |

## 综述稿五席

| 席位 | 只问这些问题 |
|---|---|
| 领域编辑 | 这是综述还是目录？论点一句话是什么，能被证伪吗？ |
| 方法学 | 检索式、日期、计数能复现吗？纳入规则可机械判定吗？编码表每字段有取值集合吗？κ 多少？ |
| 领域专家 | 漏了哪些该纳入的工作？已有综述表是否齐、差异是否成立？ |
| 读者视角 | 读完能据此选方法吗？覆盖矩阵的空白格有没有变成路线图？ |
| 魔鬼代言人 | 论点能否被某篇已有综述或某组被纳入文献直接反驳？ |

## 产出格式（review_log.md）

```
### R1 方法学
1. [major] <意见一句话> → 已改: <改在哪（§x.y / Table n）>
2. [minor] <意见> → rebut: <理由，引用结果文件>

## Re-review (round 1)
- R1-1 closed: <复核依据>
```
