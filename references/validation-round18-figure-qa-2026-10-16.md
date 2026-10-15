# 验证轮 18：从 scipilot-figure-skill / scientific-visualization 搬来的三项（2026-10-16）

## 读了什么

两个 skill 各 3–4k 行。逐脚本读完，判断哪些是本 skill 流程里**真缺**的（而不是"它们有我们没有"）：

| 对方机制 | 本 skill 现状 | 搬不搬 |
|---|---|---|
| scipilot `check_figure._check_pdf_fonts`：pypdf 读字体表，Type 3 FAIL | **本 skill 出的每张 PDF 都是 Type 3**（matplotlib 默认 fonttype=3，没人改过；用 PyMuPDF 查 med-world-model 的 fig_t2p_main.pdf 证实）。G5 查印刷字号时读的就是这个 PDF，却从没查过字体类型 | 搬 |
| scipilot `visual_qa.audit_layout`：存图前内存渲染，缺字 / 越界 / 刻度重叠 | G5 只在存图后查；缺字方框、刻度挤成团只能靠目测 | 搬，接进 `finish()` |
| scipilot `export_figure._grayscale_from`：灰度预览 | 没有；dataviz 规则写了"灰度下可分"但没产物 | 搬 |
| scipilot `profile_data` + chart_selection：先剖析数据再选图型 | 本 skill 的图型由结果表结构决定（main/ablation/seeds/curves），不需要"选"；非标准图已路由给 scipilot（17b） | 不搬 |
| scipilot `setup_style` 的 CJK 字体配置 | 本 skill 面向英文投稿；中文稿路由给 scipilot | 不搬 |
| scientific-visualization `style_presets.configure_for_journal`：按刊设 rcParams | 本 skill 的版心宽度已从 `latex_check.py widths --tex` 实测，比预设准 | 不搬 |
| scientific-visualization `figure_export.verify_font_embedding` | 与 scipilot 同一件事 | 并入上面第一项 |

## 改动

| 位置 | 内容 |
|---|---|
| `scripts/make_figure.py` | rcParams 加 `pdf.fonttype=42, ps.fonttype=42, axes.unicode_minus=False`；新函数 `audit_layout(fig)`（缺字 FAIL；文字**压到别的面板**的数据区 WARN——不是"出画布"，因为 `bbox_inches="tight"` 会把页面撑大，出画布不是问题；相邻刻度标签包围盒相交 WARN）；`finish()` 存图前跑它，结果打印、写进 figures.csv 的 issues，FAIL 退出 1；同时写 `<name>_gray.png` |
| `scripts/gate_check.py` | `_dpi_fonts_embedded`：登记的 PDF 含 Type 3 → FAIL，未嵌入 → WARN（pypdf，缺则 INFO）；`_dpi_grayscale`：没有 `_gray.png` 的图 INFO。挂在 `gate_dpi` 里印刷字号之后 |
| `gates.md`、`phases/P5.md`、`lessons.md` | 各一段 / 两行 |
| `tests/test_fig_qa.py` | 5 个：出图无 Type 3 且有灰度；G5 对 fonttype=3 的 PDF FAIL；audit 抓刻度重叠与缺字；干净图零告警；跨面板压字 WARN |

## 在真项目上

med-world-model `fig_t2p_main.pdf` 重出：字体从 `Type3 TimesNewRomanPSMT` 变为 TrueType；G5 对项目里 4 张 skill 图报"字体全部嵌入且无 Type 3"。

## 教训

- "出画布"不等于"被裁切"：第一版 audit 把 x 轴标签在名义画布之外也报 WARN，一张最普通的图就误报。tight bbox 救得回画布外，救不回压到别的面板上——判据要按存图方式定。
- 没人看过自己出的 PDF 里是什么字体。G5 读 PDF 文本层查字号已经一轮了，字体表就在旁边。
- fonttype 42 出的是 Type0 复合字体，字体程序挂在 `/DescendantFonts` 的描述符上，不在顶层；第一版嵌入检查只看顶层，把刚修好的图又报成"未嵌入"。查嵌入要沿 descendant 走一层。

281 tests pass（6 e2e deselected）。未 push。
