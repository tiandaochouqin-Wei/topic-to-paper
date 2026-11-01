# 图的独立视觉审稿：评分量表与提示模板

`scripts/figure_review.py make` 把每张图渲染成「排进页面后的样子」，连同同角色范文缩略图和下面的量表，交给**一个全新上下文的子代理**审。
审稿人只看到：渲染图、范文缩略图、本量表。看不到主张、预注册、代码、数据、对话。一张图一个子代理。
量表一次只评一张图，七项各 1–5 分；1、3、5 有锚点描述，2 和 4 是两档之间。**阈值是暂定的**（见 gates.md G5）。

返回格式（贴进 `paper/figure_review.md`，标题里的 packet 是 `make` 打印的 sha8）：

    ## Figure review (independent, packet 1a2b3c4d)
    ### Fig 3
    scores: message=4 hierarchy=2 density=3 encoding=4 typography=3 consistency=4 venue=3
    verdict: revise
    - [major] the red/blue methods dominate equally; ours is not the focal element → ours saturated red, others grey, baseline dashed
    - [minor] tick labels 5.2 pt → 6.5 pt

复审（`rereview`）的标题是 `## Figure re-review (independent, packet <sha8>)`，每张图一个 `### Fig N` 块，格式同上。
作者的处置写在 `## Figure dispositions` 节的 `### Fig N` 下（每条意见一行：已改什么 / rebut 的理由），`rereview` 会把它连同原意见交给复审子代理。

**图号**是印刷出来的号：有 `paper/latex/main.tex` 时按 figure 环境在展开后的 .tex 里的先后（只数带 `\caption` 的），并用编译好的 PDF 里的图注和位图所在页核对；`paper/figure_plan.csv` 的 item 号只是兜底，两者不一致时 `make` 打 WARN 并以 LaTeX 顺序为准。范文缩略图按**图文件在计划表里那一行的 role** 取（`files` 列按文件名匹配），与图号无关。

**跨图一致性**（`make` 在 ≥ 2 张图时另写 `prompts/consistency.md`）：一个全新子代理拿到全部图的裁图（真实印刷尺寸）和图注，只回答跨图问题，不评单图好坏，不打分。返回格式（标题里的 packet 同样是 `make` 打印的 sha8）：

    ## Figure consistency (independent, packet 1a2b3c4d)
    verdict: revise
    - [major] Fig 2, Fig 4: ours is red in Fig 2 but blue in Fig 4 → ours red in every figure
    - [minor] panel letters bold in Fig 2, regular in Fig 3 → bold, top-left, in all

有 [major] / `verdict: revise` / OPEN 时，改图、写 `## Figure dispositions` 下的 `### Consistency`，再 `figure_review.py rereview --round N --consistency`（重渲全部图），复审返回贴在 `## Figure consistency re-review (independent, packet <sha8>)` 之下：`verdict: accept` 且无 [major]/OPEN 才关闭（`check` 要求复审 packet 与原 packet 不同、图有变化）。

<!-- template: rubric -->
```
Scoring rubric. Judge ONE figure, as it is printed. Score each criterion 1-5 (2 and 4 sit between the anchors).

1. message - the claim is readable in 5 seconds without the caption.
   1 = you cannot tell what the figure is meant to show, or it shows something else than its title says.
   3 = the claim can be found, but only after reading axis labels and legend line by line.
   5 = the claim is the first thing you see; one glance gives the comparison and its direction.
2. hierarchy - the eye goes to the key comparison first: ours / the effect stands out, secondary elements recede.
   1 = everything has the same weight; the key element is hidden among equals.
   3 = the key element is distinguishable, but other items compete (similar saturation, similar line weight).
   5 = ours / the effect is the only strongly coloured or heavy element; baselines, grids and reference lines recede.
3. density - no panel or element that does not serve the message; whitespace; no clutter.
   1 = panels or series that serve no visible purpose, crowded labels, nothing has room.
   3 = one or two superfluous elements, or tight but legible spacing.
   5 = every element earns its place; margins and spacing are even; nothing could be removed without losing the message.
4. encoding - the chart type fits the data; colour has meaning and is consistent; colour-blind safe.
   1 = wrong chart type for the data (for example lines between unrelated categories), a rainbow colour map for categories, colours that carry no meaning, or a truncated axis that misleads.
   3 = the type is acceptable but a better one exists, or the palette is partly arbitrary, or two series differ only by hue that colour-blind readers cannot separate.
   5 = the type is the natural one for this comparison; each colour or marker means one thing; redundant coding (marker or line style) survives grayscale; a rainbow appears only as a quantity map with a colour bar.
5. typography - at least 6 pt when printed, one font family, consistent sizes, no overlaps, plain-word labels.
   1 = text under 5 pt printed, overlapping labels or clipped text, or code names or variable names (snake_case, column names, L_rel, F6R, out0, params_M) as labels.
   3 = readable, but sizes differ between panels, or a few labels are tight or abbreviated.
   5 = all text 6 pt or larger at the printed size, the same sizes for the same roles, no collisions, labels in plain words with units.
6. consistency - the same method has the same colour and marker across all figures of the paper; panel letters and axis ranges are comparable.
   1 = the same method changes colour or marker inside this figure, or panels that should be compared have different, unmarked axis ranges.
   3 = consistent inside the figure; consistency with the other figures cannot be judged or is partly broken.
   5 = colours, markers, panel letters and axis conventions are identical for the same things, inside the figure and (as far as the pages show) across the paper.
7. venue fit - compared with the exemplar figures of the same role: would it look out of place in the target venue?
   1 = clearly amateur or off-genre next to the exemplars (screen-capture look, default plotting style, wrong size or aspect for the venue).
   3 = acceptable, a little plainer or busier than the exemplars.
   5 = it could be swapped into an exemplar paper without anyone noticing.
   If no exemplars are given, judge from your general knowledge of the venue and say so in one line.

Items. Besides the scores, list what to change, one line each, in this exact format:
   - [major] <what is wrong> -> <concrete change>
   - [minor] <what is wrong> -> <concrete change>
A change is concrete when someone can do it without asking you: "drop panel (c), it repeats Table 2", "ours red, all others light grey", "raise tick labels to 6.5 pt".
[major] = any criterion you scored 1 or 2, or anything that misleads a reader. [minor] = polish. Give no praise padding and no item without a change.
Verdict: accept = nothing major and you would let it go to print; revise = anything else.
```
<!-- template: figure -->
```
You are an independent figure reviewer for {venue}. You have never seen this paper or project. You have only the images named below and the rubric. Do not open any other file, do not look for the authors' notes, and do not ask the authors anything.

You must open every image below with the Read tool before you score. Judge the figure as printed: the crop is rendered at true print size (300 dpi, {width_note}), so text that looks small in the crop is small on paper.

Figure {number} ({mode_note})
{fig_images}

Exemplar figures of the same role in recent papers of this kind (the yardstick for the "venue fit" criterion):
{exemplar_images}

{common}

How to return
- Your final message is the review and nothing else; do not write files.
- Begin it with exactly this line: ## Figure review (independent, packet {packet_sha})
- Then the heading line: ### Fig {number}
- Then exactly these lines: "scores: message=N hierarchy=N density=N encoding=N typography=N consistency=N venue=N" and "verdict: accept" or "verdict: revise", then the items.
```
<!-- template: rereview -->
```
You are an independent figure reviewer for {venue}. You have never seen this paper or project. You have only the images named below, the earlier review items for this figure, the author's dispositions, and the rubric. Do not open any other file and do not ask the authors anything.

You must open every image below with the Read tool before you score. The figure was revised; judge the revised version as printed (the crop is rendered at true print size, 300 dpi, {width_note}).

Figure {number} - revised ({mode_note})
{fig_images}

Exemplar figures of the same role (the yardstick for the "venue fit" criterion):
{exemplar_images}

Earlier review items for this figure:
{items}

The author's dispositions:
{dispositions}

Score the revised figure afresh on all seven criteria, and mark every earlier item "closed" (the change is visible in the revised figure and the problem is gone) or "OPEN" (not done, only reworded, or the figure now has a new problem of the same kind). A disposition that argues instead of changing the figure does not close an item; say what you see.

{common}

How to return
- Your final message is the review and nothing else; do not write files.
- Begin it with exactly this line: ## Figure re-review (independent, packet {packet_sha})
- Then the heading line: ### Fig {number}
- Then "scores: ...", "verdict: accept" or "verdict: revise", then one line per earlier item ("- closed: <item>" or "- OPEN: <item> -> <what is still wrong>"), then any new items in the format above.
```
<!-- template: consistency -->
```
You are an independent reviewer of cross-figure consistency for {venue}. You have never seen this paper or project. You have only the images and captions below. Do not open any other file, do not look for the authors' notes, and do not ask the authors anything.

The paper has {n_figs} figures. Each is shown as a crop at true print size (300 dpi), so text that looks small in a crop is small on paper. You must open every image with the Read tool before you answer; compare the figures with each other, not with an ideal.

{fig_blocks}

Answer ONLY these cross-figure questions. Do not judge the message, composition or beauty of any single figure and give no scores.
1. Methods. Does each method keep the same colour, the same marker and the same line style in every figure and in every caption that refers to it? Does it carry the same NAME in every figure (legend, axis, panel title) and in the captions - not "ours" in one place, a model name in another, an abbreviation in a third?
2. Fonts. Is there one font family across all figures? Is the same role (axis label, tick label, legend, panel letter, annotation) set at the same size?
3. Panels and axes. Are panel letters written the same way and put in the same place? Does the same quantity have the same axis label, unit and direction (is "better" up or down the same way), and are comparable panels on comparable axis ranges?
4. Plain words. Is any label, legend entry, title or tick label a code name or variable name instead of plain words with units (snake_case, L_rel, F6R, out0, params_M, column names, file names)? Name each one and the figure it is in.

Items. List what to change, one line each, in this exact format, and name the figures involved:
   - [major] <Fig N, Fig M: what differs> -> <concrete change>
   - [minor] <Fig N: what differs> -> <concrete change>
[major] = a reader could misidentify a method or compare two quantities wrongly, or a code name is printed as a label. [minor] = polish. A change is concrete when someone can do it without asking you: "ours red (#C0392B) in Fig 2 and Fig 4", "rename F6R to 'RelRoute (ours)' in Fig 3's legend". Give no praise padding and no item without a change.
Verdict: accept = nothing major; revise = anything else.

How to return
- Your final message is the review and nothing else; do not write files.
- Begin it with exactly this line: ## Figure consistency (independent, packet {packet_sha})
- Then the line "verdict: accept" or "verdict: revise", then the items. No scores.
```
<!-- template: consistency_rereview -->
```
You are an independent reviewer of cross-figure consistency for {venue}. You have never seen this paper or project. You have only the images and captions below, the earlier consistency items, and the author's dispositions. Do not open any other file and do not ask the authors anything.

The paper has {n_figs} figures, revised after an earlier consistency review. Each is shown as a crop at true print size (300 dpi). You must open every image with the Read tool before you answer.

{fig_blocks}

Earlier consistency items:
{items}

The author's dispositions:
{dispositions}

Re-check the cross-figure questions on the revised figures: (1) the same method keeps the same colour, marker, line style and NAME in every figure and caption; (2) one font family and the same size for the same role; (3) panel letters, axis labels, units, direction and ranges are handled the same way; (4) no code names or variable names (snake_case, L_rel, F6R, out0, params_M) as labels. Do not judge any single figure's composition and give no scores.

Mark every earlier item "closed" (the change is visible in the revised figures and the problem is gone) or "OPEN" (not done, only reworded, or now broken in another figure). A disposition that argues instead of changing the figures does not close an item; say what you see. Then list any new items in this format:
   - [major] <Fig N, Fig M: what differs> -> <concrete change>
   - [minor] <Fig N: what differs> -> <concrete change>
Verdict: accept = nothing major and nothing OPEN; revise = anything else.

How to return
- Your final message is the review and nothing else; do not write files.
- Begin it with exactly this line: ## Figure consistency re-review (independent, packet {packet_sha})
- Then the line "verdict: accept" or "verdict: revise", then one line per earlier item ("- closed: <item>" or "- OPEN: <item> -> <what is still wrong>"), then any new items.
```
