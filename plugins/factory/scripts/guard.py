#!/usr/bin/env python3
"""guard.py — the never-automated list, enforced. A Claude Code hook; reads the event on stdin.

Active only in a repository that has tickets/CONFIG.md (a factory repository); elsewhere it allows everything.

PreToolUse (Bash): exit 2 on a push to main/master, a force push, a remote branch deletion, and the common
destructive commands. The message tells the agent to leave the step to a person.
TaskCompleted: exit 2 when the task names a ticket whose eval.md carries no accepted verdict.
"""
import json, os, re, sys


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    root = event.get("cwd") or os.getcwd()
    if not os.path.isfile(os.path.join(root, "tickets", "CONFIG.md")):
        return 0
    name = event.get("hook_event_name", "")
    if name == "PreToolUse":
        cmd = (event.get("tool_input") or {}).get("command", "") or ""
        rules = [
            (r"git\s+push\b(?!.*--dry-run).*\b(main|master)\b", "push to main or master"),
            (r"git\s+push\b.*(--force|-f\b|\+refs)", "force push"),
            (r"git\s+push\b.*(--delete|:refs/heads/|\s:\S)", "deleting a remote branch"),
            (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|~|\$HOME|\.\.)", "recursive delete outside the worktree"),
            (r"\bgit\s+(reset\s+--hard|clean\s+-[a-zA-Z]*f|branch\s+-D)\b.*\b(main|master|integration)\b", "destroying the integration or main branch"),
            (r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE|DELETE\s+FROM\s+\w+\s*;)", "destructive SQL"),
            (r"\b(terraform|tofu)\s+(apply|destroy)\b|\bkubectl\s+(apply|delete)\b|\bhelm\s+(install|upgrade|uninstall)\b|\bfly\s+deploy\b|\bvercel\s+--prod\b|\bgcloud\s+.*\bdeploy\b|\baws\s+.*\b(deploy|delete)\b", "deploy or infrastructure change"),
            (r"\b(prisma\s+migrate\s+deploy|alembic\s+upgrade|rails\s+db:migrate|knex\s+migrate:latest|flyway\s+migrate)\b", "running a migration"),
            (r"\bgh\s+(repo\s+delete|secret\s+set|api\s+.*-X\s+DELETE)\b", "GitHub permission or deletion change"),
        ]
        for pat, why in rules:
            if re.search(pat, cmd, re.I | re.S):
                print(f"factory guard: {why} is on the never-automated list. Leave this step to a person; record it in the ticket as 'stops for a person'. Command: {cmd[:160]}", file=sys.stderr)
                return 2
        return 0
    if name == "TaskCompleted":
        text = " ".join(str(event.get(k, "")) for k in ("task_subject", "task_description"))
        m = re.search(r"\b(T-\d{3,})\b", text)
        if not m:
            return 0
        ev = os.path.join(root, "tickets", m.group(1), "eval.md")
        if not os.path.isfile(ev):
            return 0
        if not re.search(r"^- Verdict:\s*accepted\s*$", open(ev, encoding="utf-8").read(), re.M):
            print(f"factory guard: {m.group(1)} has no accepted verdict in eval.md; a task closes on evidence, not on a claim.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
