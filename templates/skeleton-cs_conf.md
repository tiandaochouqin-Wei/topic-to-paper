# <Title>

## Abstract
<150–200 words. Problem → limitation of existing methods (one sentence, specific) → what we propose (name it) → key mechanism → headline results on named benchmarks with numbers → code link.>

## 1. Introduction
<≤20 % of body, 5–7 paragraphs. Para 1: task and why it matters. Para 2: what existing methods do and the specific failure (gap_map 失效点, cited; prereg §0 现象), shown in the motivation figure (references/motivation-figures.md). Para 3: why it fails (prereg §0 原因假设) — this is the insight paragraph. Para 4: our approach in one paragraph. Para 5: "Our contributions are summarised as follows:" 3–4 bullets, each = one claims.csv row with its number. Optional teaser figure (Fig. 1) on page 1 showing the failure and the fix.>

## 2. Related Work
<2–3 paragraphs or 2.1–2.3 subsections by theme; each paragraph ends with how our work differs. Covers problem_table rows.>

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
