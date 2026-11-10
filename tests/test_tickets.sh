#!/usr/bin/env bash
# The factory's own regression test: the whole ticket lifecycle in a scratch repository, plus the guard.
# Runs in CI on every push and pull request; run it locally with: bash tests/test_tickets.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
T="python3 $HERE/plugins/factory/skills/ticket-router/scripts/tickets.py"
G="python3 $HERE/plugins/factory/scripts/guard.py"
S=$(mktemp -d); trap 'rm -rf "$S" "$S-wt"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
expect_fail() { if "$@" >/dev/null 2>&1; then fail "expected failure: $*"; fi; }

cd "$S"; git init -q -b main . && git config user.email t@t && git config user.name t
mkdir -p src && echo 'console.log(1)' > src/a.js && echo '{"name":"x","scripts":{"test":"node -e \"process.exit(0)\""}}' > package.json
git add -A && git commit -qm init

# init, feature, tickets
$T init >/dev/null
[ -f tickets/CONFIG.md ] && [ -d tickets/scorers ] && [ -f tickets/SCORES.md ] || fail "init files"
F=$($T feature new "Dark mode" --request "Add a dark mode toggle." --requested-by tester | head -1); [ "$F" = F-001 ] || fail "feature id"
A=$($T new "Fix #42 tokens" --feature F-001 --owns src/theme/ --deliverable src/theme/ --risk low --reviews quality | head -1); [ "$A" = T-001 ] || fail "ticket id"
B=$($T new "Toggle" --feature F-001 --owns src/settings/ --deliverable src/settings/ --risk medium --reviews quality,accessibility --depends T-001 | head -1)
grep -q "^title: Fix #42 tokens" tickets/T-001/rd.md || fail "title with # kept"
$T validate >/dev/null || fail "validate clean"

# open questions block ready; decide + resolve clears them
python3 - <<'EOF'
p='tickets/T-002/rd.md'; s=open(p).read(); open(p,'w').write(s.replace("## Open questions\nNone.","## Open questions\nlocalStorage or profile API?"))
EOF
expect_fail $T ready T-002
expect_fail $T decide T-002 --question "two
lines" --decided x --why y --by worker --level trivial
D=$($T decide T-002 --question "localStorage or profile API?" --decided localStorage --why "pattern src/prefs" --by council --dissent "Architect: API"); [ "$D" = D-001 ] || fail "decision id"
$T resolve T-002 --decision D-001 >/dev/null; $T ready T-001 >/dev/null; $T ready T-002 >/dev/null
git add -A && git commit -qm tickets && git branch integration

# transitions and start rules
expect_fail $T status T-001 done
$T status T-001 running >/dev/null
expect_fail $T status T-002 running   # depends on T-001
$T next | grep -q "nothing runnable" || fail "next respects deps"

# gate from a worktree, fail-closed verdict, stale gate
git worktree add -q -b ticket/T-001 "$S-wt" integration
mkdir -p "$S-wt/src/theme" && echo x > "$S-wt/src/theme/t.js" && (cd "$S-wt" && git add -A && git commit -qm "T-001: tokens")
(cd "$S-wt" && $T gate T-001 >/dev/null) || fail "gate pass"
[ -f tickets/T-001/evidence/gate.txt ] || fail "gate evidence lands in the main tree"
$T status T-001 review >/dev/null
expect_fail $T verdict T-001                      # unsigned checker
python3 - <<'EOF'
p='tickets/T-001/eval.md'; s=open(p).read(); open(p,'w').write(s.replace("- Verdict: accepted | returned","- Verdict: accepted").replace("- Checked by:","- Checked by: checker"))
EOF
v=$($T verdict T-001 || true); [[ $v == approve* ]] || fail "low risk approve: $v"
echo y > "$S-wt/src/theme/u.js" && (cd "$S-wt" && git add src && git commit -qm "T-001: more")
expect_fail $T verdict T-001                      # stale gate
(cd "$S-wt" && $T gate T-001 >/dev/null) || fail "gate pass 2"
$T status T-001 done >/dev/null; $T log T-001 --minutes 30 --tokens 120000 --role worker >/dev/null

# votes: listed roles only, arbiter tie-break, status required
expect_fail $T vote T-002 --role quality --vote approve --why x   # T-002 is ready, not running
$T status T-002 running >/dev/null; $T status T-002 review >/dev/null
mkdir -p tickets/T-002/evidence && printf 'gate\nHEAD: none\nRESULT: PASS\n' > tickets/T-002/evidence/gate.txt
python3 - <<'EOF'
p='tickets/T-002/eval.md'; s=open(p).read(); open(p,'w').write(s.replace("- Verdict: accepted | returned","- Verdict: accepted").replace("- Checked by:","- Checked by: checker"))
EOF
$T vote T-002 --role Quality --vote approve --why ok >/dev/null
expect_fail $T vote T-002 --role security --vote approve --why unlisted
$T vote T-002 --role accessibility --vote changes --why "FIX · Toggle.jsx:14 · no name" >/dev/null
v=$($T verdict T-002 || true); [[ $v == escalate* ]] || fail "split escalates: $v"
$T vote T-002 --role arbiter --vote changes --why "defect is real" >/dev/null
v=$($T verdict T-002 || true); [[ $v == changes* ]] || fail "arbiter tie-break: $v"
$T vote T-002 --role accessibility --vote approve --why fixed >/dev/null
v=$($T verdict T-002 || true); [[ $v == approve* ]] || fail "majority approve: $v"
$T status T-002 done >/dev/null
$T feature list | grep -q "\[review\]" || fail "feature rolls up to review"

# scoring, summary, rework, bench, stats, dashboard
$T sample | grep -q "T-002" && fail "T-002 should fall outside the 50% medium sample (stable bucket 74)"
python3 - <<'PY'
p='tickets/CONFIG.md'; s=open(p).read(); open(p,'w').write(s.replace("  medium: 50\n  high: 100", "  medium: 100\n  high: 100"))
PY
$T sample | grep -q "T-002" || fail "medium risk sampled at 100%"
$T score T-002 --scorer task-compliance --label partial --why "added a footer nobody asked for" >/dev/null
grep -q "score FAIL on T-002" tickets/INBOX.md || fail "failing score to inbox"
$T feature summary F-001 >/dev/null
R=$($T rework F-001 --note "D-001 is wrong: follow the user across devices" --overrides D-001 | head -1); [ "$R" = T-003 ] || fail "rework id"
grep -q "Overridden by: D-002" tickets/DECISIONS.md || fail "override marked"
$T precedent "localStorage profile" | head -1 | grep -q "D-002 \[person" || fail "person precedent first"
expect_fail $T bench add T-001                     # not merged yet: no commit titled T-001: on integration
git checkout -q integration && git merge -q --squash ticket/T-001 >/dev/null && git commit -qm "T-001: Fix #42 tokens" && git checkout -q main
$T bench add T-001 >/dev/null; [ -f tickets/bench/T-001/task.md ] || fail "bench task"
grep -q "Base commit" tickets/bench/T-001/task.md || fail "bench base"
$T bench record T-001 --model opus --passed 5/5 --minutes 20 --tokens 90000 >/dev/null
$T stats | grep -q "Benchmarks: opus 5/5" || fail "bench in stats"
$T stats | grep -q "Tokens logged" || fail "tokens in stats"
$T dashboard >/dev/null; [ -f tickets/dashboard.html ] || fail "dashboard"
$T feature status F-001 accepted >/dev/null; grep -q "^accepted: " tickets/features/F-001/feature.md || fail "accepted date"

# lock: two concurrent writers both land
( $T log T-001 --minutes 1 & $T log T-001 --minutes 2 & wait )
[ "$(grep -c '^| T-001' tickets/RUN.md)" -ge 3 ] || fail "concurrent logs"
[ ! -f tickets/.lock ] || fail "lock released"

# guard
ev() { printf '{"hook_event_name":"PreToolUse","cwd":"%s","tool_name":"%s","tool_input":{"command":"%s"}}' "$S" "$1" "$2"; }
for c in 'git push origin main' 'git -C . push origin main' 'echo hi && git push -f origin feat' 'git push origin -d feat' 'rm -rf /tmp/x' 'kubectl -n ns apply -f x' 'gh api --method DELETE repos/x'; do
  ev Bash "$c" | $G 2>/dev/null && fail "guard should block: $c"; done
for c in 'git push -u origin integration' 'git push --dry-run origin main' "rm -rf $S/build" 'rm -rf build' 'npm test'; do
  ev Bash "$c" | $G 2>/dev/null || fail "guard should allow: $c"; done
ev mcp__github__create_issue '' | $G 2>/dev/null || fail "mcp allowed with empty allowlist"
python3 - <<'EOF'
p='tickets/CONFIG.md'; s=open(p).read(); open(p,'w').write(s.replace("mcp_allowlist: []", "mcp_allowlist: [playwright]"))
EOF
ev mcp__github__create_issue '' | $G 2>/dev/null && fail "mcp blocked off allowlist"
ev mcp__playwright__browser_navigate '' | $G 2>/dev/null || fail "mcp allowed on allowlist"
printf '{"hook_event_name":"TaskCompleted","cwd":"%s","task_subject":"T-003 rework"}' "$S" | $G 2>/dev/null && fail "task without verdict should not close"
printf '{"hook_event_name":"TaskCompleted","cwd":"%s","task_subject":"T-001"}' "$S" | $G 2>/dev/null || fail "task with verdict closes"

echo "ok: lifecycle, verdicts, votes, scoring, rework, bench, lock, guard"
