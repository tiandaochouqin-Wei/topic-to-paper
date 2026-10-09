# Preregistration — domain-robust force estimation (fixture)

锁定日期：2026-10-10
sha256: recorded in research-state.yaml gates.G2.prereg_sha256 (the test harness recomputes it after copying).

## 0. phenomenon
- 现象: GeoNet-style regressors trained on platform E1 degrade on platform E2 even when visual appearance is matched, and the residual is a near-constant offset (source: failure slices of the E1 model on E2 and the recurring gap "no held-out platform" in problem_table.csv).
- 原因假设: the platform-specific sensor offset, not visual appearance, is the dominant cause of the cross-platform error.
- 最小对照实验: done — subtracting the measured offset from the E2 labels before evaluation removed most of the degradation, so the offset is the lever and the method must remove it from the representation.

## 1. hypothesis
Existing force regressors fail under platform shift because the domain-specific sensor offset is absorbed into the regressor; a domain-adversarial regularizer removes this offset, expected RMSE reduction of at least 10 % on the held-out platform.
来源: gap#A

## 2. primary_metric
RMSE of the predicted force against the sensor reading on the held-out platform E1 test split, computed by eval.py in code/ (function rmse_contact); rmse_E2 is the secondary metric and does not enter the success criterion.

## 3. denominator
RMSE is normalised by the number of contact samples per clip and then averaged over clips; the denominator is the same across datasets (E1 and E2), with no per-platform rescaling of forces.

## 4. inclusion_window
contact-window: only samples with |F| ≥ 0.1 N enter the statistics; the window is the same across datasets, and every table header carries the contact-window label so the convention is visible.

## 5. baselines
| 名称 | 来源 | 复现方式 | 预期值范围 |
|---|---|---|---|
| baseA | [1] | official code, 3 seeds | RMSE E1 0.24–0.26 |
| baseB | [3] | re-implemented from the paper | RMSE E1 0.26–0.28 |

## 6. ablations
| 去掉/替换什么 | 预期影响 |
|---|---|
| no_dom | worse: RMSE rises (+), large effect |
| no_cons | worse but small (+) |

## 7. success
ours must reduce RMSE on E1 by at least 5 % relative to the strongest baseline, with 3 seeds per method, the same seed set for every method, and a paired t-test at alpha 0.05 on the per-seed values.

## 8. failure
If the improvement is below 5 % or not consistent across seeds, the hypothesis is rejected; fallback claim: the sensor offset is dataset-specific and we instead report a calibration study of the offset rather than a method claim.

## 9. 数据与划分
Split key is the subject: no subject appears in both train and test (splits/train.txt and splits/test.txt). Target-platform labels are never visible during training (use_target_labels stays 0 in every main-table run).

## 10. 事前预测
- no_dom − ours on rmse_E1: + (higher error without the regularizer, well above seed noise)
- no_cons − ours on rmse_E1: + but small, possibly not resolvable
- ours is lower than baseA and baseB on both rmse_E1 and rmse_E2
