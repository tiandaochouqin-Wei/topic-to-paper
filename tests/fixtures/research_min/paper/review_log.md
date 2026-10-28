# Review log — round 1 (fixture)

## Reviewer R0 (independent, packet 1a2b3c4d)
Strongest reason to reject: the gain over baseB is small next to the seed spread.
1. [minor] The abstract does not say which platform is held out. category: clarity → 已改: abstract names the held-out platform.
rating: 4
confidence: 3

## Reviewer R1+R3 (independent, packet 1a2b3c4d)
### R1 Methods reviewer
1. [major] The ablation table reports single-run differences; state which cells are within seed noise. → 已改: Section 4.4 now marks two of four cells as not resolvable (Table 2).
   category: evidence
2. [minor] Define RMSE at first use. → 已改: expanded in the abstract.
   category: clarity

## Reviewer R2 (independent, packet 1a2b3c4d)
### R2 Domain reviewer
1. [major] Clarify the contact-window convention used for every table. → 已改: Section 4.1 states the window; Table 1 carries it in the caption.
   category: clarity
2. [minor] Give reproduction details for baseB. → rebut: the official code is unavailable; the re-implementation is described in Section 4.2.
   category: novelty

## Re-review R1+R3 (independent, packet 9f8e7d6c)
- R1-1 closed: Table 2 and Section 4.4 updated.

## Re-review R2 (independent, packet 9f8e7d6c)
- R2-1 closed: convention stated in Section 4.1 and in the Table 1 caption.
