# factory

An autonomous ticket pipeline. You say what to build; the intake writes the feature and its tickets; workers build them on their own branches; when a worker meets a question, a panel of agents argues it out against the ledger of past decisions, the repository's own patterns and named standards, and writes the verdict down; a deterministic gate, a checker and reviewers accept by a rule tied to risk; a merger lands each ticket; and you get a summary sorted by what is most likely to need rework. Anything you disagree with becomes a rework ticket whose decision outranks the panel's from then on. The one front door is `/factory`.

```
/factory setup                      first use in a repository: tickets/, CONFIG.md, checks.sh
/factory build dark mode toggle     a feature, end to end; you hear back when the summary is ready
/factory status                     the board
/factory review F-001               the summary: decisions without precedent first, then dissent, then what to look at
/factory rework F-001 D-014 is wrong: exports stay CSV
/factory accept F-001
/factory map our release process    redesign a process before adding agents to it
/factory stats                      throughput, first-pass rate, and the share of panel decisions you overrode
```

What never happens without a person: a push to `main`, a deploy, a migration, deleting data, money, posting outside the repository, changing permissions. A hook enforces it in any repository that has `tickets/CONFIG.md`.

Install: `claude plugin marketplace add hwillGIT/agent-plugins` then `claude plugin install factory@hwillgit`. The full README, PROMPTS.md and the marketplace catalog are in the repository root.
