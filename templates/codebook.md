# Codebook — 编码表（每字段：列名 | 取值集合 或 free text / float / int | 判定规则）

一行一篇纳入文献，写进 `coding/coded.csv`。取值不在集合内的，`survey_check.py coding` 判 FAIL；未知写 `?`。

| column | values | rule |
|---|---|---|
| `doi` | free text | 标识符，优先 DOI，其次 pmid / arxiv_id |
| `year` | int | 发表年 |
| `pair` | img, txt, ehr, sig, omics, know, pro（`\|` 连接，字母序） | 实际喂进融合模型的数据源族，不是仅提到的 |
| `task` | dx, grade, prog, resp, seg, det, gen, retr, other | 主任务 |
| `level` | data, feature, semantic, decision, knowledge, mixed | 融合发生的层级；data = 任何可学习编码器之前合并 |
| `mechanism` | concat, attn, graph, gen, retrieval, moe, prompt, gating, other | 融合算子 |
| `metric` | AUROC, AUPRC, Cindex, acc, F1, Dice, BLEU, other | 用于 Δ 的指标 |
| `P_fusion` | float | 融合模型在主测试集上的值 |
| `P_best_uni` | float | 同一测试集上最强单模态模型的值 |
| `delta_rep` | float | P_fusion − P_best_uni；M0 留空 |
| `delta_ci` | yes, no | 是否报告了**差值**的 CI 或重复划分方差 |
| `M` | 0, 1, 2, 3 | 基线匹配等级：0 无单模态基线；1 有但训练预算/骨干不同；2 同骨干同预算；3 同骨干同预算且同完整病例队列 |
| `L` | 0, 1, 2, ? | 泄漏暴露：0 受试者级划分且无目标信息进训练；1 划分级别不明；2 样本级划分或目标信息可见 |
| `ablation` | yes, no | 报告了模态消融 |
| `missing_test` | yes, no | 报告了缺失模态下的性能 |
| `ext_val` | yes, no | 外部/多中心测试集 |
| `n_test` | int | 测试集受试者数 |
| `source` | title, abstract, methods | 编码依据来自哪一层 |
| `notes` | free text | |
