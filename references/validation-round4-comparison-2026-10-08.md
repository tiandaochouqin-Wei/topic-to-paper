# 验证轮 4：对比图表生成器（2026-10-08）

对照样本：Zhang et al., *SKYDET*, IEEE TGRS 64 (2026), `Z:\LDCT\SKYDET_An_End-to-End_Multiscale_Attentive_Detection_Network_From_Foundation_Models_for_Small_Objects_in_Remote_Sensing_Images.pdf`，Fig. 5/6、Table III/IV/V/VII。

## 新增 `scripts/make_comparison.py`

| 子命令 | 复刻目标 | 输入 | 验证结果 |
|---|---|---|---|
| `sota` | Table III（AI-TOD，23 行，CNN/Transformer 分组，Params/FLOPs，红最优/蓝次优，ours 加粗置底） | 23 行 CSV 抄自原表 | pdflatex 编译通过，红/蓝标记 6 处与原表逐格一致（0.561 红、0.553 蓝、0.235/0.278 红、0.218/0.265 蓝） |
| `multi` | 多数据集并排（NWPU + AI-TOD） | 10 行长表 | `\multicolumn` 表头 + `\cmidrule` 正确；每数据集独立排名 |
| `ablation` | Table V（✓/× 三组件，Group 列，全 ✓ 行加粗） | 4 行 | 与原表逐格一致 |
| `seeds` | Table VII（5 seed + Mean ± Std，最优设置加粗） | 10 行长表 | 编译通过 |
| `grid` | Fig. 5（Origin + N 方法 × M 样本，右上 inset 放大，方法名在列下，`--cols` 换行分组） | 6 方法 × 2 合成样本 | 2884 px @ 183 mm = 400 dpi，自动算格子尺寸与字号 |

## 与 G6 的接线
`--numbers` 把每格写进 `paper/numbers.csv`，key 形如 `dataset=|method=SKYDET-C|metric=AP50,value` 指向 `<out>.source.csv`。
对照试验：97 条映射全 PASS；人为把 0.561 改成 0.571 后 numbers 关口两条 FAIL（值不符 + 正文无此数）。即生成的表格数字从此不可能与结果文件脱节。

## 发现并修掉的坑
1. `--extra` 列（Params/FLOPs）最初统一格式化到 2 位小数，把原表的 `258.2` 印成 `258.20`。改为按原文逐字引用，不重格式化：这些列来自论文抄录而非自家结果，改写小数位等于改写数据。
2. grid 的标签高度固定 28 px，字号随格子放大后被裁掉下半截。改为字号 = 0.085 × 格子边、标签带高 = 1.7 × 字号。
3. 表头下标：`AP50_95` 这类列名直接进 LaTeX 会出 `AP50\_95`。加 `--labels 'AP50_95=AP$_{50:95}$'`，Markdown 镜像自动去 `$`。

## 未做
- grid 的 inset 位置目前全图统一（`--inset x,y,w,h` 为源图分数坐标）；原文 Fig. 5 每个样本的 inset 位置不同。需要时按样本给一个 CSV。
- 表格里的 `\cite{44}` 用的是 `--cite-col` 的裸数字；真实稿件应填 bib key，由 tex_to_md 解析。
- 跑一次 `t2p.py check` 时 G6 对 `_gen/` 下的试验稿不生效（不在 paper/），这是预期。
