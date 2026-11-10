---
description: Did the ticket deliver what the request asked for, and only that?
agents: [worker]
labels:
  - value: compliant
    description: The diff delivers the ticket's Outcome, inside its owns, and nothing else.
    score: 1
  - value: partial
    description: Part of the Outcome, or unrequested scope added.
    score: 0.5
  - value: non_compliant
    description: The Outcome is not delivered.
    score: 0
passingScore: 1
---
Read `rd.md` (the Outcome and Out of scope), the feature's Request, the diff of the merge commit titled `<id>:` on the integration branch, and the evidence folder. Do not read the worker's report, notes.md or the summary: judge the work, not its account of itself. `compliant` when the diff does what the Outcome says, inside `owns`, with nothing added that the request did not ask for; `partial` when it does part of it or adds scope; otherwise `non_compliant`. Name the file and line that decided it.
