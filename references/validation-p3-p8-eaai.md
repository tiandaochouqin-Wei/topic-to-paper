# P3–P8 流程验证：手术力估计 EAAI 稿全链路（2026-10-07）

## 为什么用这个项目
遥感项目停在 P3 等数据。要验证 P3 到 P8 不能用合成夹具，必须有真实 run、真实 eval 文件、真实正文、真实投稿包。EAAI 稿是唯一全部具备的项目：22 个 run（含泄漏 run 与未训完 run）、18 个 eval.json、9 张图、34 条参考文献、已生成的标题页/盲稿/cover letter/highlights。所有输入直接取自项目文件，`_t2p_validate/` 里只有状态文件、从 eval.json 派生的表和两个生成脚本。

## 每道关口的输入与结果

| 关口 | 输入（真实文件） | 结果 | 当场发现 |
|---|---|---|---|
| G3 audit_check | 16 个主表 run 的 args/log、code/*.py | 泄漏 PASS；有效配置 16 FAIL；静默降级 2 FAIL | 16 条全是基线 run 的 beta/alpha 未生效（is_ours 门控）——与论文 §5.3 "β=0" 口径一致，但 args 写的 0.1 会误导复现者；datasets.py:88/125 两处判 frames/ 读 frames_256.npy 仍在代码里 |
| G4 results_check | main.csv 12 行 + ablation.csv 5 行，全部从 eval.json 派生 | trace PASS 17/17；口径 PASS；seeds WARN（有 waiver）；覆盖 PASS；3 条事前预测符号 PASS | 评估文件均新于 log、无 _tainted |
| G5 dpi | 9 张图，印刷宽度从 LaTeX `\includegraphics` 取 | 8 栅格 ≥300 dpi + 1 矢量，PASS | — |
| G6 refs | tex/refs.bib 34 条 CrossRef 解析 | 25 条 DOI 标题全匹配；9 条无标识符（NeurIPS/ICML/JMLR 老文） | — |
| G6 floats | 正文 | 9 图 8 表全部被引用且存在 | — |
| G6 acronyms | 正文 + 项目白名单 24 项 | 9 个缩略语均首现前展开 | — |
| G6 scope | 正文 | 旧词表 0 句；**加全称量化词后 4 句** | L144 "under any channel loss" 是真实作用域悬置：证据只有四种缺失模式。审稿人 DA 人工先抓到，词表随后补上 |
| G6 numbers | Tables 3/4/5/8 共 101 个数登记到 eval.json | 101/101 值一致；Tables 6/7 的 86 个数**无法登记** | Table 4 一度报 2 处不符，根因是我派生表先四舍五入再算均值；改存原始值后全对。Tables 6/7 由 agentic.py 现场算出不落盘，与 InfoFusion §9.4 同一问题 |
| G6 limits | 关键词 6/6，摘要 250 词 | PASS | — |
| G7 review | 4 999 词的摘要/贡献/§5.3–5.11/§6 + 全部 eval.json | 五席审稿，minor revision，8 条意见 | 每条先回 eval.json 复核：61%、15×、32–40%、27% vs 152%、"most accurate of six"、自适应后反被 RCNN 超过——全部成立且论文已自述。真问题 2 条：贡献 1 的 "any"；摘要 "halves every baseline" 少了 "proprioception-using" |
| G8 submission | 真实标题页、cover letter、highlights、盲稿 PDF 文本 | 数字一致；盲稿干净 | 第一轮误报：盲稿参考文献表里的被引作者 "Zhang" 被当成泄露。关口改为先截掉参考文献表 |

## 对 skill 的修改（本次）
1. `gate_check.py submission`：盲稿检查先 `body_only()` 截掉参考文献表（被引作者不是身份泄露）。
2. `gate_check.py numbers`：`_lookup` 支持多键选行 `method=ours|cond=E2,mean`（派生表需要）。
3. `gate_check.py scope`：SCOPE_STRONG 加 "under/for/on/across any|all|every + 名词"、"robust to any"。EAAI 稿 0→4 句（1 真 + 3 待人工），InfoFusion 稿 2→3 句，未爆炸。
4. lessons.md 新增：**进表的数字其生成脚本必须同时落盘**，否则 numbers 关口无法溯源（两个项目都撞上）。

## 结论
- P3 到 P8 六站的脚本在同一个真实项目上串起来跑通了，所有 FAIL 都能解释，没有一条是关口自身错误（G8 的一条误报已修）。
- 整条链上人仍需做的只剩三件：填 state 的配置段、给审稿意见写处置、对 scope 的 CLAIM 行逐句回表。
- 还没验证的：从 P4 的"训练中"状态自然推进到 P5（本次所有 run 都是训完的）；P7 的 re-review 轮（本次只做了一轮）。这两项要等遥感项目的真实实验。
