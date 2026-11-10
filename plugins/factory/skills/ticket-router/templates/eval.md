# T-001 Acceptance

Every item names the command, file or action that proves it, and the evidence the checker saves in `tickets/T-001/evidence/`. A worker's statement that an item passed is not evidence. Rows 1–5 are run by the gate (`tickets.py gate`) before any model looks at the work.

## Must pass
| # | Check | How to verify | Evidence file |
|---|---|---|---|
| 1 | Existing tests still pass | `npm test` exits 0 (or the project's runner in `tickets/checks.sh`) | `evidence/gate.txt` |
| 2 | New behaviour works | `npm test -- feature.spec` exits 0 and covers the outcome | `evidence/tests.txt` |
| 3 | No files changed outside `owns` | `git diff --name-only integration...HEAD` lists only paths under `owns` | `evidence/diff-files.txt` |
| 4 | Lint, type checks and build clean | `tickets/checks.sh` exits 0 | `evidence/gate.txt` |
| 5 | Branch merges cleanly | `git merge --no-commit --no-ff integration` reports no conflicts, then abort | `evidence/merge-check.txt` |

## Must pass for code (standards built in)
| 6 | No secret or credential in the diff | `tickets/checks.sh` secrets step passes; reviewer `security` finds no key, token or password | `evidence/gate.txt` |
| 7 | New dependencies are justified | Each added package is named in rd.md Context with why; none is unmaintained or duplicates one already present | `evidence/deps.md` |

## Must pass when the ticket touches a screen
| 8 | The screen does what the outcome says | Open the page, perform the action, save before and after screenshots | `evidence/before.png`, `evidence/after.png` |
| 9 | No console errors | Browser console empty of errors after the action | `evidence/console.txt` |
| 10 | Accessible at WCAG 2.2 AA | Keyboard-only pass of the flow; contrast and labels checked in the browser (axe or the installed accessibility auditor) with zero serious findings | `evidence/a11y.md` |
| 11 | Core Web Vitals within budget | Lighthouse or the browser's performance panel on the changed page: LCP ≤ 2.5 s, CLS ≤ 0.1, INP ≤ 200 ms on a throttled run | `evidence/perf.md` |

## Must pass when the ticket produces a document or analysis
| 12 | The deliverable exists at its path and opens | `ls -l <deliverable>`; open it | `evidence/deliverable.txt` |
| 13 | It answers the outcome for its named reader | Checker reads it as that reader; notes any promised question left open | `evidence/read-through.md` |
| 14 | Every figure ties to a source | Each number, date or quote has a source the checker can open | `evidence/sources.md` |
| 15 | Required sections are present | The headings rd.md names appear, in order, with content | `evidence/sections.txt` |

## Must not happen
- No push to `main`, no deploy, no migration run, no data deleted, no message posted outside the repo, no permission changed. If any of these is needed, the ticket stops and a person does it.

## Checker's verdict
- Verdict: accepted | returned
- Returned because:
- Checked by:

## Approval
| Role | Verdict | Why | When |
|---|---|---|---|
