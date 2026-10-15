# 验证轮 17：画图能力补全（2026-10-16，来自 med-world-model）

## 触发

用 skill 给 med-world-model 稿出图：12 张图里 `make_figure.py` 只能画 3 张（main / ablation / seeds），
曲线类（rollout horizon、校准、留出分位曲线）全靠手写 matplotlib；`make_comparison.py seeds` 把 NLL
最大的一行加粗；P5.md 与 routing.md 把"其它数据图"路由到本机不存在的 `cs-experiment-figure-studio`。
figure-norms 自己的统计：cs_conf 论文 33%、cs_journal 55% 含曲线图——关口验得出缺，脚本画不出来。

## 改动

| 位置 | 内容 |
|---|---|
| `scripts/make_figure.py` | 新子命令 `curves --csv <long> --x --y [--series] [--panel] [--band sd\|minmax\|none] [--logx]`：长表一行一点，同 (series, x) 的多 seed 合并成均值 + 带，`--panel` 列每个取值一个面板；`--ours` 红。出 .png/.pdf/.source.csv（panel, series, x, y_mean, y_sd, n）并登记 figures.csv。缺列 FAIL 并列出可用列 |
| `scripts/make_figure.py` | 所有子命令加 `--lower m1,m2`；main / seeds 的 .source.csv 多一列 `best`（--lower 指标取最小均值，其余最大）。画法不变，只改"谁是最好"的记录 |
| `scripts/make_comparison.py` | `seeds` 子表的加粗按 `--lower` 取方向（原先一律 max） |
| `references/routing.md`、`phases/P5.md` | 去掉不存在的 skill；数据图先试 `make_figure.py` 四个子命令，不够再 `nature-figure` / `academic-plotting` |
| `SKILL.md` | P5 行加 `curves` |
| `references/lessons.md` | 三行 |
| `tests/test_figure_caps.py` | 5 个测试：curves 产物与 seed 合并、缺列 FAIL、main best 跟随 --lower、comparison seeds 加粗跟随 --lower、路由不指向未安装 skill |

## 在真项目上

med-world-model 的 rollout 曲线（4 目标 × 2 库 × 48 h）：`make_figure.py curves --csv results/rollout_long.csv
--x horizon_h --y mae --series objective --panel dataset --band none --lower mae` 一条命令复现了手写的图 4。

## 教训

- 补丁脚本里的 `"\n"` 经 bash heredoc 会变成真实换行；连错三次后改用 Edit 工具改那一行。lessons.md 早就记了"不要用 heredoc 打补丁"，这次是在补丁脚本本身上又犯了一次。
- 断言 `count(x) == 2` 要算准 helper 定义行也含该子串；对调用点计数要带缩进前缀。

## 17b：路由指向 scipilot-figure-skill（同日）

用户装了 `scipilot-figure-skill`（Haojae，2.6k⭐，无 API key；pip 装了 SciencePlots）。routing.md 两行与 P5.md
一句改为：非标准数据图默认走它（先剖析数据再按论证目标推荐图型，拦小样本均值柱 / 双 Y 轴 / 截断轴，
Nature / IEEE / 中文核心期刊版式，CJK 字体自动配），要 R 或 Nature QA 清单时走 `nature-figure`。
`test_routing_names_only_installed_or_bundled_skills` 同时断言两处都提到 scipilot。

在 med-world-model 的 `results/seeds_long.csv` 上跑它的 `profile_data.py`：识别出 setting 每类 n=5，
警告「小样本必须展示原始数据点，不要只画均值柱状图」——与本 skill `make_figure.py main` 的
mean±sd + 逐种子点设计一致，两边规则互相印证。

275 tests pass（6 e2e deselected）。未 push。

## 后续（2026-10-15，metric-direction 修复 d779de4 合并后）

`make_comparison.py seeds` 的方向改用共享的 `higher_for()`；`make_figure.py` 的 best 列在 `--lower` 未列出时读 state 的 `metric_direction` / `primary_direction`，再按 `metric_direction.py` 的列名正则。`test_comparison_seeds_bold_follows_lower` 后半随之改为：`nll` 不写 `--lower` 也按名字判为 lower；正则认不出的列名（`score`）才默认 higher。
