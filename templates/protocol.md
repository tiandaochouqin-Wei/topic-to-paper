# 综述协议（综述分支的预注册；S2 末哈希锁定）

锁定日期：
sha256（锁定后写入 research-state.yaml gates.G-S2.protocol_sha256）：
目标刊：
综述的论点（一句可证伪的话，不是"我们综述了 X"）：

## 1. inclusion 纳入规则
每条必须可机械判定（含阈值、数量、必须含的词、年份区间之一）。
- 发表年份 2015-01-01 至 检索日
- 同行评审期刊或 CVPR/ICCV/ECCV/NeurIPS/ICML/ICLR/MICCAI 正会；arXiv 仅当被 ≥1 篇纳入文献引用
- 标题 + 摘要命中 ≥2 个数据源族（族表见 codebook `pair`）且含方法词（见 codebook `mechanism`）
- 报告了融合模型与至少一个单模态基线在同一测试集上的数值

## 2. exclusion 排除规则
- 单一数据源族内的融合（如多序列 MRI）—— 由已有综述 [x] 覆盖
- 无定量评估的综述、观点、协议文章
- 非英文全文

## 3. codebook 编码表
见 `coding/codebook.md`。每字段：列名 | 取值集合或"free text"/"float"/"int" | 判定规则。编码来源（标题/摘要/方法节）记在 `source` 列。

## 4. claims 主张清单
| claim | 判据（从 coded.csv 能算出来的条件） | 事前预测 |
|---|---|---|
| A 报告的融合增益随基线匹配严格度缩小 | M3 组 Δ_rep 中位数 < M1 组中位数 | 成立，差 0.01–0.03 |
| B 大多数研究不报告差值的不确定性 | delta_ci = yes 的占比 < 30% | 成立，约 20–25% |
| C 缺失模态测试罕见 | missing_test = yes 的占比 < 10% | 成立 |

## 5. prediction 事前预测
对每条主张写方向与量级（上表第三列）。跑完汇总后与此对照，偏离要在正文解释并在 state.convention_changes 记录。

## 6. kappa 第二编码员验证
抽 100 篇（按自动预筛层级分层），第二编码员盲于规则编码；报告每个字段的 κ；κ < 0.6 的字段修改 codebook 规则后重编。正文 limitations 节明写第二编码员是谁（人或语言模型）。

## 7. 与已有综述的差异
`literature/prior_surveys.csv`：近 5 年同主题综述，每行 title, year, venue, doi, how_this_differs。≥3 篇时正文要有对比表。
