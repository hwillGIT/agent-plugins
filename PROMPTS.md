# Prompts

Ready to paste. Three places, from most to least help from the tool.

## 1. Claude Code (the plugin installed)

The plugin's skills load on their own when the request matches; the slash form is a shortcut, not a requirement. Any of these works typed as a plain sentence too.

```
/factory setup
/factory build Add a dark mode toggle to settings that remembers the choice
/factory build #42                       (a GitHub issue)
/factory status
/factory review F-001
/factory rework F-001 D-014 is wrong: the preference must follow the user across devices
/factory accept F-001
/factory map the way a support ticket becomes a release today
/factory decide what did we decide about export formats
/factory stats
/factory pause      /factory resume
/factory bug <paste the stack trace>
```

To run only the router on tickets already written: `claude --agent factory:router`, then "run the ready tickets" (add "observe mode" the first time in a repository).

## 2. Codex CLI, Gemini CLI, and other tools that read `~/.agents/skills`

These tools read the SKILL.md files but have no router agent and no parallel subagents, so the prompt names the skill and asks for the panel to be run in turns. Blind positions first, then reconciliation, is what keeps three voices from collapsing into one.

**Write the tickets for a feature**

```
Use the ticket-writing skill in ~/.agents/skills/ticket-writing. Feature request, verbatim:
"<request>"
Create the feature with the script (python3 ~/.agents/skills/ticket-router/scripts/tickets.py feature new ...),
brainstorm it through three lenses — Architect, Skeptic, Advocate — writing each lens's note in full before
reading the next, merge them as the skill says, and write the tickets with tickets.py new --feature F-0xx.
For every open question, run tickets.py precedent first; if nothing covers it, run the panel: three positions
written blind in the panelist format from ~/.agents/skills/ticket-router (do not read a position while writing
another), then an arbiter pass that declares consensus or rules on the reasons, then tickets.py decide and
tickets.py resolve. Leave only an irreversible or outside-the-repository question for me. Mark the tickets ready.
```

**Work one ticket**

```
Use the ticket-router skill's worker role in ~/.agents/skills/ticket-router/agents/worker.md for ticket T-003.
Branch ticket/T-003, change only the paths under owns, run every must-pass row and bash tickets/checks.sh,
save evidence under tickets/T-003/evidence/. A trivial call you make and note; anything larger you stop and
write as a question block. Report in the worker's format.
```

**Accept a ticket**

```
Act as the checker in ~/.agents/skills/ticket-router/agents/checker.md for T-003 from a clean checkout of
ticket/T-003: re-run every row, overwrite the evidence, write the verdict into eval.md. Then, as the reviewer
for each surface in the ticket's reviews list, vote with tickets.py vote. Then run tickets.py verdict T-003
and tell me the word it printed and why.
```

**Review a finished feature**

```
Run python3 ~/.agents/skills/ticket-router/scripts/tickets.py feature summary F-001, then fill the two italic
sections of tickets/features/F-001/summary.md as the summarizer role describes
(~/.agents/skills/ticket-router/agents/summarizer.md). Show me the first two sections and the "what to look at" lines.
```

## 3. ChatGPT (no tools, no files)

Paste the prompt and the material after it. The model plays every role in turn; the format keeps the roles honest.

**Tickets from a request**

```
You will write tickets for the request below using a two-file contract.
rd.md: id, title, kind (code|document|analysis|operations), depends, owns (the only paths the work may change),
deliverable, risk (low|medium|high: high touches auth, payments, migrations, deletion, secrets, permissions,
external posting or personal data), reviews (quality, security; add accessibility and performance for screens;
schema for data; reader for documents); sections Outcome (what the user can do afterwards, no steps),
Context, Constraints, Out of scope, Open questions.
eval.md: numbered rows | # | Check | How to verify (an exact command or action) | Evidence file |, with the
standing rows (tests pass, new behaviour covered, no files outside owns, lint and types clean, merges cleanly),
the standards rows that apply (no secret in the diff; WCAG 2.2 AA and Core Web Vitals for screens; sources and
sections for documents), and three to eight rows for this ticket alone. A row a different person could not run
and get yes or no is not a row.
First, read the request through three lenses one at a time — Architect (structure, interfaces, data flow),
Skeptic (what fails, what is assumed, what is missing), Advocate (the person using it) — and write each lens's
note in full (must be true to count as done; what breaks it; hidden dependencies; checks demanded; questions
only the requester can answer; how to split) before starting the next. Then merge: every risk becomes a
constraint, an out-of-scope line or an eval row; the union of the splits; the Architect's cut wins a dispute.
Then settle each question the lenses raised yourself, by this procedure: write three positions blind, each
in the form Position / Because (cite a standard, a common pattern, or the request's own words) / Reversible /
Cost of being wrong / Would change my mind; then an arbiter paragraph that declares consensus or rules for the
better-cited reasons and records the dissent. Record each as D-001, D-002 … with question, decided, why,
dissent. Leave for me only a question that is irreversible or that only I can know.
Output: the decisions, then each ticket's rd.md and eval.md in full.
Request: <paste>
Material: <paste code, docs or notes>
```

**A decision panel on one question**

```
Settle this question for a software team by a panel. Write three positions blind, in order, each headed by its
lens — Architect, Skeptic, Advocate (use Operator for anything deployed, Guardian for data or compliance,
Strategist for scope) — in the form: Position / Because (2–4 lines, each citing a named standard, a documented
recommendation, or a pattern in the material) / Reversible: yes|no — what undoing takes / Cost of being wrong /
Would change my mind / Should a person decide this instead: no|yes — why. Do not let a later position refer to
an earlier one. Then write the arbiter's ruling: lay the positions side by side; consensus if all agree,
majority with dissent recorded if reversible, otherwise name the disputed facts and give the dissenting lens
one reply that must concede or bring a new argument; then rule for the better-cited reasons or say the matter
should go to a person and why. End with one ledger entry: Question / Options / Decided / Why / Precedent /
Dissent / Reversible.
Question: <paste>
Context: <paste>
```

**Review a summary and write rework lines**

```
Here is a feature summary written by an agent pipeline. Read it as the person who asked for the feature.
List, one line each: the decisions you would overturn and why (name the D- id), the places you would open
before accepting, and anything built that was not asked for. Then write the rework lines in the form
"D-0xx is wrong: <what should be true>" or "<ticket>: <what must change>".
Summary: <paste>
```
