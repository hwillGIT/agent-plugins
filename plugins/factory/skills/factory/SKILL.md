---
name: factory
description: The one front door for the ticket factory. Say it in plain words — build a feature, status, review F-001, rework F-001, map a process, setup — and it routes to the right skill, role and script.
argument-hint: build <feature> | status | review F-001 | rework F-001 <note> | map <process> | setup | stats | pause | resume
---

# Factory

Everything in the ticket factory is reached from here, in plain words. Nobody needs to remember a role name or a script command; this skill reads the request, picks the path, and runs it. Script: `${CLAUDE_PLUGIN_ROOT}/skills/ticket-router/scripts/tickets.py` (`T`). The three skills behind this one — `ticket-writing`, `ticket-router`, `outcome-map` — hold the detail; load the one the path names before acting.

The request is `$ARGUMENTS`. Read it, match the first row that fits, confirm in one line what you are about to do, and do it.

| The person says (any wording) | What happens |
|---|---|
| **setup**, "set this repo up", first use in a repository without `tickets/` | `T init`; open `tickets/CONFIG.md` and `tickets/checks.sh`, fit `checks.sh` to the project's lint, type check, tests and build (read `package.json`, `pyproject.toml`, `justfile`, `Makefile`); create the integration branch from `main` if missing; commit `tickets/` (it now includes `scorers/`, `SCORES.md`, `BENCH.md`). Then say what `promote` is set to, that `price_per_million_tokens` turns token counts into money, and offer `setup --github`. |
| **build …**, "make …", "add …", "I want …", a pasted issue link or `#42` | A feature. `T feature new "<title>" --request "<verbatim>"` (or `T import-issue 42`), then spawn `factory:intake` with the feature id. When it reports, start the router: spawn `factory:router` with "run F-0xx" — in observe mode if this repository has never run one. Tell the person the feature id and that they will hear back when the summary is ready. |
| **run**, "run the tickets", "start", "go" | Spawn `factory:router` with the ready tickets or the named feature. |
| **status**, "board", "where are we", "what's running" | `T board` and `T feature list`; answer in a few lines from the board: what is running, what is waiting on a person, what is in review. `T dashboard` when they want a page. |
| **review F-001**, "what did it build", "show me the summary" | Open `tickets/features/F-001/summary.md` (write it first with `T feature summary F-001` if missing or stale). Give the person the first two sections and the "what to look at" lines; offer to open any evidence file or screen. |
| **rework F-001 …**, "that's wrong", "change …", "D-014 should be …", lines written in `review.md` | For each note: `T rework F-001 --note "<their words>" [--overrides D-0xx]` — the id when the note names or plainly contradicts a decision. Then spawn `factory:router` to run the rework tickets. The person's note is the precedent now; say so in one line. |
| **accept F-001**, "ship it", "looks good" | `T feature status F-001 accepted`. If `promote` is `pr`, remind them the pull request is theirs to merge; `local`, merge the integration branch into `main` locally; `auto` is already done. |
| **ticket …**, "write a ticket for …", "one ticket" | The `ticket-writing` skill directly: a single ticket, no feature, then `T ready`. |
| **map …**, "how should this process work", "before we automate …" | The `outcome-map` skill: current-state map, outcomes, AI does / person does / person decides, one card per agent, measures, rollout. |
| **decide …**, "what did we decide about …", "why did it choose …" | `T precedent "<words>"`; read the entries aloud with their reasons and dissent. |
| **stats**, "is this worth it", "how are we doing", "what does it cost" | `T stats`; the override share is the line to read first, then cost per merged ticket and the score pass rates. |
| **score**, "grade the last runs", "run the judges" | `T sample`, then one `factory:scorer` per listed ticket and scorer; report the pass rates and what failed. |
| **improve**, "what should we change", "factory engineering" | Spawn `factory:improver`; it proposes at most one change as a feature with counts. Tell the person the pattern and the feature id, and that it runs through the normal pipeline. |
| **bench …**, "which model should we use", "compare models" | `T bench add` for the done tickets named (or the three smallest, three medium and two largest by budget when none are), then for each model named spawn a `factory:worker` from the task's base commit with that model, gate and check it, and `T bench record`. Report rows passed against minutes and tokens per model. |
| **setup --github**, "run it from GitHub", "automate intake" | Copy `${CLAUDE_PLUGIN_ROOT}/skills/ticket-router/templates/github/factory.yml` to `.github/workflows/factory.yml`, say which secret the repository needs (`ANTHROPIC_API_KEY`), which labels trigger it (`factory-ready`), that `@factory` in a comment reaches it, and that a person still merges. Never add the secret yourself. |
| **pause** / **resume** | Set `paused` in `tickets/CONFIG.md`; running tickets finish, nothing new starts. |
| **bug …**, "this is broken", a stack trace | Spawn `factory:reproducer`; it returns a failing test and a draft ticket. |
| **help**, anything that fits no row | List these rows in the person's words, with one example each. |

## Rules this door keeps

- A feature request is taken as written: the request goes verbatim into `feature.md`, and the intake decides, researches and decomposes without asking the person for what the repository, the web or the ledger can answer. Only a question on the `always_escalate` list in `CONFIG.md` reaches them.
- The person's words in a rework note are kept verbatim in the ticket and the ledger.
- Nothing here pushes to `main`, deploys, migrates, deletes data, posts outside the repository or changes permissions. Those are the person's, from their own terminal.
- When the plugin's agents are not available (outside Claude Code), say so and fall back to doing the intake and the ticket writing in this session, with the panel run as turns — blind positions written before any reconciliation.
