#!/usr/bin/env python3
"""guard.py — the never-automated list, enforced. A Claude Code hook; reads the event on stdin.

Active only in a repository that has tickets/CONFIG.md (a factory repository); elsewhere it allows everything.

PreToolUse (mcp__*): when tickets/CONFIG.md names an mcp_allowlist, exit 2 for any MCP server not on it.
PreToolUse (Bash): exit 2 on a push to main/master, a force push, a remote branch deletion, destroying the
integration or main branch, a recursive delete outside the working directory, destructive SQL, deploys and
infrastructure changes, migrations, and GitHub deletions or permission changes. Each segment of a compound
command (;, &&, ||, |, newline) is tested on its own; options between the tool and its verb are allowed for.
Out of reach, by design: commands hidden in quoting, variables, aliases, scripts or `bash -c` strings — the
guard stops the plain forms an agent types, it is not a sandbox.
TaskCompleted: exit 2 when the task names a ticket whose eval.md is missing or carries no accepted verdict
signed by a checker (the same line tickets.py checks: `- Verdict: accepted` inside "Checker's verdict").
"""
import json, os, re, sys

OPTS = r"(?:\s+-\S+(?:\s+[^-\s]\S*)?)*"   # options between a tool and its verb: git -C x push, kubectl -n ns apply
RULES = [
    (rf"\bgit{OPTS}\s+push\b(?![^;&|\n]*--dry-run)[^;&|\n]*\b(main|master)\b", "push to main or master"),
    (rf"\bgit{OPTS}\s+push\b[^;&|\n]*(\s--force\b|\s-f\b|\s--force-with-lease\b|\s\+\S+)", "force push"),
    (rf"\bgit{OPTS}\s+push\b[^;&|\n]*(\s--delete\b|\s-d\b|\s:\S)", "deleting a remote branch"),
    (rf"\bgit{OPTS}\s+(reset\s+--hard|clean\s+-\S*f|branch\s+(-D|-d|--delete))\b[^;&|\n]*\b(main|master|integration)\b", "destroying the integration or main branch"),
    (r"\brm\s+(?:-\S*r\S*|--recursive)(?:\s+-\S+|\s+--\S+)*\s+(?P<target>\S+)", "recursive delete"),
    (r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE|DELETE\s+FROM\s+\w+\s*;)", "destructive SQL"),
    (rf"\b(terraform|tofu){OPTS}\s+(apply|destroy)\b|\bkubectl{OPTS}\s+(apply|delete)\b|\bhelm{OPTS}\s+(install|upgrade|uninstall)\b|\bfly{OPTS}\s+deploy\b|\bvercel\b[^;&|\n]*--prod\b|\bgcloud\b[^;&|\n]*\bdeploy\b|\baws\b[^;&|\n]*\b(deploy|delete)\b", "deploy or infrastructure change"),
    (r"\b(prisma\s+migrate\s+deploy|alembic\s+upgrade|rails\s+db:migrate|knex\s+migrate:latest|flyway\s+migrate)\b", "running a migration"),
    (r"\bgh\s+(repo\s+delete|secret\s+set|api\b[^;&|\n]*(-X\s*DELETE|--method\s+DELETE))", "GitHub permission or deletion change"),
]
VERDICT_RE = re.compile(r"^- Verdict:\s*(accepted|returned)\s*$", re.M)   # the same line as tickets.py VERDICT_RE; keep them identical
CHECKED_BY_RE = re.compile(r"^- Checked by:\s*(\S.*)$", re.M)


def segments(cmd):
    return [s.strip() for s in re.split(r"\s*(?:;|&&|\|\||\||\n)\s*", cmd) if s.strip()]


def check_bash(cmd, cwd):
    """The reason this command is refused, or None."""
    for seg in segments(cmd):
        for pat, why in RULES:
            m = re.search(pat, seg, re.I)
            if not m: continue
            if why == "recursive delete":
                target = m.group("target").strip("'\"")
                if not (target.startswith("/") or target.startswith("~") or target.startswith("$") or target.startswith("..")): continue   # a relative path inside the worktree is ordinary cleanup
                if target.startswith("/") and os.path.abspath(target).startswith(os.path.abspath(cwd) + os.sep): continue
                why = "recursive delete outside the working directory"
            return f"{why} is on the never-automated list. Leave this step to a person; record it in the ticket as 'stops for a person'. Segment: {seg[:160]}"
    return None


def mcp_allowlist(root):
    """The mcp_allowlist from tickets/CONFIG.md's yaml block: a list of server names, or [] for no restriction."""
    try: text = open(os.path.join(root, "tickets", "CONFIG.md"), encoding="utf-8").read()
    except OSError: return []
    m = re.search(r"^mcp_allowlist:\s*(\[[^\]]*\])?\s*(?:#.*)?$((?:\n  - [^\n]*)*)", text, re.M)
    if not m: return []
    inline = [x.strip() for x in (m.group(1) or "").strip("[]").split(",") if x.strip()]
    block = re.findall(r"^  - ([^\n#]+)", m.group(2) or "", re.M)
    return [x.strip() for x in inline + block if x.strip()]


def check_mcp(root, tool_name):
    """The reason an MCP tool is refused, or None: the server (second segment of mcp__<server>__<tool>) is not on the allowlist."""
    allowed = mcp_allowlist(root)
    if not allowed or not tool_name.startswith("mcp__"): return None
    server = tool_name.split("__")[1] if tool_name.count("__") >= 2 else tool_name
    if server.lower() in {a.lower() for a in allowed}: return None
    return f"MCP server '{server}' is not in tickets/CONFIG.md mcp_allowlist ({', '.join(allowed)}); add it there if this repository's agents may use it."


def check_task(root, text):
    """The reason a task naming a ticket may not close, or None. Fails closed when the evidence is missing."""
    ids = sorted(set(re.findall(r"\b(T-\d{3,})\b", text)))
    for tid in ids:
        ev = os.path.join(root, "tickets", tid, "eval.md")
        if not os.path.isfile(ev): return f"{tid} has no eval.md; a task closes on evidence, not on a claim."
        s = open(ev, encoding="utf-8").read()
        sec = re.search(r"^## Checker's verdict\s*\n(.*?)(?=^## |\Z)", s, re.S | re.M | re.I)
        body = sec.group(1) if sec else ""
        m = VERDICT_RE.search(body)
        if not (m and m.group(1) == "accepted" and CHECKED_BY_RE.search(body)): return f"{tid} has no accepted verdict signed by a checker in eval.md; a task closes on evidence, not on a claim."
    return None


def main():
    try: event = json.load(sys.stdin)
    except Exception: return 0
    root = event.get("cwd") or os.getcwd()
    if not os.path.isfile(os.path.join(root, "tickets", "CONFIG.md")): return 0
    name = event.get("hook_event_name", "")
    why = None
    if name == "PreToolUse":
        tool = event.get("tool_name", "") or ""
        why = check_mcp(root, tool) if tool.startswith("mcp__") else check_bash((event.get("tool_input") or {}).get("command", "") or "", root)
    elif name == "TaskCompleted": why = check_task(root, " ".join(str(event.get(k, "")) for k in ("task_subject", "task_description")))
    if why: print("factory guard: " + why, file=sys.stderr); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
