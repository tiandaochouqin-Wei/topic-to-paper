# Codebook — fixture (one row per included study in coding/coded.csv)

| column | values | rule |
|---|---|---|
| `doi` | free text | identifier |
| `year` | int | publication year |
| `pair` | {img, txt, ehr, sig} (joined subset, alphabetical) | data-source families actually fed to the fusion model |
| `task` | {dx, prog, seg, other} | main task |
| `level` | {data, feature, decision, mixed} | where fusion happens |
| `mechanism` | {concat, attn, graph, other} | fusion operator |
| `metric` | {AUROC, AUPRC, Cindex, acc, other} | metric used for the gain |
| `P_fusion` | float | fusion model score on the main test set |
| `P_best_uni` | float | best unimodal score on the same test set |
| `delta_rep` | float | P_fusion minus P_best_uni |
| `delta_ci` | {yes, no} | confidence interval or variance of the difference reported |
| `M` | {0, 1, 2, 3} | baseline matching level |
| `L` | {0, 1, 2, ?} | leakage exposure |
| `ablation` | {yes, no} | modality ablation reported |
| `missing_test` | {yes, no} | missing-modality test reported |
| `ext_val` | {yes, no} | external or multi-centre test set |
| `n_test` | int | test subjects |
| `source` | {title, abstract, methods} | where the coding came from |
| `notes` | free text | |
