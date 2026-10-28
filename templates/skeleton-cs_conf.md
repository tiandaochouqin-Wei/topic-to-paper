# <Title>

## Abstract
<150–200 words. Problem → limitation of existing methods (one sentence, specific) → what we propose (name it) → key mechanism → headline results on named benchmarks with numbers → code link.>

## 1. Introduction
<≤20 % of body. FOLLOW paper/argument.md `outline` (templates/argument.md), one paragraph per move, in this order: (1) context: the task and why it matters, one paragraph; (2) belief: what current methods assume or do; (3) gap: the failure with the evidence that shows it (gap_map 失效点, prereg §0 现象) — name at most 3 prior works here, the rest belong to Related Work; shown in the motivation figure (references/motivation-figures.md); (4) this paper: what we do, in one paragraph (prereg §0 原因假设 is the insight); (5) finding: the argument.md `claim`, in reader terms — the LAST paragraph before the contribution list repeats that sentence; (6) "Our contributions are summarised as follows:" 3–4 bullets, each ≤ 2 numbers and ≤ 60 words, one claims.csv row each; only the headline claim carries its number here, the other numbers live in Results. Fig. 1 on page 1 is the default (90 % of CVPR and 82 % of ICCV papers have a page-1 figure, references/figure-norms.md): the failure and the fix in one picture. Story changes go into argument.md first, then here.>

## 2. Related Work
<2–3 paragraphs or 2.1–2.3 subsections GROUPED BY THEME, not one sentence per paper. Each paragraph: theme sentence → 2–4 works → how they relate to each other → how we differ. Covers problem_table rows; the works the Introduction named for the gap are named here again with their failure point.>

## 3. Method
### 3.1 Problem formulation / Preliminaries
<Notation, task definition, what is observed at train vs test time (data split, no target labels).>
### 3.2 <Component A>
<One subsection per component that has an ablation row (prereg §6). Equations numbered. Motivation sentence first (prereg §0 原因假设), then mechanism.>
### 3.3 <Component B>
### 3.4 Training objective
<Total loss, hyperparameters' meaning.>

## 4. Experiments
### 4.1 Datasets and metrics
<Named datasets, splits, metric definitions with the inclusion convention stated (prereg §3/§4).>
### 4.2 Implementation details
<Backbone, optimiser, schedule, seeds, hardware; identical for all baselines.>
### 4.3 Comparison with state-of-the-art
<Table: baselines (prereg §5, grouped by family) with best/second-best marked; one sentence per baseline family; relative change vs strongest baseline stated.>
### 4.4 Ablation study
<✓/× table; each row one component; cells within seed noise stated as not resolvable (ablation resolve).>
### 4.5 Analysis
<Failure cases / qualitative grid (make_comparison grid); failure_slice worst slice + does-the-model-know; sensitivity to key hyperparameter.>

## 5. Conclusion
<One paragraph: what was shown, one number, limitation in one sentence, future work in one sentence.>

<!-- NeurIPS/ICML: add "Limitations" paragraph (NeurIPS 72 %) and "Broader impact" (checklist). Appendix: full tables, extra ablations, proofs, hyperparameters. -->

## References
<~40–60.>
