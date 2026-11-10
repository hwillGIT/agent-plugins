# agent-plugins

Claude Code plugins by Hubert Williams, installed from this repository as a marketplace. One plugin so far.

## factory

An autonomous ticket pipeline. You say what to build; the intake writes the feature and its tickets; workers build them on their own branches; when a worker meets a question, a panel of agents argues it out against the ledger of past decisions, the repository's own patterns and named standards, and writes the verdict down; a deterministic gate, a checker and reviewers accept by a rule tied to risk; a merger lands each ticket; and you get a summary sorted by what is most likely to need rework. Anything you disagree with becomes a rework ticket whose decision outranks the panel's from then on. The one front door is `/factory`.

```
/factory setup                      first use in a repository: tickets/, CONFIG.md, checks.sh
/factory build dark mode toggle     a feature, end to end; you hear back when the summary is ready
/factory status                     the board
/factory review F-001               the summary: decisions without precedent first, then dissent, then what to look at
/factory rework F-001 D-014 is wrong: exports stay CSV
/factory accept F-001
/factory map our release process    redesign a process before adding agents to it
/factory stats                      throughput, first-pass rate, cost per merged ticket, the share of panel decisions you overrode
/factory score                      run the judges on the sampled finished tickets
/factory improve                    one proposed change to the factory, with the counts behind it
/factory bench opus sonnet          replay finished tickets under each model; quality against cost
/factory setup --github             issue-label intake, @factory comments, CI-failure triage, a weekly audit
```

What never happens without a person: a push to `main`, a deploy, a migration, deleting data, money, posting outside the repository, changing permissions. A hook enforces it in any repository that has `tickets/CONFIG.md`.

## Install

On any Mac or Linux machine with Claude Code, one line:

```
curl -fsSL https://raw.githubusercontent.com/hwillGIT/agent-plugins/main/install.sh | bash
```

Or by hand, on any machine including Windows:

```
claude plugin marketplace add hwillGIT/agent-plugins
claude plugin install factory@hwillgit
```

Or inside Claude Code: `/plugin marketplace add hwillGIT/agent-plugins`, then `/plugin install factory@hwillgit`. Updates arrive with `claude plugin update factory@hwillgit`.

For Codex CLI, Gemini CLI and other tools that read `~/.agents/skills`:

```
git clone https://github.com/hwillGIT/agent-plugins ~/.agents/agent-plugins
ln -s ~/.agents/agent-plugins/plugins/factory/skills/* ~/.agents/skills/
```

For claude.ai (web, desktop, mobile): upload the four zips in `plugins/factory/claude-ai-uploads/` under Customize › Skills. They are account-wide.

See `PROMPTS.md` for ready-to-paste prompts in each place.

## Layout

```
.claude-plugin/marketplace.json      the catalog
plugins/factory/
  .claude-plugin/plugin.json
  skills/factory/SKILL.md            the front door
  skills/ticket-writing/SKILL.md     the two-file ticket contract, lenses, standards rows
  skills/ticket-router/SKILL.md      the pipeline: four authorities, the panel, acceptance, the feature loop
  skills/ticket-router/scripts/tickets.py   the only writer of ticket state (standard library)
  skills/ticket-router/templates/    CONFIG.md, DECISIONS.md, feature.md, review.md, rd.md, eval.md, checks.sh, …
  skills/outcome-map/SKILL.md        process redesign before agents
  agents/                            router, intake, worker, panelist, arbiter, watchdog, checker, reviewer, merger, summarizer, reproducer, lens, scorer, improver
  skills/ticket-router/templates/scorers/   the three judges; templates/github/factory.yml the automations
  hooks/hooks.json + scripts/guard.py   the never-automated list and the MCP allowlist, enforced
tests/test_tickets.sh                the factory's own regression test (CI runs it)
```

## Changing it

Edit on a branch, open a pull request, merge. Every machine picks the change up on its next `claude plugin update`. The ticket factory can run its own changes: `/factory build …` in this repository.
