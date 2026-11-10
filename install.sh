#!/usr/bin/env bash
# One line on any Mac or Linux machine with Claude Code:
#   curl -fsSL https://raw.githubusercontent.com/hwillGIT/agent-plugins/main/install.sh | bash
# Installs the factory plugin (user scope) and refreshes ~/.agents/skills for Codex, Gemini and other tools.
set -e
command -v claude >/dev/null || { echo "Claude Code (claude) is not on PATH; install it first: https://code.claude.com"; exit 1; }
echo "Claude Code $(claude --version 2>/dev/null)"
# Every error is shown: a failed install says why, instead of falling through to an update that cannot work.
if claude plugin marketplace list 2>/dev/null | grep -qi "hwillgit"; then claude plugin marketplace update hwillgit
else claude plugin marketplace add hwillGIT/agent-plugins; fi
if claude plugin list 2>/dev/null | grep -q "factory@hwillgit"; then claude plugin update factory@hwillgit
else claude plugin install factory@hwillgit || { echo; echo "The install failed with the message above. If it names a schema or version problem, update Claude Code (claude update) and run this line again."; exit 1; }; fi
if command -v git >/dev/null; then
  mkdir -p ~/.agents/skills; rm -rf ~/.agents/agent-plugins
  git clone -q --depth 1 https://github.com/hwillGIT/agent-plugins ~/.agents/agent-plugins
  for s in factory ticket-writing ticket-router outcome-map; do rm -rf ~/.agents/skills/$s; cp -R ~/.agents/agent-plugins/plugins/factory/skills/$s ~/.agents/skills/$s; done
  cp -R ~/.agents/agent-plugins/plugins/factory/agents ~/.agents/skills/ticket-router/agents
fi
echo "done: /factory in Claude Code; ~/.agents/skills refreshed. In a repository: /factory setup"
