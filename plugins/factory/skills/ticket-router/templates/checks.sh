#!/usr/bin/env bash
# tickets/checks.sh — the deterministic gate. Runs before any model reviews a ticket, from the ticket's worktree.
# Exit 0 means every check passed. Cheap, mechanical, no judgement: lint, types, tests, build, secrets.
# Edit the commands to match the project; delete what the project lacks. Keep it under five minutes.
set -euo pipefail

say() { printf '\n== %s\n' "$1"; }

if [ -f package.json ]; then
  say "install";   (npm ci --prefer-offline >/dev/null 2>&1 || npm install >/dev/null 2>&1)
  grep -q '"lint"'      package.json && { say "lint";      npm run -s lint; }
  grep -q '"typecheck"' package.json && { say "typecheck"; npm run -s typecheck; }
  grep -q '"test"'      package.json && { say "test";      CI=1 npm test -- --watch=false 2>/dev/null || CI=1 npm test; }
  grep -q '"build"'     package.json && { say "build";     npm run -s build; }
fi

if [ -f pyproject.toml ] || [ -f requirements.txt ]; then
  command -v ruff   >/dev/null && { say "ruff";   ruff check .; }
  command -v mypy   >/dev/null && [ -f mypy.ini -o -f pyproject.toml ] && { say "mypy"; mypy . || true; }
  command -v pytest >/dev/null && { say "pytest"; pytest -q; }
fi

if [ -f justfile ] && command -v just >/dev/null; then
  just --list 2>/dev/null | grep -q '^ *check' && { say "just check"; just check; }
fi

if [ -f go.mod ];     then say "go";    go vet ./... && go test ./...; fi
if [ -f Cargo.toml ]; then say "cargo"; cargo test --quiet; fi

say "secrets"
# Anything that looks like a live credential in the diff against the integration branch fails the gate.
base="${FACTORY_BRANCH:-integration}"
if git rev-parse --verify -q "$base" >/dev/null; then
  if git diff "$base"...HEAD | grep -E '^\+' | grep -Ei '(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|password\s*[:=]\s*["'"'"'][^"'"'"']{6,})' ; then
    echo "possible secret in the diff"; exit 1
  fi
fi

say "ok"
