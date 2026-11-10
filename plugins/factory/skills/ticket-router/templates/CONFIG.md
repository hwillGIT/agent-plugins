# Factory settings

Read by `tickets.py config` and by every role. Change a value and the next step uses it; nothing restarts.

```yaml
branch: integration        # accepted tickets merge here, one squash commit each
promote: pr                # how a finished feature reaches main: pr (a person merges) | local (merge into local main, no push) | auto (merge and push; use for low-risk work you have reviewed ten times without rework)
concurrency: 3             # workers at once
paused: false              # true stops new assignments; running tickets finish
models:
  router: opus
  intake: sonnet
  worker: sonnet
  checker: sonnet           # acceptance is where quality is decided; do not save money here
  reviewer: sonnet
  panelist: sonnet
  arbiter: opus             # judges reasons against precedent; the weak point if cheap
  summarizer: sonnet
decisions:
  trivial: worker           # naming, local structure, order of work: the worker decides and writes it in notes.md
  standard: panel-3         # three blind positions, one round to reconcile, the arbiter rules; majority with dissent recorded
  high: panel-5             # five positions with a Skeptic as devil's advocate, two rounds, unanimous or escalate
approval:
  low: checker              # the checker's accepted verdict is enough
  medium: majority          # checker plus the listed reviewers; majority approves, dissent stays in eval.md
  high: unanimous           # every listed reviewer approves, or the ticket escalates to a person
reviews_by_surface:
  code: [quality, security]
  screen: [quality, accessibility, performance]
  data: [quality, security, schema]
  document: [reader]
scoring:                   # share of done tickets a scorer judges, by risk; a reworked ticket is always scored
  low: 25
  medium: 50
  high: 100
price_per_million_tokens: 0  # blended $/M tokens for your plan; 0 leaves cost lines in tokens only
mcp_allowlist: []            # empty: no restriction. Named: in this repository, agents may call only these MCP servers (e.g. [github, playwright])
always_escalate:
  - an irreversible step or one outside the repository: deploy, migration, deleting data, money, messages, permissions
  - reversing a decision a person made (a D- entry with by: person)
  - no consensus after the rounds the level allows
  - any question the arbiter judges the person would want to answer themselves (state why)
```

How a level is chosen for a question: **trivial** when it changes nothing another ticket, reader or system can see; **standard** when it touches a public interface, a data format, a dependency, a user-visible behaviour or another ticket's work; **high** when it is hard to reverse, touches security, money, personal data or compliance, or sets a pattern others will copy. The arbiter classifies and says why in the decision entry.
