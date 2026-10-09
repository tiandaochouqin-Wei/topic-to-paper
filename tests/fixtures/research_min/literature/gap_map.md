# Gap map（P1 第一产物）— fixture

语料：literature/problem_table.csv 8 条；counts below are illustrative.

## 候选主张与饱和证据

| # | 候选主张 | 邻域计数（逐年） | 主张计数（逐年） | 判定 |
|---|---|---|---|---|
| A | the cross-platform error of force regressors is a label-side sensor offset that a domain-adversarial term can remove | 2024:38 2025:51 2026:44 | 2024:0 2025:1 2026:0 | go |
| B | self-supervised video pretraining fixes platform shift | 2024:120 2025:160 2026:150 | 2024:9 2025:14 2026:17 | 饱和，只引用 |
| C | tactile sensors replace vision | 2024:20 2025:22 2026:19 | 2024:4 2025:6 2026:5 | 不可及（硬件） |

## 现有方法在哪里失效

| 工作 | 做法 | 失效点（原句） |
|---|---|---|
| GeoNet | geometric features plus a regression head | "we assume the force sensor calibration is shared across platforms" |
| ForceFormer | appearance-adaptive transformer with a per-platform head | "the prediction head is specific to the training platform" |

## 反复出现的"未来工作"
Three of eight papers list "validate on a held-out robot platform" as future work; none does it.

## 评测盲区
The standard full-window evaluation averages over non-contact samples, which hides the offset error because most frames carry zero force; the contact-window convention exposes it.

## 邻域默认假设
In the adjacent field of visual domain adaptation the default assumption is that the shift lives in the image statistics, whereas in force sensing the shift is partly in the label channel itself; neither community has tested the label-side assumption.

## 判定
verdict: go
claim_source: gap#A
reason: three of eight core papers share the gap "no held-out platform" and none models the sensor offset explicitly
值不值得做（五行都要答）：
- 重要性: Surgical force estimation must transfer across robot platforms because recalibrating the sensor for every platform is impractical in the operating room
- 新颖性: no prior work isolates the sensor offset as the cause of cross-platform degradation
- 可验证性: the offset hypothesis is testable with a held-out platform and a single control experiment that changes only the offset
- 可解释性: the regularizer removes a named nuisance variable rather than adding capacity
- 可推广性: two platforms in this study; a third platform is listed as future validation
