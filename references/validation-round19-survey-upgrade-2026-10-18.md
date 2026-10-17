# 2026-10-18 第十九轮：2.11.0 综述升级在真实综述项目上的首次运行

## 做了什么
把 2.11.0（分支 feat/survey-upgrade，未提交）的全部新规则与新脚本，拿到第一次验证过 survey 分支的真实项目上跑：`D:\claude-pro\1\机械学报\InfoFusion_multimodal`（261 篇审计编码表、30 034 行筛选表）。在临时目录里的副本上操作，原项目没动。第二个真实项目 `InfoFusion_review`（纵向影像综述）只读，用来测两处：手写的 `kappa_results.json`（κ 文件格式）和 2 000 行成稿（目录式段落检测器的假阳性）。

该项目没有 `research-state.yaml`，目录也不是 skill 的默认布局（`lit/` 而非 `literature/`，编码表叫 `audit_coded.csv`）。副本里补了一份 state，把 `survey:` 段的路径指向项目自己的文件；`paper/manuscript.md` 由 `draft_sec3_framework.md` + `draft_sec6_audit.md` 拼成。这是"一个已有项目接进来"的真实用法，也因此暴露了几处格式假设。

**项目里本来没有、为了跑每条规则而补的输入**（均已标明，不当作真实发现）：
| 输入 | 来源 |
|---|---|
| `coding/tables.yaml` | 按项目自己的 `audit_summary.py` 重写；结果与手写表逐格一致（M1 中位 0.056、均值 0.085、q25 0.032、q75 0.110；L? 中位 0.138） |
| `coding/audit_coded.csv` 加 `audit_status` 列 | 手写脚本靠 `notes` 里含 "exclude/duplicate" 过滤；spec 的 `where` 表达不了，所以项目侧加一列（234 / 25 / 2） |
| `paper/claims.csv`、`coding/tensions.csv` | 3 条主张、3 对研究（引用正文原句）；手写 |
| `lit/seed_studies.csv` | 从 coded 取 12 篇，故意写成 DOI URL / 大写 / 仅标题 三种形式 |
| `coding/coded_second.csv`、`coded_second_b.csv` | **模拟**的第二编码员（随机翻转若干格），只为跑 κ 与 PABAK 分支 |
| `coding/qc_exclusion_sample.csv` 的 `qc_decision` | **模拟**复核（全部 exclude，另让 2 条 near_miss 判 include） |
| `paper/prisma_checklist.csv` | 模板原样拷入，未填 location |

## 跑了什么
`t2p.py check`，以及 `survey_check.py` scope / search / coding / tables / claims / writing，`survey_tables.py` summary / crosstab / kappa / characteristics / prior / qc-sample，`survey_figure.py` prisma / timeline / coverage / bubble / rob。所有新规则都在真实数据上执行过一遍。五张图都看过（见下）。

## 真问题（项目本身的问题，规则抓对了）
| 位置 | 发现 |
|---|---|
| G-S3 | `metric` 174 行写 AUC 而 codebook 规定 AUROC，另有 QWK / Obuchowski / r；`mechanism` 80 个值（nomogram / late / LR / stacking / ensemble …）不在集合；`level` 1 个 prompt。**与第三轮同一批问题**，仍未修 |
| G-S3 | 编码表 `sel_same` 列在 codebook 里叫 `sel_same_cohort`，名字对不上 |
| G-S1 | `candidates.csv` 有 192 行无任何标识符：全是滚雪球记录，URL 是 `semanticscholar.org/paper/None`，是 `snowball.py` 取不到 ID 时仍写入的垃圾行 |
| G-S1 / G-S5 | 25 篇已有综述的 `how_this_differs` 仍为空（第三轮已指出），"first fusion-gain audit" 主张因此 FAIL |
| G-S1 | 只做了一轮滚雪球（`snowball_log.json` 是 25 个种子的统计，没有轮次与 new_included），饱和规则无从判断（WARN，正确） |
| G-S3 | 2 683 篇 include 没进 coded.csv（审计子集，WARN，正确：正文 §6.1 已说明） |
| G-S3 | 无 κ（真项目没做第二编码）；QC 排除抽样没做。系统综述必做，FAIL 正确 |
| G-S3 | PRISMA 里 `reason` 列存的是"机制"（`title_manual` / `abstract_manual`）而不是排除理由，PRISMA 图因此只有一个理由类别 "abstract_manual (n = 501)"。流程图要的是理由分类，项目没记 |
| G-S4 | `level=feature` 占已知值 87%（skew 提示，WARN，讨论节要回答是领域还是检索造成） |
| G-S5 | PRISMA 清单 42 项全未定位（`review_type: systematic` 时 FAIL，正确）；§3/§6 草稿只覆盖方法论与结果 |
| 另 | 正文 §6.1 写"2 563 篇标题级纳入"，筛选表 include 是 2 937（含 374 篇摘要级纳入）；这条不归本 skill 的关口管，但数字对账时会撞上 |
| 另 | 手写的 `InfoFusion_review/coding/kappa_results.json`：4 个字段 κ < 0.6（fusion_level 0.47、task 0.44、n_timepoints 0.10、treatment_conditioned 0.27），按规则 FAIL 是对的，该项目自己也记了这件事 |

## 假阳性（新规则的错，已修）
| # | 规则 | 现象 | 原因 | 修法 |
|---|---|---|---|---|
| 1 | G-S1 检索源 | `terms` / `prescreen_flags` 被当成检索源，报"缺 query/date/count"；`snowball` 缺 date | 扁平日志的 `date` 在顶层，`terms` 是检索式；`pubmed_records: N` 是计数不是 dict | `_sources`：跳过元数据 dict；源没写 date/query 时继承顶层 `date` 与 `query`/`terms`；认 `<name>_records` 计数 |
| 2 | G-S1 种子召回 | 12 个种子漏 2 个 | (a) `https://doi.org/10.1016/J.…` 未规范化，与候选里小写裸 DOI 对不上；(b) 种子标题抄自截断到 150 字符的编码表，与完整标题精确匹配失败 | DOI 去 URL/`doi:` 前缀并转小写（同时用于候选去重、QC 联表、include↔coded 对账）；标题 ≥ 8 词时允许前缀匹配 |
| 3 | G-S3 PRISMA 单调性 | FAIL：included 2 937 > screened_abstract 875 | 项目的 `abstract_screened` 是"摘要级读过的 875 条 maybe"，不是"进入资格评估"阶段（3 438 = 5 247 已决 − 1 809 标题级排除；2 937 + 501 摘要级排除恰好 = 3 438）。同时 `identified` 与 `deduplicated` 都取了 `candidates`（30 034），没用 search_log 的 total_raw 31 850 | 新增共享的 `prisma_counts` / `load_prisma`：`screened_abstract` 小于 included 时改用筛选表推出的阶段数并打 INFO；identified 取 search_log.total_raw。**G-S3 与 `survey_figure.py prisma` 现在用同一个读法**（之前图脚本不认项目的键名，直接 FAIL） |
| 4 | G-S4 覆盖矩阵合计 | FAIL：261 ≠ 纳入篇数 2 937 | 矩阵是从 coded.csv 来的，却拿 PRISMA included 对；而 G-S3 明说审计子集可以小于纳入集 | 有 coded.csv 时对 coded 行数；两者不等时只加一句"矩阵只覆盖编码子集，正文要说明" |
| 5 | G-S4 `--verify` | 项目的 `audit_summary.py` 不认 `--verify`，只是重跑并覆盖表，gate 却报"--verify 通过" | 假通过：表是旧的也过，还会把作者的表覆盖掉 | 运行前后对表做快照，逐格比较：变了 → FAIL 并还原；没变 → PASS 但如实写"脚本没有 --verify 开关，重跑代替校验"；不再改作者的文件 |
| 6 | G-S5 κ | 手写 κ 文件格式 `{字段: {kappa, agreement, ci…}}` 被忽略，gate 打印空的 "κ:" 并 PASS | 只认扁平的 `{字段: 数值}` | 两种格式都读；读不到任何数值时 WARN，不再 PASS |
| 7 | G-S5 PABAK 降级 | （模拟数据上发现）κ = −0.02、一致率 96 % 被降为 WARN | 降级只看 PABAK ≥ 0.8；稀有类上两位编码员一个都没对上，高一致率只是主导类撑起来的 | 降级要求 κ > 0；κ ≤ 0 一律 FAIL |
| 8 | G-S5 无边界新颖性 | "a gap is a cell … whose gain has never been measured under missingness" 被报 | `has never been` 无条件触发；这句是定义，不是对领域的断言 | 该短语前面的同一句里有 whose / which / that / if / cell / gap 时不算（"no study has"、"first survey to" 仍照报） |
| 9 | G-S5 引用识别 | 正文用 `[schouten2025navigating]`、`[a2010x, b2018y]` 的 bibkey 引用，带引用段落只数到 4 个（其余看不见） | `CITE` 只认 `[@key]`、`\cite`、`[12]`、et al. | 增加 `[authorYYYYword(, …)]` 形式。引用识别是目录式检测器和"每篇纳入文献被引"的前提 |
| 10 | `summary` | `group_by: L` 的表里行加起来 231，"all" 行 261：30 个 L=? 被静默丢掉 | `group_by` 没显式 `groups` 时排除了 `?` / 空 | 无显式 `groups` 时多加一行 `L?`；显式 `groups` 仍是子集语义。另加 `count(列)` = 该列有已知值的篇数 |
| 11 | `qc-sample` | `--n 100` 但 near-miss 1 226 + random 100 = 1 326 行，没人会盲复核 | near-miss 不设上限 | 新增 `--max-near-miss`，默认等于 `--n`，按 seed 抽，超了打 WARN 并报总命中数 |
| 12 | `survey_figure.py prisma` | 排除理由框空了，没有报错 | `--reasons-pass abstract` 对 `screen_pass` 做精确匹配，项目写的是 `abstract_v1` | 前缀匹配 |
| 13 | PRISMA 图 | "Records removed before screening: duplicates (n = 1816); Other methods (n = 6924)"，读上去像 6 924 条被删 | 滚雪球记录（PRISMA 2020 的 other methods）被放进了"删除"框 | 左上框写 Records identified (n = 31 850)，下分 Databases / Other methods 两臂；"删除"框只写重复 |
| 14 | 时间线图 | x 轴 12 个年份标签粘在一起；最高柱顶到上边框 | 刻度步长 `len//12` 恒为 1；没留 headroom | 按宽度每约 11 mm 一个标签；y 上限留 8 % |
| 15 | rob 图 | 水平条全是同一灰色，图例分不出（用 M/L 的 0–3 等级做的合成用法）；caption 行写"domain with most high-risk ratings: M (0)" | 非评级词的等级都映射到 "unclear" 灰；没有 high 等级也硬报 | 两个以上非评级词的等级各用调色板里的一色，`?`/unclear 仍灰；没有高风险等级时 caption 行如实说"none of the levels … reads as a high-risk rating" |

没有改动的规则（真实数据上无假阳性）：G-S0 scope；协议级的 `check_protocol` 没在本项目跑（项目没有 protocol.md）；目录式段落检测器在 `InfoFusion_review` 2 000 行成稿上 0/49 条合格段落触发，在 `InfoFusion_multimodal` 草稿上 0/4（引用识别修后 0/7）。**这里只能说没有假阳性，没有数据说明真阳性的召回率**（真实稿里没有已知的目录式段落；召回仍只靠夹具里的 mutation 测试）。tensions 台账、报告清单、饱和规则、特征表 / 已有综述表（LaTeX 与 md）按设计工作。

## 图
五张图都目测过：timeline、coverage、bubble、rob、prisma。修前后各看一遍：
- timeline：修后年份每隔一年一个标签，无重叠，最高柱不再贴边。
- coverage：数字、0 格红框、旋转标签正常。
- bubble：气泡面积与色标正常；最小气泡里的数字（1、2）略出圈，可读，没改。
- rob：修后各等级可区分，白字/深字随底色自动切换。
- prisma：修后"Databases / Other methods"分臂，右侧只写重复 1 816；排除框理由为项目的 `abstract_manual (n = 501)`（项目数据问题，见上）。顶部框略高于文字，没改。
- `figures.csv` 的 `inspected` 在副本里仍是 `no`（我没有走"裁图后改 yes"的流程，G5 因此 FAIL，符合设计）。

## 改了哪些文件（均在 feat/survey-upgrade，未提交）
- `scripts/survey_check.py`：`_ndoi`、`prisma_counts` / `load_prisma` / `_eligibility_from_sheet`；`_sources` 重写；种子匹配；κ 读取；tables 的快照校验与 coverage 对 coded 行数；`CITE` / `_unbounded`。
- `scripts/survey_tables.py`：`count(列)`、未知分组行、`--max-near-miss`。
- `scripts/survey_figure.py`：prisma 用共享计数、前缀匹配、两臂框；timeline 刻度与 headroom；rob 颜色与 caption。
- `tests/test_survey_upgrade.py`：新增 13 条回归测试（本文件 36 条全过）。
- 全量：`python -m pytest tests -q -p no:cacheprovider --ignore=tests/pytest-cache-files-3gmdwyoa`（结果见汇报）。

## 没做 / 留给后续
- 本次没在真实数据上跑 `check_protocol`（项目没有 protocol.md）；`survey_search.py`（检索与分诊脚本）也没跑——项目用的是自己的 `lit/*.py`，和第三轮一致。
- PRISMA 的 `screened_abstract` 派生规则假定筛选表的 `screen_pass` 以 `title` 开头代表标题级。别的命名（`ti`、`T1`）要靠显式 `screened_abstract`。
- PABAK 降级现在要求 κ > 0，但仍可能掩盖稀有类上的低一致；κ 与 PABAK 并排写进正文是现有提示，没再加按类别的一致率。
- `tables.yaml` 的 `where` 只支持 `列=值`，没有"不等于 / 包含"；项目里靠 `notes` 文本过滤的写法需要先在项目侧加一列。
- 该项目的真问题（metric / mechanism 取值、`sel_same` 列名、192 行无 ID 的滚雪球垃圾记录、`how_this_differs`、PRISMA 理由是机制不是理由、2 937 对 2 563 的数字）要在项目里修，不是 skill 的事。
