# 2026-10-07 第三轮：从"手册"到"一句话"，加综述分支

## 用户的问题
"不能做成不用跑脚本、我告诉你做什么主题的综述你就帮我做的那种 skill 吗？"

两件事出了错：SKILL.md 写得像给人看的命令行手册；九站流程只覆盖有实验的研究论文，综述没有分支。

## 改了什么
1. **SKILL.md 重写为给 Claude 的执行指令**（v2.0.0）。开头一张表："用户说什么 → Claude 做什么"，六种话术各对应一条路径。明确只有四种情况回来问用户（凭据、实质分歧、改锁定的预注册、需要领域判断的 FAIL），其它自己做完汇报。汇报格式固定：结论 → 关口表 → 需要用户做的事，不展示命令和脚本输出。
2. **综述分支 S0–S6**。从两篇 Information Fusion 综述的真实流程提炼：S0 要求写出综述的**论点**（编辑退稿最常见理由是"目录不是综述"）；S1 先查已有综述再系统检索，PubMed 按年切片；S2 协议 = 综述的预注册（纳入/排除规则每条可判定、编码表、主张清单带判据、κ 计划、与已有综述的差异表）；S3 筛选与编码，零 token 部分交脚本、判断部分 Claude 按批做；S4 汇总表必须能从 coded.csv 重算；S5 每个主张回到表的具体行；S6 审稿席位换成综述专属。
3. **`survey_check.py`** 三个子命令 protocol / coding / claims，接进 `t2p.py check`（branch: survey 时隐藏 G2/G3/G4，显示 G-S2/G-S3/G-S5）。`t2p.py init --branch survey` 建综述工作区（coding/ tables/ literature/pdf/，拷 protocol.md 与 codebook.md 模板）。
4. 模板：`templates/protocol.md`、`templates/codebook.md`（照 InfoFusion 的 M0–M3 / L0–L2 写法）；state 模板加 `branch:` 与 `survey:` 段。

## 在真实综述项目上的结果（InfoFusion_multimodal，261 篇编码表）
| 关口 | 结果 | 发现 |
|---|---|---|
| G-S2 protocol | codebook 22 字段全部解析（含 `{img, txt, …}` 集合与 `|` 连接的多值） | — |
| G-S3 coding | 30 034 行筛选表合法；**metric 列 174 行写 AUC 而 codebook 规定 AUROC**；**mechanism 列 68 个值（nomogram/late/LR/stacking/ensemble/contrastive）不在集合**；level 列 1 个 prompt | 这两处会让 §6 的汇总口径不自洽：按 codebook 分组时这些行要么被丢要么被错归。要么改 codebook 加取值，要么重编 |
| G-S5 claims | 三条测试主张都能回到 tables/audit_by_grade.csv 的具体行并满足判据；**"first fusion-gain audit" 主张对应的 25 篇已有综述表没有一行写本文差异** | prior_surveys 要加 how_this_differs 列 |

## 没做的
- S1 的系统检索脚本仍是项目内的（InfoFusion 的 search_literature.py / triage.py / snowball.py），没有抽成 skill 通用脚本。它们依赖主题词表，通用化要等第二个综述项目验证。
- S4 的 `--verify` 约定（汇总脚本自带重算核对）只写在文档里，survey_check 只查有没有生成脚本。
