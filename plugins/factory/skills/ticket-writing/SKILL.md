---
name: ticket-writing
description: Writes a ticket before work starts: a requirements file plus a checkable acceptance file with owned paths, dependencies, risk, reviews and standards rows. Use to write or break down tickets.
---

# Ticket writing

A ticket is a contract between the person who wants something and the agent that will build it. It has two files, kept in `tickets/<id>/`: `rd.md` says what must exist when the work is done and where the work may happen; `eval.md` says how anyone can prove it, with the command or action for each check and the file of evidence it leaves behind. A ticket that cannot be checked is not ready, whoever is going to do the work.

Tickets serve code, documents, analyses and operations alike. For a report or a plan, the deliverable is a file and the checks read it as its audience would. Tickets that come from one request are grouped under a feature (`tickets/features/F-0xx/feature.md`: the request verbatim, the outcome, the end-to-end definition of done, the ticket list); the feature is what the person reviews when the tickets are done, and a rework note on it becomes a new ticket by `tickets.py rework`.

## Before writing

Read what exists: the code or documents the ticket touches, `tickets/DECISIONS.md` for questions already answered, and any plan or spec the ticket comes from. Then pick the front door that fits the size of the request. All three end in the same files.

| Size of the request | Front door |
|---|---|
| One ticket under about 30 minutes, or a bug | Write it directly (sections below) |
| A feature of two to eight tickets, code or business | **Brainstorm with lenses** (next section), then write |
| A large or contested feature, or one that needs a requirements document the team will sign | Run `/agentic-council:council` first; its requirements document and acceptance contract become the source. Each user story becomes one ticket, and the contract's method and evidence columns move into `eval.md` rows as they stand |
| A code feature inside an existing codebase that needs exploring first | Run `/feature-dev` or `/agentic-sdlc:sdlc-start` intake first; its plan or task list becomes the source. "Files Expected" becomes `owns`, "Depends on" becomes `depends`, the test plan seeds `eval.md` |

Whichever door, the questions the material cannot answer do not go to the person first. Run `tickets.py precedent "<words>"` against `tickets/DECISIONS.md`; what precedent covers is followed and cited. What it does not cover goes to the decision panel (the ticket-router skill, section 3): three lenses argue it blind, the arbiter records the verdict, and the ticket cites it. Only a question on the `always_escalate` list in `tickets/CONFIG.md` — a step that cannot be undone, a reversal of a person's decision, a matter only they can know such as a budget or a name that must appear — stays in Open questions for a person. Everything else gets a stated default and a line in Context saying so.

## Brainstorm with lenses

Three or four agents read the same request, each through one lens, in parallel. They do not talk to each other; the lead merges their notes. Use the council's installed lens agents when present (`agentic-council:Strategist`, `Architect`, `Skeptic`, `Advocate`, `Operator`, `Guardian`, and the finance and revenue lenses); otherwise spawn the generic `lens` role from the ticket-router kit with the lens named in its prompt.

Pick the lenses by the ticket's kind:

| Kind | Lenses | Add when |
|---|---|---|
| code | Architect, Skeptic, Advocate | Operator if it touches deployment, infrastructure or data stores; Guardian if it touches personal data, auth or compliance |
| document or analysis | Strategist, Skeptic, one domain lens (Capital or FP&A for finance, Herald for growth and marketing, Guardian for compliance, Controller for accounting) | Advocate when the reader is a customer |
| operations | Operator, Guardian, Skeptic | Treasurer or Controller when money moves |

Each lens gets the request, the relevant files, and `DECISIONS.md`, and returns this note and nothing else:

```
Lens: <name>
Must be true for this to count as done: 3 to 6 lines
What breaks it: 3 to 5 risks, each with where it would show up
Hidden dependencies: what this needs from code, data, people or decisions that the request does not mention
Checks I would demand: eval.md rows, each with the command or action that proves it
Questions only the person can answer: at most 2
Split: the tickets I would cut, with the paths each owns, or "one ticket"
```

The lead then:

1. Merges the "must be true" lines into the outcome, dropping duplicates and keeping each lens's wording where it is sharper.
2. Turns every risk into a constraint, an out-of-scope line, or an `eval.md` row. A risk that becomes none of these is dropped and said so.
3. Takes the union of the splits. Where lenses disagree on the cut, the Architect's cut wins for code and the Strategist's for business, and the disagreement goes into the ticket's context so the worker knows it.
4. Collects the questions, removes any already answered in `DECISIONS.md`, sends the rest to the panel, and leaves in Open questions only those on the `always_escalate` list.
5. Writes the tickets. Every check a lens demanded appears in some ticket's `eval.md` or is named in the context as deliberately left out.

Cap it at four lenses and one round. A brainstorm that wants a second round is a sign the feature is large enough for the council.

## Writing `rd.md`

Create the folder with `python3 tickets/tickets.py new "<title>" --kind <code|document|analysis|operations> --owns <paths> --deliverable <path>` when the script is present, or copy the template below. Then fill the sections:

- **Outcome.** One paragraph from the user's or reader's side: what they can do, see or know once the ticket is done. No steps, no technology choices.
- **Context the worker needs.** Where the relevant code or material lives, how it is run today, conventions to follow, decisions already made with their dates.
- **Constraints.** Public interfaces and data formats that must not change; files outside `owns` that must not be touched; anything that needs a person before it happens.
- **Out of scope.** The adjacent things a reasonable worker would assume are included and are not.
- **Open questions.** One concrete question per line, or `None.` A ticket with an open question stays in draft.

And the header fields:

| Field | Rule |
|---|---|
| `kind` | code, document, analysis or operations. It decides which checks `eval.md` carries. |
| `mode` | `solo` for one worker. `team` when several workers build adjacent parts; a team ticket needs a contract ticket first (below). |
| `depends` | Ticket ids that must be done first. Keep the graph acyclic; the script refuses cycles. |
| `owns` | Every file and folder the work may change, and nothing else. Two tickets with overlapping paths never run at once. Narrow is better than broad. |
| `deliverable` | The output a reader opens: a code folder, or a file such as `deliverables/q3-plan.md`. |
| `budget.minutes` | How long one worker should need. Over 60 means the ticket should split. |
| `budget.interventions` | How many questions the worker may send before the router stops the ticket. Usually 1. |
| `risk` | `high` when `owns` touches auth, payments, migrations, deletion, secrets, permissions, external posting or personal data; `medium` when it touches a public interface, a data format or a shared component; else `low`. Risk picks the approval rule (checker only / majority / unanimous) and the panel size for its questions. A high-risk ticket says in Constraints where it stops for a person. |
| `reviews` | The surfaces a reviewer votes on after the checker: from `reviews_by_surface` in `tickets/CONFIG.md`. `quality, security` for code; add `accessibility, performance` when a template, component or stylesheet is in `owns`; `schema` when a migration or query is; `reader` when the deliverable is a document. |
| `feature` | The `F-0xx` this ticket belongs to, when it comes from a feature request. `tickets.py new --feature F-0xx` sets it and adds the ticket to the feature file. |

## Writing `eval.md`

Every row names a check, the exact command or action that verifies it, and the evidence file it leaves in `tickets/<id>/evidence/`. The test of a row: could a different agent, who never saw the work, run this line and get a yes or no? If the answer needs judgement, write what the judge looks for and what they save.

Keep the standing rows (tests pass, lint clean, diff within `owns`, branch merges cleanly), add the screen rows when a screen changes, add the document rows when the deliverable is a file, and then add the rows that belong to this ticket alone: the specific behaviour, number, page or section the outcome promises. Three to eight ticket-specific rows is the usual range. A row the worker cannot run from the repository is a sign the ticket needs material from the person.

The standards rows are not optional where they apply: the secrets and dependency rows for every code ticket, the WCAG 2.2 AA and Core Web Vitals rows for every ticket that changes a screen, the source and section rows for every document. They are what the reviewers vote on; a ticket without them has nothing for a reviewer to check against.

For a code ticket, write the tests at spec time: on a branch `spec/<id>` from the integration branch, add the failing tests that encode the outcome, and point rows 2 and 8 at them. The worker starts from that branch and the gate turns green when the outcome exists. A test written before the code is the only acceptance row no worker can argue with.

The "must not happen" list stays as written. It names the actions that are never automated.

## Sizing and splitting

A ticket fits one worker's context and one sitting: one deliverable, one branch, 20 to 60 minutes. Split when the outcome has an "and", when two different readers are served, when `owns` spans unrelated parts of the tree, or when the budget passes 60 minutes.

For a feature that needs several workers, write the **contract ticket** first: the interfaces, types, API shapes or document outline the others build against, small enough to finish in 20 minutes. Every other ticket in the group lists it in `depends`. Without it, workers diverge and the merger inherits the design work.

## From a bug

A bug ticket starts with its reproduction: the first "must pass" row is the failing test or the recorded steps going green. If no one has reproduced it yet, the ticket is for the reproduction, and the fix is a second ticket that depends on it.

## Marking ready

Run `tickets.py ready <id>` (the script lives in the ticket-router skill's `scripts/` folder; in the plugin, `${CLAUDE_PLUGIN_ROOT}/skills/ticket-router/scripts/tickets.py`). It refuses a ticket with open questions, an empty `owns` or one that includes `tickets/`, an unknown dependency or feature, a dependency cycle, or an `eval.md` row without a verification or evidence file. An open question is cleared by a decision: `tickets.py decide … ` then `tickets.py resolve <id> --decision D-0xx`. Without the script, check the same list by hand and set `status: ready` in the header.

## Template: `rd.md`

```markdown
---
id: T-001
title: Short name of the deliverable
status: draft
feature:
kind: code
mode: solo
depends: []
owns:
  - src/feature/
  - tests/feature/
deliverable: src/feature/
reviews: [quality]
budget:
  minutes: 45
  interventions: 1
risk: low
pr:
---

# T-001 Short name of the deliverable

## Outcome
## Context the worker needs
## Constraints
## Out of scope
## Open questions
None.
```

## Template: `eval.md`

```markdown
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
```
