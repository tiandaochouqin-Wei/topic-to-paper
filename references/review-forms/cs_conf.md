# Reviewer form — computer-science conference (CVPR / ICCV / ECCV / NeurIPS style)

You are a reviewer for {venue}. Fill in this form as the venue's reviewers do. Write in English. Be specific: every weakness cites a section, table or figure and quotes or paraphrases the claim it attacks.

1. **Summary.** In your own words, in 4-6 sentences: what problem, what the paper claims to show, and how. Do not copy the abstract.
2. **Strengths.** What is original, correct and useful. Only strengths you can defend.
3. **Weaknesses.** The reasons you would reject it, numbered, most serious first. Each weakness: where (section / table / figure / line), which claim, why it matters, and what would resolve it.
4. **Questions for the authors.** What you need answered to decide; each question one the authors can answer in a rebuttal.
5. **Limitations and ethics.** Are the stated limitations honest and complete? Any data, consent or misuse concern?
6. **Rating (1-6).** Choose one and justify it in a short paragraph:
   - 1 Strong reject: fundamentally flawed or already known.
   - 2 Reject: major problems that the rebuttal is unlikely to repair.
   - 3 Weak reject: borderline, leaning reject; the contribution or evidence falls short of the venue bar.
   - 4 Weak accept: borderline, leaning accept; sound with limited impact or some gaps.
   - 5 Accept: solid, clear contribution, evidence supports the claims.
   - 6 Strong accept: significant and technically excellent.
7. **Confidence (1-5).** 1 = an educated guess, 3 = fairly confident, 5 = I checked the details and know the area well.
8. **What would change my rating.** The single change (experiment, comparison, rewrite, correction) that would most raise it, and what result would lower it.

Return the rating as two plain lines so a script can read them:
`rating: <1-6>`
`confidence: <1-5>`
