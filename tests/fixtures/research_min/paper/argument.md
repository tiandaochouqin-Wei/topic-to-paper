---
claim: "Cross-platform degradation of vision-based force estimation is dominated by a label-side sensor offset; removing it with a domain-adversarial regularizer lowers held-out RMSE by 19.2% against the strongest baseline."
reader_question: "Why do vision-based force regressors degrade on another robot platform, and can the degradation be removed without target labels?"
headline: {claim_id: C1, number: "19.2%"}
why_not_obvious: "Visual domain adaptation assumes the shift lives in the image statistics, and force-sensing work (GeoNet) assumes a shared sensor calibration; nobody tested the label-side assumption."
strongest_objection: "Only two robot platforms were studied, so the offset account might not hold on a third platform."
where_answered: "§4.6 and Table 2"
not_claimed:
  - "no claim about the consistency term, which is not resolvable at the present seed budget"
  - "a third platform remains future validation"
outline:
  - "context: transferring force estimation across robot platforms matters because recalibrating the sensor on every platform is impractical, and existing vision-based regressors report strong in-platform accuracy"
  - "gap: GeoNet and ForceFormer inherit the platform offset, and visual domain adaptation never tested the label-side assumption"
  - "finding: GeoNet-style regressors degrade on the other platform with a near-constant offset, and a domain-adversarial regularizer removes it, lowering RMSE by 19.2%"
  - "contributions"
sections:
  method: "one regularizer behind the prediction head removes the offset"
  experiments: "two platforms, three seeds, one-factor ablations with explicit seed-noise resolution"
  discussion: "two platforms only; the consistency term is not resolvable"
---

# Notes

Fixture argument for tests/test_argument.py: every field is satisfied by paper/manuscript.md.
