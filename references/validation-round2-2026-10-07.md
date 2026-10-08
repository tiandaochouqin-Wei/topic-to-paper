# 2026-10-07 第二轮优化：入口、LaTeX 输入、跨项目压测

## 做了什么
1. **`t2p.py` 前门**。四个子命令：`init`（从模板建工作区，填 venue/field/started）、`check`（读 state，凡输入存在的关口都跑，九行状态板，退出码 = FAIL 数）、`status`（只读 state）、`doctor`（依赖 + 每个脚本 `--help`）。此前 12 个脚本各有各的参数，新用户要读 18 KB 的 SKILL.md 才知道从哪开始。
2. **`tex_to_md.py`**。LaTeX 稿不再需要手写 Markdown 镜像：图表按出现顺序编号并把 `\label` 映射到同一编号，`\ref/\autoref/\cref` 解析，`\cite` 按首次出现转 `[n]` 并裁出 `refs.bib`，`tabular` 转 Markdown 表，`includegraphics` 的宽度按 `\textwidth`/`\columnwidth`（双栏类取半）折算进 figures.csv。
3. **四个脚本补 argparse**（calibrate、jats_to_md、pdf_to_md、venue_norms）：此前 `--help` 直接 IndexError。
4. **numbers 关口按表汇报未登记数字**：`Table 5 ×22; Table 6 ×35; Table 7 ×28; Table 8 ×3`，而不是一串裸数字。
5. `check` 的 PENDING 判定：prereg.md 仍是模板、figures.csv 仍是模板、state.audits 没填关键字段，都算 PENDING 而不是跑出一堆无意义 FAIL。

## 压测：四个真实项目

| 项目 | 输入形态 | 结果 | 暴露的问题（项目的，不是 skill 的） |
|---|---|---|---|
| RS_nowcast | 本 skill 原生 | G0–G2 PASS，G3–G8 PENDING，退出码 0 | 无；状态板正确指向 G3 |
| 机械学报/_t2p_validate（EAAI） | Markdown + 真实 run | 9 道全跑：G2 9F（事后重建的 prereg 本就不完整）、G3 18F（已知）、G4/G5/G7/G8 PASS、G6 numbers 2F | Tables 5–8 共 86 个数无落盘来源 |
| OrganFusion_TCyb | LaTeX（IEEEtran） | tex_to_md 转出 2 图 5 表 55 引用；floats 报 Fig. 3–8 悬空、acronyms 报 MONTH/DAY/XXXX | **55 个 `\cite` 键里 43 个是 `ORIG_11` 式占位符，bib 里没有**；正文第 336–347 行是粘贴进来的 PDF 图轴文本（"0.5 0.6 0.7 0.8 0.9 1.0 AUC-ROC 0.728 …"），审稿 PDF 会原样印出来 |
| CUG_TTA_MedSeg | LaTeX（草稿） | 0 图 0 表 23 引用（11 键缺）；scope 抓到 "The first front-door TTA framework" | 稿子还是骨架；bib 缺 11 个键 |

OrganFusion 那两条是这轮最有价值的发现：这篇稿在 `tools/` 里有 28 个自检脚本，没有一个查"引用键是否在 bib 里"或"正文里有没有粘贴的 PDF 文本"。tex_to_md 现在对后者打 WARN（≥8 个小数且非表格的长行）。

## 对 skill 的修改
- 新增 `scripts/t2p.py`、`scripts/tex_to_md.py`
- `gate_check.py numbers`：按表汇报
- 四个脚本 argparse
- SKILL.md 顶部加"一条命令"块，resume 改成 `status → check`
- routing.md 加 LaTeX 入口

## 下一轮候选（按价值排）
1. `tex_to_md` 的 `\cite` 键缺失现在只在转换时打印，应进 G1/G6 的 refs 关口作为 FAIL（"引用了 bib 里没有的键"是比 DOI 错更早的错）。
2. OrganFusion 式"粘贴 PDF 文本"应成为 G6 的独立检查，不只在转换器里 WARN。
3. `t2p.py check --fix-hints`：每条 FAIL 后面直接给出改哪个文件哪一行的建议（现在要人去翻对应脚本的输出）。
