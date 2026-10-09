# 综述协议 — fixture (survey branch preregistration)

锁定日期：2026-10-10
sha256: recorded in research-state.yaml gates.G-S2.protocol_sha256 (the test harness recomputes it after copying).
目标刊：Information Fusion
综述的论点：the reported fusion gain shrinks as the baseline matching level gets stricter.

## 1. inclusion 纳入规则
- Published between 2015 and 2026 in a peer-reviewed journal or conference.
- Title and abstract must name at least two data-source families from the codebook `pair` set.
- Reports a fusion model and at least one unimodal baseline on the same test set.

## 2. exclusion 排除规则
- Fusion within a single data-source family, such as multi-sequence MRI, covered by [1].
- Papers that report 0 quantitative results, such as reviews, perspectives and protocols.
- Full text not available in English.

## 3. codebook 编码表
See coding/codebook.md: one row per included study; each field has a value set or is marked free text / float / int, and the `source` column records which part of the paper the value came from.

## 4. claims 主张清单
| claim | 判据（从 coded.csv 能算出来的条件） | 事前预测 |
|---|---|---|
| A the reported fusion gain shrinks as baseline matching gets stricter | median delta_rep of the M3 group < median of the M1 group and < 0.03 | holds |
| B most studies do not report uncertainty of the gain | fraction of delta_ci = yes < 0.5 | holds |

## 5. prediction 事前预测
Both claims are expected to hold: the M3 median is predicted below 0.03 and the delta_ci fraction below 0.5. Deviations are explained in the text and recorded in state.convention_changes.

## 6. kappa 第二编码员验证
A second coder blind to the rules codes every included study; kappa is reported per field in coding/kappa_results.json and any field below 0.6 is re-coded after its rule is clarified.

## 7. 与已有综述的差异
literature/prior_surveys.csv lists the prior surveys on the topic and states how this survey differs from each of them.
