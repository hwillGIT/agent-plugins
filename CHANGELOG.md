# Changelog

## 3.1.0 — 2026-11-10

Measurement and automation, from the *Software Factories: An Infrastructure Approach* deck and Warp's factory examples.

- **Scorers** (`tickets/scorers/*.md`, three shipped) judge done tickets from the request, the diff and the evidence; `tickets.py sample` picks them by risk-weighted sampling, reworked tickets always; `tickets.py score` writes `SCORES.md` and sends failures to `INBOX.md`. New `scorer` role.
- **Improver** role: factory engineering as a feature request with counts, from the scores, inbox, overrides and run log; the proposal runs through the normal pipeline.
- **Benchmarks**: `tickets.py bench add|list|record` turns finished tickets into replayable tasks and records quality against cost per model in `BENCH.md`.
- **Cost and cycle time** in `stats`: tokens by role, money when `price_per_million_tokens` is set, request-to-accepted days per feature.
- **GitHub Actions automations** (`templates/github/factory.yml`, installed by "factory: setup --github"): issue label intake, `@factory` comments, CI-failure triage, a weekly dependency audit, manual dispatch.
- Reviewers classify findings **FIX** or **DECIDE**; DECIDE findings go to the decision panel.
- The router enters mid-procedure (CI failure, comment on delivered work, merge notice), acknowledges at once, speaks in one voice, links everything.
- Checker records multi-step screen flows.
- Guard: optional **MCP allowlist** per repository (`mcp_allowlist` in CONFIG.md).
- `tickets.py pr` labels the pull request `factory`.
- Precedent search follows an override back to the question it overturned; live entries rank above overridden ones.
- The repository tests itself: `tests/test_tickets.sh` and `claude plugin validate` on every push.

## 3.0.0 — 2026-11-10

Autonomous pipeline: router, intake, decision panel (panelists, arbiter, ledger with precedent and overrides), gate, checker, reviewers voting by risk, merger, feature summaries and rework. Packaged as the `factory` plugin in the `hwillgit` marketplace with the `/factory` front door.
