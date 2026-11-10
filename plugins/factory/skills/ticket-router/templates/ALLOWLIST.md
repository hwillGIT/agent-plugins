# Allowlist

Who may open a ticket when requests arrive from somewhere other than this terminal: a chat channel, a GitHub issue, a scheduled run, another agent. A request from anyone not listed is recorded in `tickets/INBOX.md` and never started. Bots and other agents may suggest; they may not request.

| Name | Handle or account | May request | May answer a worker's question | Notes |
|------|-------------------|-------------|--------------------------------|-------|
| (you) | | yes | yes | |

Mode for requests not made by a listed person (pick one): `off` (ignore), `observe` (record what would have been accepted, start nothing), `auto` (start when a rule below matches). Default: `observe`.

Rules for `auto` (empty until you write one):
-
