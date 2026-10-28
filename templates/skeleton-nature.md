# <Title: a declarative sentence or a noun phrase; no "A novel …", no colon-method-name>

## Abstract
<≤150 words, one paragraph, no subheadings, no citations, no abbreviations undefined. Sentence 1–2: the problem and why it matters. 3: what is unknown / what fails. 4: "Here we show …" + the central finding with one number. 5–6: mechanism / generality. 7: implication.>

## Introduction
<No heading in the final PDF; 3–5 paragraphs, ≤600 words. Para 1: field-level importance (gap_map 判定.重要性). Para 2–3: what has been done and precisely where it fails — name the works (gap_map 失效点 原句, cited). Para 4: the unanswered question (prereg §0 现象 + 原因假设). Last paragraph: "Here we show that …" = the paper/argument.md `claim` (templates/argument.md), one sentence, + one sentence of scope; the same sentence is the abstract's sentence 4 and opens the Discussion. Follow argument.md `outline`; name at most 3 prior works individually. No contribution list. No "state-of-the-art".>

## Results

### <Claim-style subheading: a full sentence, e.g. "SRF conditioning transfers zero-shot to an unseen sensor">
<Each Results subsection = one claims.csv row. State the comparison with n, test, p or 95% CI, effect size with units; refer to Fig. 1a–c. Baselines named (prereg §5). 2–4 paragraphs.>

### <Claim 2>
<…>

### <Claim 3: mechanism / control experiments>
<The "ablation" lives here as control experiments; cells within seed noise are stated as not resolvable; the failure-slice finding ("errors concentrate in …; the model's uncertainty predicts them, AUROC …") goes here or in Discussion.>

### <Claim 4: generality / boundary>
<Where it does NOT hold (prereg §8 failure branch, 五维弱项).>

## Discussion
<4–6 paragraphs. 1: restate the central finding in one sentence and what it changes. 2: relation to prior conclusions (which earlier interpretation it supports or overturns, with citations). 3: mechanism — why it works. 4: limitations (每条 prereg §8 / 五维弱项一句). 5: generalisation boundary and what would be needed to extend. 6: implication for practice / next step. No "Conclusion" heading.>

## Methods
<Placed last. Subheadings are noun phrases: Data; Preprocessing; Model; Training; Baselines; Evaluation metrics; Statistics; Reporting summary. Equations allowed here. Every number in Results must be reproducible from this section + SI. Statistics subsection states each test, sidedness, correction, n definition.>

## Data availability
<Where the data are; accession numbers; restrictions.>

## Code availability
<Repository URL + version/DOI.>

## References
<≤70 (Nat Commun) / ≤50 (Nature). Numbered in order of first appearance.>

## Acknowledgements
## Author contributions
## Competing interests

<!-- Supplementary Information: Supplementary Figs./Tables/Notes; Extended Data Figs. (Nature main journal). Main text refers to them as "Supplementary Fig. 1". Full ablation tables and hyperparameters go here. -->
