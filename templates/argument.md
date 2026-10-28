---
# paper/argument.md — the paper's argument, written BEFORE the draft (claims.csv + prereg.md -> this file -> outline -> draft).
# Rule: write this first; the draft must follow it; if the story changes, change it HERE first, then the draft.
# argument_check.py (gate G6g) checks that the title, abstract, end of the Introduction and the Conclusion tell this story. Every <angle-bracket> prompt below must be replaced.
#
# Filled example (generic, not from a real project):
#   claim: "Detectors trained on daytime images lose a third of their accuracy at night because their features encode exposure, not shape; normalising exposure recovers 80 % of the loss."
#   reader_question: "Why do detectors that are accurate by day collapse at night, and is it fixable without night labels?"
#   headline: {claim_id: C1, number: "-31 % AP"}
#   why_not_obvious: "The field assumes night failure is a data-scarcity problem and collects night data (Name et al.); nobody tested whether exposure alone explains it."
#   strongest_objection: "Exposure may be confounded with scene type, so the fix could be learning a scene prior rather than removing exposure."
#   where_answered: "§4.3 and Table 2 (exposure-matched day/night pairs)"
#   not_claimed: ["no claim for thermal cameras", "no claim beyond the three benchmarks studied"]
#   outline:
#     - "context: night perception matters for driving and nobody can label it at scale."
#     - "belief: methods treat night failure as scarce data and collect or synthesise night images."
#     - "gap: on exposure-matched pairs the same detector loses 31 % AP, so data volume is not the cause."
#     - "this paper: we remove exposure from the feature path and keep everything else fixed."
#     - "finding: exposure normalisation recovers 80 % of the loss without night labels."
#     - "contributions"
#   sections: {method: "one module removes exposure from the features", experiments: "matched pairs isolate exposure as the cause", discussion: "scope: three benchmarks, no thermal"}

claim: "<ONE sentence, at most 35 words and 2 numbers: what this paper shows, with the measured quantity and its scope; it needs a verb that could be false (shows, lowers, fails, exceeds)>"
reader_question: "<the question a reader of the target venue asks that this paper answers, in the reader's words>"
headline: {claim_id: "<C1>", number: "<the ONE number a reader should remember, exactly as written in the abstract; the claim_id must be a row of paper/claims.csv>"}
why_not_obvious: "<what the field currently assumes / why a reader would not already believe the claim; name the prior belief and who holds it>"
strongest_objection: "<the best reason a reviewer would give to reject the claim>"
where_answered: "<§ / Table / Fig where the paper answers that objection, e.g. §4.3, Table 2>"
not_claimed: ["<a scope limit the paper states explicitly in Limitations>", "<another one>"]
outline:                                   # the Introduction, one entry per paragraph, in order; each = that paragraph's topic sentence ("move: what it says")
  - "context: <why the task matters, one sentence>"
  - "belief: <what current methods assume or do>"
  - "gap: <the failure, with the evidence that shows it; name at most 3 prior works, the rest go to Related Work>"
  - "this paper: <what we do>"
  - "finding: <the claim, in reader terms>"
  - "contributions"                         # cs families: the 3-5 bullets (<= 2 numbers each, <= 60 words). Nature: replace by "finding: Here we show …" (no contribution list)
sections:                                  # one-sentence point of each main section, in order
  method: "<…>"
  experiments: "<…>"
  discussion: "<…>"
---

# Notes (free text, not checked)

Order of work: claims.csv -> this file -> draft. The claim is the sentence the title shortens, the abstract states, the last Introduction paragraph before the contribution list repeats,
and the Conclusion opens with. If you cannot write it in one sentence, the paper is not ready to be drafted: go back to the results.
