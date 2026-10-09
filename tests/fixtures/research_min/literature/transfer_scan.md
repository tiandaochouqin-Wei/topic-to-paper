# 方法迁移扫描（P1 第二产物）— fixture

结构查询（不含领域词）：regression under label-side offset, nuisance removal from shared representation
领域词（count 用）：surgical force estimation
来源：fixture rows (no network call); 域内计数 format follows `transfer_scan.py count`.

## 候选

| # | 方法 | 来源（刊/会 年） | 问题结构 | 对应物 | 域内计数 | 失效点 | 判定 |
|---|---|---|---|---|---|---|---|
| T1 | adversarial nuisance removal | ICML 2025 | remove a nuisance variable from a shared encoder | platform identity as the nuisance | oa:1+local:0 | the nuisance is in the label channel, not the input, so the discriminator must see the prediction head | 候选 |
| T2 | offset-invariant regression | NeurIPS 2025 | regression with an additive per-domain bias | per-platform sensor offset | oa:0+local:0 | the offset is force-dependent at contact onset, a constant bias model under-corrects | 候选 |
| T3 | test-time entropy minimisation | CVPR 2025 | adapt batch statistics at test time | per-clip adaptation | oa:2+local:1 | — | 淘汰-无失效点 |
| T4 | domain-adversarial training | ICML 2024 | align input distributions | image-level alignment | oa:14+local:3 | aligns appearance, leaves the label offset | 淘汰-已有人做 |
| T5 | optimal-transport label shift | ICML 2025 | reweight classes under label shift | — | oa:0+local:0 | regression labels have no classes to reweight | 淘汰-无对应 |
