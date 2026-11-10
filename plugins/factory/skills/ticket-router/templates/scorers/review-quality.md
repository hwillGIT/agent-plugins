---
description: Did the reviewers' votes name defects with locations and corrections, and did they find what the diff holds?
agents: [reviewer]
labels:
  - value: actionable
    description: Every changes vote names a file and line, the impact, and what would make it right; no evident defect was missed.
    score: 1
  - value: vague
    description: Findings are real but lack a location or a correction.
    score: 0.5
  - value: empty_or_noise
    description: Approval on a diff with an evident defect, or findings that are only preferences.
    score: 0
passingScore: 1
---
Read the Approval table in `eval.md` and the diff. For each `changes` vote, check that it names a location and a correction. Then read the diff once yourself for the surfaces listed in `reviews` and note any evident defect (a secret, an unhandled error at a boundary, a control without a name, an unbounded query) that no vote mentions. `actionable` when the votes are specific and nothing evident was missed; `vague` when the findings are real but under-specified; `empty_or_noise` when an evident defect went unmentioned or the only findings are preferences. Name what was missed.
