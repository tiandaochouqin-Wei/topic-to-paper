# 验证轮 9：按稿件家族分写法（2026-10-09）

起因：用户指出 CCF-A 会议、CS 期刊、Nature/Science 系三类稿件的长度、写法、格式不同，skill 之前只有一套写作规定（和 limits 关口的字数上限）。

## 数据
`scripts/venue_shape.py` 对 275 篇校准语料提取章节序列、各节词数占比、Methods 是否在 Results 后、贡献列表、句式小标题、公式、"we" 密度、SI 提及等 38 列（`references/venue-shape-per-paper.csv`），与已有的 venue-norms 合并成三个家族画像 `references/venue-profiles.md`。关键差异（中位数/占比，cs_conf n=100 / cs_journal n=75 / nature n=98）：

| 特征 | cs_conf | cs_journal | nature |
|---|---|---|---|
| Methods 在 Results 后 | ≈0 | ≈0 | 96% |
| Related Work 节 | 75% | 53% | 5% |
| Conclusion 节 | 87% | 52% | 11% |
| 引言贡献列表 | 44% | 29% | 0% |
| Results 句式小标题（中位） | 1 | 0 | 4 |
| 正文公式（中位） | 6 | 14 | 0 |
| Discussion 占正文 | 4% | 8% | 18% |
| 消融 | 63% | 78% | 10% |
| p 值 / CI | 5% / 3% | 4% / 1% | 63% / 30% |
| "state-of-the-art" | 73% | 78% | 20% |
| "we" /千词 | 17 | 19 | 9 |

检测器的已知失真：CS 双栏 PDF 的章节序列命中率 30–50%（标题被拆行），TIP 文本层把全文并进一节，Nat Med 混入 Perspective；所以画像用家族中位数，单 venue 行只作参考。

## 加了什么
- `references/venue-profiles.md`：三家族的硬差异、各 venue 原始行、写作规则、跨家族迁移最常犯的错。
- `templates/skeleton-{cs_conf,cs_journal,nature}.md`：P6 起点骨架，每节注明该从 P1–P4 哪个产物取内容。
- `state.target.family`（空则由 venue 名推断）。
- `scripts/shape_check.py` = **G6c**：按家族查章节顺序、禁用节、摘要长度/段数/引用、贡献列表 vs "Here we show"、句式小标题、公式位置、禁用词、Discussion 占比、统计句占比、"we" 密度；CS 侧查贡献条目 3–5、Ablation 小节、方法公式、Related/Limitations。
- `draft_plan.py` 加家族项（nature：Here-we-show 句、句式小标题、与前人结论的关系；cs：贡献列表、消融小节、结论含数字）。
- t2p.py 状态板加 G6c 行；SKILL.md P0 定 family、P6 先取骨架。

## 验证
- **6 篇 Nature 系 OA 论文**（Europe PMC JATS → jats_to_md：Nat Commun ×4、Nat MI ×1、Nat Med ×1）：5 篇 ALL PASS；1 篇 FAIL 是 Nat MI 稿真的有 Conclusion 节（该刊允许，判据对 Nat Commun/Med 正确）。
- **3 篇 CS**（CVPR/NeurIPS/TPAMI PDF → pdf_to_md）：章节顺序、摘要、引言占比全过；贡献条目与消融小节报 FAIL 是 PDF 转换丢了项目符和小标题（TPAMI 的 "• We propose…" 三条在文本层里有但不在行首）。改为"有 contributions 句但无条目 → 按 We propose… 句计数"后 TPAMI 过。对作者 markdown 稿无此问题。
- **EAAI 稿**：按 cs_journal ALL PASS（摘要 251 词 +3% 容差内）；强制按 nature 判 8 FAIL，每条都对（有 Related/Conclusion/贡献列表、摘要 251 词、Results 小标题 1/11 是句子、Discussion 4%）。
- 校准改掉的阈值：Nature 已发表摘要 150–230 词（投稿限 150，出版后常超）→ >1.6× 才 FAIL；Nat Med Results 小标题是名词短语 → 句式小标题 ≥2 WARN 不 FAIL；SOTA 词 Nature 20% 出现 → WARN；Discussion 6–12% → WARN。

## 坑
- JATS 的 Abstract 节后跟 "Subject terms" 和编辑摘要段，直接数词把 150 数成 250；只取第一段。
- IEEE 的 "Abstract—…" 内联在正文首行，无标题；正则提升为节。
- PDF 转换出的重复短节（页眉 "Introduction"）让 sec() 取到空节；改取同名最长节。
- heredoc 写含 `\s` `\[` 的补丁再次失败（记忆里已有此坑），改用 Edit 工具。

## 仍不机械的
形状对不等于写得对。"Here we show" 句可以有而主张错；Nature 的 Discussion 四段（与前人关系/机制/局限/边界）只查了"与前人关系"一项的措辞。
