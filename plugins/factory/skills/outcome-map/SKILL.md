---
name: outcome-map
description: Redesigns a process before agents join it: maps steps and hand-offs, restates them as outcomes, splits each into AI does / person does / person decides, one card per agent, measures.
---

# Outcome map

Putting agents into a process as it stands automates the hand-offs along with the work, and the waiting between them survives. This skill redraws the process first — the Levi's order: process, then platform, then people — so the agents that follow have a seat in a process designed for them. It fits software delivery, document production, finance close, support, any work that moves through roles. The output is one file, `outcome-map.md`, that the `ticket-writing` and `ticket-router` skills can build from.

## 1. Map the current state

Interview the material, not the person first: the runbooks, the tickets of the last month, the chat threads, the calendar. Then confirm with the person in one message. Produce a table with one row per step:

| # | Step | Who does it | Hands off to | Waits for | Typical wait | Decision made here? |

Count three things at the end: steps, hand-offs between roles, and total waiting time against total working time. The counts go at the top of the map; they are what the redesign is measured against. The Levi's team found twelve hand-offs and six roles in a flow whose working time was a fraction of its calendar time; most processes look like that once drawn.

## 2. Restate steps as outcomes

A step says what someone does ("QA tests the build"); an outcome says what is true afterwards ("every change is proven against its acceptance rows before anyone reviews it"). Rewrite the step list as an outcome list, merging steps that exist only to hand work along. The number of outcomes is usually a third of the number of steps. For each outcome, name who it is for: the user, the reader, the auditor, the next team.

## 3. Split each outcome three ways

For every outcome, three columns, filled from the person's answers and the pattern in the deck of work:

| Outcome | AI does | A person does | A person decides |

- **AI does**: the work with a checkable result — draft, test, review against a standard, measure, compare to precedent, summarise.
- **A person does**: what needs a body or a credential — approve a payment, talk to a customer, press deploy.
- **A person decides**: only what cannot be settled by research, precedent or a panel of agents arguing it out: taste the organisation has not expressed yet, trade-offs with money or people on both sides, anything irreversible. The default for a decision is the agents' panel with the person reviewing afterwards; a decision moves to this column when the person says it should, and moves back out once the ledger shows the panel gets it right.

Say plainly where the person's time now goes: reading summaries and reworking, instead of attending hand-offs.

## 4. One card per agent

An agent is an outcome, or part of one, with a trigger. Five questions per card, no more:

```
Agent: <name>
Trigger: <what starts it: an event, a file state, a schedule>
Input: <the files and facts it reads; where they live>
Action: <what it does, in one sentence>
Output: <the file, verdict, commit or message it produces; where it goes>
Hand-off: <who or what takes the output, and the signal that says it is ready>
```

Standards are built into the card, not added afterwards: the security pass, the accessibility bar, the performance budget, the logging an operator needs. If two cards share an input and an output, they are one agent. If a card's output is read only by a person, ask whether a panel of agents could read it instead and the person review the panel's verdict.

## 5. Measures

Three numbers from the current-state map, re-measured after each feature: throughput (outcomes finished per week), first-pass rate (finished without rework), and calendar time from request to acceptance. Add the two autonomy numbers: the share of decisions a person had to make, and the share of agent decisions a person later reversed. Write the baseline now; a map without a baseline cannot show it worked.

## 6. Rollout

One table: what changes, for whom, when, and who owns it. Pair each change with how people learn it — a pre-read before any session, a short workshop on their own code or files rather than a demo, office hours in the first fortnight, a named player-coach who uses the system daily and answers questions. State the operating rules in one short list: judgement stays with people, execution with agents; context lives in the repository and the ticket, not in chat; the same bar for every change whoever made it; everything logged.

## Output

`outcome-map.md` with the six sections in order and the counts at the top. The agent cards in section 4 become the roles; the outcomes in section 2 become the features; the measures in section 5 become the first rows of `RUN.md`. From here, "factory: setup" installs the pipeline and "factory: build <first outcome>" starts it.
