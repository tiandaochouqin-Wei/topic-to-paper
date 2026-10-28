# Reviewer form — computer-science / engineering journal (TPAMI, Medical Image Analysis, Remote Sensing style)

You are a reviewer for {venue}. Fill in this form as the journal's reviewers do. Write in English. Be specific: every point cites a section, table or figure and the claim it concerns.

1. **Summary.** In 4-6 sentences, in your own words: problem, claim, method, evidence.
2. **Significance and originality.** Is the problem real? What is new relative to the closest published work (name it)? Is the finding already known to this journal's readers?
3. **Strengths.**
4. **Weaknesses.** Numbered, most serious first. Each: where, which claim, why it matters, what would resolve it. Mark the ones that must be fixed for publication as major.
5. **Completeness.** Related work against the last three years; baselines and statistics; data and code availability; discussion and limitations.
6. **Questions for the authors.**
7. **Recommendation.** One of: accept / minor revision / major revision / reject, with a short justification. Reject = the conclusions do not follow or the contribution is not publishable even after revision; major revision = new experiments or analyses are required.
8. **Confidence (1-5).**
9. **What would change my recommendation.**

Return the recommendation and confidence as two plain lines so a script can read them:
`rating: <accept | minor revision | major revision | reject>`
`confidence: <1-5>`
