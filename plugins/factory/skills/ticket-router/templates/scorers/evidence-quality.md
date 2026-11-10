---
description: Does the evidence prove each must-pass row, or merely assert it?
agents: [worker, checker]
labels:
  - value: proven
    description: Every must-pass row has an evidence file whose content shows the check ran and passed.
    score: 1
  - value: thin
    description: Evidence exists but some files are summaries, truncated, or do not match the row.
    score: 0.5
  - value: asserted
    description: Rows are marked passed with no file that shows it.
    score: 0
passingScore: 1
---
For each must-pass row in `eval.md`, open the named evidence file. `proven` when every file is the actual output of the row's command or action (an exit code, a test runner's output, a screenshot of the state the row names, a recording for a multi-step flow) and the gate file ends in PASS at the merged commit. `thin` when a file is a paraphrase, is cut short, or shows a different state than the row names. `asserted` when a row's file is missing or empty. Name the rows that fell short.
