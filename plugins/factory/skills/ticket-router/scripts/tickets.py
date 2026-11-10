#!/usr/bin/env python3
"""tickets.py — the only writer of ticket state. Standard library only. Run from anywhere inside the repository.

State lives in <main worktree>/tickets/: one folder per ticket (rd.md, eval.md, notes.md, evidence/), one folder
per feature (tickets/features/F-001/feature.md, summary.md, review.md), and the shared files CONFIG.md,
DECISIONS.md, BOARD.md, RUN.md, ALLOWLIST.md, INBOX.md, checks.sh. A linked worktree never holds state: the
script finds the main worktree through git and writes there. BOARD.md is a view, rewritten after every change.
Every writing command takes tickets/.lock first and writes each file atomically, so two agents cannot
interleave a check with a write.

  init                                        create tickets/ from the templates (idempotent)
  config                                      the settings in force, as JSON
  feature new "Title" [--request "..."] [--requested-by name]
  feature status F-001 <proposed|decomposed|running|review|accepted|rework>
  feature list | feature show F-001
  feature summary F-001                       write summary.md from tickets, decisions, votes, evidence
  new "Title" --owns src/a/,tests/a/ --deliverable path [--kind code|document|analysis|operations]
              [--mode solo|team] [--depends T-001,T-002] [--risk low|medium|high] [--feature F-001]
              [--reviews quality,security]
  show T-003 | validate [T-003] | ready T-003 | next | board
  status T-003 <draft|ready|running|review|done|blocked> [--why "..."]   (--why required for blocked)
  precedent "words to match"                  decisions that may already answer a question, a person's first
  decide T-003 --question "..." --decided "..." --why "..." --by council|arbiter|worker|person|escalated
         [--options "a | b"] [--level trivial|standard|high] [--precedent "D-003 (followed)"] [--dissent "..."]
         [--reversible yes|no] [--overrides D-014]            prints the new D- id
  resolve T-003 --decision D-014 (--number N | --all)   clear open question(s); record the decision in Context
  gate T-003 [--worktree path]                checks.sh from the integration branch + the owns check; evidence/gate.txt
  vote T-003 --role security --vote approve|changes --why "..."
  verdict T-003                               approve | changes | escalate, from gate, checker, votes, CONFIG.md
  rework F-001|T-003 --note "..." [--overrides D-014] [--owns ...] [--risk ...] [--kind ...]
  log T-003 --minutes 23 [--attempt 1 --questions 1 --returned 0 --defects 0 --restarts 0 --tokens N --role worker|panel|review|score]
  stats                                       throughput, first-pass rate, decisions by maker, override share
  dashboard                                   write tickets/dashboard.html   (alias: html)
  import-issue 42 [--kind ...] [--feature F-001]   a draft ticket from a GitHub issue (gh CLI)
  pr F-001|T-003 [--base main]                push the integration branch and open the pull request (gh CLI)
  sample                                      done tickets due for scoring (by risk-weighted sampling; reworked ones always)
  score T-003 --scorer task-compliance --label compliant --why "..."   record a judge's label; SCORES.md
  bench add T-003 | bench list | bench record T-003 --model opus --passed 7/8 --minutes 22 [--tokens N]

Exit codes: 0 ok · 1 error (message on stderr, prefixed "error:") · validate 2 when any ticket has problems ·
gate 2 FAIL · verdict 2 changes, 3 escalate. Commands that create something print the new id on the first line.

Status transitions a ticket may make: draft→ready, ready→draft|running, running→review|blocked|draft,
review→done|running|blocked, blocked→draft|ready|running, done→(none; rework makes a new ticket).
"""
import argparse, datetime, html, json, os, re, shutil, subprocess, sys, time

STATUSES = ["draft", "ready", "running", "review", "done", "blocked"]
TRANSITIONS = {"draft": {"ready"}, "ready": {"draft", "running"}, "running": {"review", "blocked", "draft"},
               "review": {"done", "running", "blocked"}, "blocked": {"draft", "ready", "running"}, "done": set()}
FEATURE_STATUSES = ["proposed", "decomposed", "running", "review", "accepted", "rework"]
KINDS = ["code", "document", "analysis", "operations"]
RISKS = ["low", "medium", "high"]
DECIDERS = ["council", "arbiter", "worker", "person", "escalated"]
SURFACES = ["quality", "security", "accessibility", "performance", "schema", "reader"]
LIST_KEYS = ("owns", "depends", "reviews", "tickets")
RD_HEADINGS = ("Outcome", "Context the worker needs", "Constraints", "Out of scope", "Open questions")
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates") if os.path.isdir(os.path.join(HERE, "templates")) else os.path.join(HERE, "..", "templates")
SHARED = ["CONFIG.md", "DECISIONS.md", "BOARD.md", "RUN.md", "ALLOWLIST.md", "INBOX.md", "checks.sh", "SCORES.md", "BENCH.md"]
RUN_COLS = ("Ticket", "Attempt", "Started", "Ended", "Minutes", "Questions asked", "Returned by checker",
            "Defects found after acceptance", "Restarts recovered", "Tokens (if known)", "Role")
ROLES = ["worker", "panel", "review", "score", "bench", "other"]
SCORERS_DIR = "scorers"
BENCH_DIR = "bench"
VERDICT_RE = re.compile(r"^- Verdict:\s*(accepted|returned)\s*$", re.M)   # guard.py checks the same line; keep the two identical
CHECKED_BY_RE = re.compile(r"^- Checked by:\s*(\S.*)$", re.M)
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
ID_RE = re.compile(r"^[TF]-\d{3,}$")
MUTATING = {"init", "feature", "new", "status", "ready", "decide", "resolve", "gate", "vote", "rework", "log", "import-issue", "pr", "score", "bench"}


# ---------------------------------------------------------------- where state lives

def main_worktree():
    """The main checkout's root, even when run from a linked worktree; cwd when this is not a git repository."""
    r = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True)
    if r.returncode != 0: return os.getcwd()
    common = os.path.abspath(r.stdout.strip())
    return os.path.dirname(common) if os.path.basename(common) == ".git" else os.getcwd()


MAIN = os.environ.get("FACTORY_ROOT") or main_worktree()
ROOT = os.path.join(MAIN, "tickets")
FEATURES = os.path.join(ROOT, "features")


# ---------------------------------------------------------------- small helpers

def fail(msg):
    print("error:", msg, file=sys.stderr); sys.exit(1)


def now(fmt="%Y-%m-%d %H:%M"):
    return datetime.datetime.now().strftime(fmt)


def read(p):
    return open(p, encoding="utf-8", newline=None).read().replace("\r\n", "\n")


def write(p, text):
    """Atomic: the file is either the old text or the new one, never empty, whoever reads it mid-write."""
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f: f.write(text)
    os.replace(tmp, p)


def append(p, text):
    write(p, (read(p) if os.path.isfile(p) else "") + text)


class lock:
    """tickets/.lock, created exclusively; a lock older than 120 s is taken as abandoned."""
    def __enter__(self):
        os.makedirs(ROOT, exist_ok=True); self.p = os.path.join(ROOT, ".lock"); deadline = time.time() + 30
        while True:
            try:
                fd = os.open(self.p, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, f"{os.getpid()} {now()}".encode()); os.close(fd); return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.p) > 120: os.remove(self.p); continue
                except FileNotFoundError: continue
                if time.time() > deadline: fail("tickets/.lock is held by another command for 30 s; wait, or remove it if nothing is running")
                time.sleep(0.2)
    def __exit__(self, *a):
        try: os.remove(self.p)
        except FileNotFoundError: pass


def template(name):
    p = os.path.join(TEMPLATES, name)
    if not os.path.isfile(p): fail(f"template {name} missing beside the script")
    return read(p)


def short(text, n=60):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def norm(path):
    p = os.path.normpath(path.strip()).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def under(path, prefix):
    """True when path is prefix itself or inside it, by path segment: src/api does not cover src/api-client."""
    p, q = norm(path), norm(prefix)
    return q == "." or p == q or p.startswith(q + "/")


def one_line(s, what):
    if "\n" in s or "\r" in s: fail(f"{what} must be one line")
    return s.strip()


def quoted(text):
    """Foreign text (an issue body, a request) goes into a file as a block quote, so its headings cannot pass for ours."""
    return "\n".join("> " + l if l.strip() else ">" for l in text.strip().splitlines())


def sh(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True)
    if check and r.returncode != 0: fail(f"{cmd if isinstance(cmd, str) else ' '.join(cmd)}\n{r.stderr.strip()}")
    return r


# ---------------------------------------------------------------- frontmatter (the one format the files share)

def strip_comment(line):
    """A comment starts at a # preceded by whitespace; 'Fix #42' is a value, 'risk: low  # note' has a comment."""
    m = re.search(r"\s#", line)
    return line[:m.start()].rstrip() if m else line.rstrip()


def split_frontmatter(text, what="file"):
    m = FRONTMATTER_RE.match(text)
    if not m: fail(f"{what} has no frontmatter block")
    return m.group(1), m.group(2)


def join_frontmatter(fm, body):
    return "---\n" + fm.strip("\n") + "\n---\n" + body


def parse_list(v):
    return [x.strip() for x in str(v).strip("[]").split(",") if x.strip()]


def parse_frontmatter(fm):
    """Flat keys, `- ` lists, inline [lists], one level of nested blocks (budget:, models:). An empty value is ""."""
    data, key, nested = {}, None, None
    for raw in fm.splitlines():
        line = strip_comment(raw)
        if not line.strip(): continue
        indent = len(line) - len(line.lstrip()); s = line.strip()
        if s.startswith("- "):
            if indent >= 2 and nested is not None and isinstance(data.get(nested), dict):
                data[nested].setdefault("_items", []).append(s[2:].strip())
            else:
                if not isinstance(data.get(key), list): data[key] = []
                data[key].append(s[2:].strip())
            continue
        k, _, v = s.partition(":"); k, v = k.strip(), v.strip()
        if indent == 0:
            key, nested = k, None
            data[k] = parse_list(v) if v.startswith("[") else v
        else:
            if not isinstance(data.get(key), dict): data[key] = {}
            nested = key
            data[key][k] = parse_list(v) if v.startswith("[") else (int(v) if v.isdigit() else v)
    for k, v in list(data.items()):
        if isinstance(v, dict) and "_items" in v: data[k] = v["_items"]
    return data


def set_frontmatter_value(text, k, v):
    fm, body = split_frontmatter(text)
    new, done = [], False
    for line in fm.splitlines():
        if re.match(rf"^{re.escape(k)}:", line) and not done:
            m = re.search(r"\s(#.*)$", line); comment = ("  " + m.group(1)) if m else ""
            new.append(f"{k}: {v}{comment}"); done = True
        else: new.append(line)
    if not done: new.append(f"{k}: {v}")
    return join_frontmatter("\n".join(new), body)


def set_frontmatter_list(text, k, items):
    fm, body = split_frontmatter(text)
    block = (f"{k}:\n" + "".join(f"  - {i}\n" for i in items)) if items else f"{k}: []\n"
    pat = rf"^{re.escape(k)}:[^\n]*\n(?:  - [^\n]*\n)*"
    fm2 = fm + "\n"
    fm2 = re.sub(pat, lambda m: block, fm2, count=1, flags=re.M) if re.search(pat, fm2, re.M) else fm2 + block
    return join_frontmatter(fm2, body)


def section(body, heading):
    m = re.search(rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", body, re.S | re.M | re.I)
    return m.group(1) if m else None


def heading_count(body, heading):
    return len(re.findall(rf"^## {re.escape(heading)}\s*$", body, re.M | re.I))


def replace_section(body, heading, content):
    if section(body, heading) is None: return body.rstrip("\n") + f"\n\n## {heading}\n{content}\n"
    return re.sub(rf"(^## {re.escape(heading)}\s*\n)(.*?)(?=^## |\Z)", lambda m: m.group(1) + content + "\n\n", body, count=1, flags=re.S | re.M | re.I)


# ---------------------------------------------------------------- config

DEFAULT_CONFIG = {"branch": "integration", "promote": "pr", "concurrency": 3, "paused": False,
                  "approval": {"low": "checker", "medium": "majority", "high": "unanimous"},
                  "scoring": {"low": 25, "medium": 50, "high": 100},
                  "price_per_million_tokens": 0}


def config():
    c = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    p = os.path.join(ROOT, "CONFIG.md")
    if os.path.isfile(p):
        m = re.search(r"```yaml\n(.*?)\n```", read(p), re.S)
        if m:
            found = parse_frontmatter(m.group(1)); c.update(found)
            if isinstance(found.get("approval"), dict): c["approval"] = {**DEFAULT_CONFIG["approval"], **found["approval"]}
            if isinstance(found.get("scoring"), dict): c["scoring"] = {**DEFAULT_CONFIG["scoring"], **found["scoring"]}
            else: c["scoring"] = dict(DEFAULT_CONFIG["scoring"])
    c["concurrency"] = int(c.get("concurrency") or 3)
    c["paused"] = str(c.get("paused")).lower() == "true"
    try: c["price_per_million_tokens"] = float(c.get("price_per_million_tokens") or 0)
    except ValueError: c["price_per_million_tokens"] = 0.0
    return c


# ---------------------------------------------------------------- records: tickets and features

def ticket_ids():
    if not os.path.isdir(ROOT): return []
    return sorted(d for d in os.listdir(ROOT) if re.match(r"T-\d{3,}$", d))


def load_record(path, what):
    text = read(path); fm, body = split_frontmatter(text, what)
    d = parse_frontmatter(fm)
    for k in LIST_KEYS:
        if k in d and not isinstance(d[k], list): d[k] = parse_list(d[k]) if d[k] else []
    d["_body"], d["_path"], d["_text"] = body, path, text
    return d


def load(tid):
    p = os.path.join(ROOT, tid, "rd.md")
    if not os.path.isfile(p): fail(f"{tid}: rd.md missing")
    return load_record(p, f"{tid}/rd.md")


def load_all():
    return {t: load(t) for t in ticket_ids()}


def save_record(rec, text):
    """The one write path for rd.md and feature.md: the file, then the parsed keys, so no caller reads stale data."""
    write(rec["_path"], text)
    fresh = load_record(rec["_path"], rec["_path"]); rec.clear(); rec.update(fresh)


def save_body(rec, body):
    fm, _ = split_frontmatter(rec["_text"]); save_record(rec, join_frontmatter(fm, body))


def set_value(rec, k, v):
    save_record(rec, set_frontmatter_value(rec["_text"], k, v))


def feature_ids():
    if not os.path.isdir(FEATURES): return []
    return sorted(d for d in os.listdir(FEATURES) if re.match(r"F-\d{3,}$", d))


def load_feature(fid):
    p = os.path.join(FEATURES, fid, "feature.md")
    if not os.path.isfile(p): fail(f"{fid}: feature.md missing")
    f = load_record(p, f"{fid}/feature.md")
    if not isinstance(f.get("tickets"), list): f["tickets"] = []
    return f


def note(tid, text):
    append(os.path.join(ROOT, tid, "notes.md"), f"- {now()} {text}\n")


def open_questions(t):
    s = section(t["_body"], "Open questions")
    if s is None: return ["(the Open questions section is missing)"]
    qs = [l.strip() for l in s.strip().splitlines() if l.strip()]
    return [] if qs and qs[0].lower() in ("none", "none.") else (qs or ["(the Open questions section is empty; write None.)"])


def eval_path(tid):
    return os.path.join(ROOT, tid, "eval.md")


def eval_rows(tid):
    if not os.path.isfile(eval_path(tid)): return None
    return [[c.strip() for c in r.strip("|").split("|")] for r in read(eval_path(tid)).splitlines() if re.match(r"^\|\s*\d+\s*\|", r)]


def owns_overlap(a, b):
    return any(under(x, y) or under(y, x) for x in a for y in b)


# ---------------------------------------------------------------- rules

def validate(tid, allt, target=None):
    """The problems that keep a ticket from the target status (default: its own). Returns a list; prints nothing."""
    t = allt[tid]; problems = []; status = target or t.get("status")
    rows = eval_rows(tid)
    if rows is None: problems.append("eval.md missing")
    elif not rows: problems.append("eval.md has no numbered check rows")
    else:
        for cells in rows:
            if len(cells) < 4 or not cells[2] or not cells[3]: problems.append(f"eval row {cells[0]} lacks a how-to-verify or an evidence file")
    for h in RD_HEADINGS:
        n = heading_count(t["_body"], h)
        if n != 1: problems.append(f"rd.md must have the heading '## {h}' exactly once (found {n})")
    if t.get("status") not in STATUSES: problems.append(f"status '{t.get('status')}' is not one of {STATUSES}")
    if t.get("mode") not in ("solo", "team"): problems.append("mode must be solo or team")
    if t.get("kind") not in KINDS: problems.append(f"kind must be one of {KINDS}")
    if t.get("risk") not in RISKS: problems.append(f"risk must be one of {RISKS}")
    if not t.get("deliverable"): problems.append("deliverable is empty: name the output a reader opens")
    if not t.get("owns"): problems.append("owns is empty: name the paths the work may change")
    if any(under(o, "tickets") or norm(o) == "." for o in t.get("owns", [])): problems.append("owns must not include tickets/ or the whole repository")
    for r in t.get("reviews", []):
        if r not in SURFACES: problems.append(f"review '{r}' is not one of {SURFACES}")
    if t.get("risk") in ("medium", "high") and not t.get("reviews"): problems.append(f"risk {t.get('risk')} needs at least one review surface")
    for d in t.get("depends", []):
        if d not in allt: problems.append(f"depends on unknown ticket {d}")
    if open_questions(t) and status in ("ready", "running"): problems.append("has open questions; decide them first (tickets.py decide, then resolve)")
    if t.get("risk") == "high" and not re.search(r"stops? for a person|needs a person|escalat", t["_body"], re.I):
        problems.append("risk is high but the ticket does not say where it stops for a person")
    if t.get("feature"):
        if not os.path.isdir(os.path.join(FEATURES, t["feature"])): problems.append(f"feature {t['feature']} does not exist")
        elif tid not in load_feature(t["feature"])["tickets"]: problems.append(f"feature {t['feature']} does not list {tid} (tickets.py new --feature keeps the two in step)")
    def visit(n, path):
        if n in path: problems.append("dependency cycle: " + " -> ".join(path + [n])); return
        for d in allt.get(n, {}).get("depends", []):
            if d in allt: visit(d, path + [n])
    visit(tid, [])
    return problems


def start_blockers(tid, allt, c):
    """Why a ready ticket cannot start now. Shared by `status running` and `next` so the two never disagree."""
    t = allt[tid]; why = []
    if c["paused"]: why.append("CONFIG.md says paused: true")
    for d in t.get("depends", []):
        if d in allt and allt[d].get("status") != "done": why.append(f"depends on {d}, which is {allt[d].get('status')}")
    running = [o for o, ot in allt.items() if ot.get("status") == "running"]
    if len(running) >= c["concurrency"]: why.append(f"concurrency {c['concurrency']} reached ({', '.join(running)})")
    for o in running:
        if owns_overlap(t.get("owns", []), allt[o].get("owns", [])): why.append(f"shares owned paths with running ticket {o}")
    return why


def set_feature_status(f, new):
    if new not in FEATURE_STATUSES: fail(f"feature status must be one of {FEATURE_STATUSES}")
    if f.get("status") != new: set_value(f, "status", new)
    if new == "accepted" and not f.get("accepted"): set_value(f, "accepted", now("%Y-%m-%d"))


def feature_rollup(fid, allt):
    """The feature's status follows its tickets: any running → running; all done → review. Blocked tickets hold it at running and show on the board."""
    f = load_feature(fid); ts = [allt[x] for x in f["tickets"] if x in allt]
    if not ts: return
    if all(x.get("status") == "done" for x in ts) and f.get("status") not in ("review", "accepted"):
        set_feature_status(f, "review"); print(f"{fid}: every ticket is done -> review (next: tickets.py feature summary {fid})")
    elif any(x.get("status") in ("running", "review", "blocked") for x in ts) and f.get("status") in ("proposed", "decomposed", "rework", "accepted"):
        set_feature_status(f, "running")


# ---------------------------------------------------------------- the board (a view)

def write_board(allt):
    c = config()
    lines = ["# Board", "", f"Source of truth is each ticket's `rd.md` frontmatter; this file is the view. Integration branch `{c['branch']}` · promote `{c['promote']}` · concurrency {c['concurrency']}" + (" · **paused**" if c["paused"] else ""), "",
             "| Ticket | Feature | Title | Status | Kind | Risk | Reviews | Depends | Owns | Budget (min) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for tid in sorted(allt):
        t = allt[tid]; budget = t.get("budget") if isinstance(t.get("budget"), dict) else {}
        lines.append(f"| {tid} | {t.get('feature','')} | {t.get('title','')} | {t.get('status','')} | {t.get('kind','')} | {t.get('risk','')} | {', '.join(t.get('reviews',[]))} | {', '.join(t.get('depends',[]))} | {', '.join(t.get('owns',[]))} | {budget.get('minutes','')} |")
    lines += ["", "## Waiting on a person", "", "Only what the panel could not settle: no consensus, an irreversible step, or a decision a person made that would be reversed.", "", "| Ticket | Why | Since |", "|---|---|---|"]
    for tid in sorted(allt):
        t = allt[tid]
        if t.get("status") == "blocked":
            blk = [l for l in (section(t["_body"], "Blocked") or "").strip().splitlines() if l.strip()]
            lines.append(f"| {tid} | {blk[-1].lstrip('- ') if blk else 'see notes.md'} | |")
    feats = feature_ids()
    if feats:
        lines += ["", "## Features", "", "| Feature | Title | Status | Tickets done | Summary |", "|---|---|---|---|---|"]
        for fid in feats:
            f = load_feature(fid); ts = [allt[x] for x in f["tickets"] if x in allt]
            done = sum(1 for x in ts if x.get("status") == "done")
            lines.append(f"| {fid} | {f.get('title','')} | {f.get('status','')} | {done}/{len(ts)} | {'features/' + fid + '/summary.md' if os.path.isfile(os.path.join(FEATURES, fid, 'summary.md')) else ''} |")
    lines += ["", "Run log: `tickets/RUN.md` · Decisions: `tickets/DECISIONS.md` · Dashboard: `tickets.py dashboard`", ""]
    write(os.path.join(ROOT, "BOARD.md"), "\n".join(lines))


def ensure_root():
    os.makedirs(FEATURES, exist_ok=True)
    for name in SHARED:
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            src = os.path.join(TEMPLATES, name)
            if os.path.exists(src): shutil.copy(src, p)
            elif name == "INBOX.md": write(p, "# Inbox\n\nTwo-line notes from workers about problems outside their ticket. The reproducer turns these into draft tickets.\n")
    sdir = os.path.join(ROOT, SCORERS_DIR); tdir = os.path.join(TEMPLATES, "scorers")
    if os.path.isdir(tdir):
        os.makedirs(sdir, exist_ok=True)
        for name in os.listdir(tdir):
            if not os.path.exists(os.path.join(sdir, name)): shutil.copy(os.path.join(tdir, name), os.path.join(sdir, name))
    gi = os.path.join(ROOT, ".gitignore")
    if not os.path.exists(gi): write(gi, "dashboard.html\n.pr-*.pending\n.lock\n*.tmp\n")


# ---------------------------------------------------------------- creating things (functions return ids; commands print them)

def new_ticket(title, *, owns, deliverable, kind="code", mode="solo", depends="", risk="low", feature="", reviews=""):
    ensure_root(); title = one_line(title, "title")
    if feature and not os.path.isdir(os.path.join(FEATURES, feature)): fail(f"feature {feature} does not exist")
    ids = ticket_ids(); tid = f"T-{(int(ids[-1][2:]) + 1) if ids else 1:03d}"
    folder = os.path.join(ROOT, tid); os.makedirs(os.path.join(folder, "evidence"))
    rd = template("rd.md").replace("T-001", tid)
    rd = re.sub(rf"^# {tid} .*$", lambda m: f"# {tid} {title}", rd, count=1, flags=re.M)
    for k, v in (("title", title), ("mode", mode), ("risk", risk), ("kind", kind), ("deliverable", deliverable or ""), ("feature", feature or "")):
        rd = set_frontmatter_value(rd, k, v)
    rd = set_frontmatter_list(rd, "owns", parse_list(owns))          # no placeholder survives: empty when not given, so validate reports it
    rd = set_frontmatter_list(rd, "depends", parse_list(depends))
    rd = set_frontmatter_value(rd, "reviews", "[" + ", ".join(parse_list(reviews)) + "]")
    write(os.path.join(folder, "rd.md"), rd)
    write(eval_path(tid), template("eval.md").replace("T-001", tid))
    if feature:
        f = load_feature(feature)
        if tid not in f["tickets"]: save_record(f, set_frontmatter_list(f["_text"], "tickets", f["tickets"] + [tid]))
        feature_rollup(feature, load_all())
    note(tid, "created")
    return tid


def new_feature(title, *, request="", requested_by=""):
    ensure_root(); title = one_line(title, "title")
    ids = feature_ids(); fid = f"F-{(int(ids[-1][2:]) + 1) if ids else 1:03d}"
    text = template("feature.md").replace("F-001", fid)
    text = re.sub(rf"^# {fid} .*$", lambda m: f"# {fid} {title}", text, count=1, flags=re.M)
    for k, v in (("title", title), ("requested_by", one_line(requested_by, "requested-by")), ("requested", now("%Y-%m-%d"))): text = set_frontmatter_value(text, k, v)
    if request: text = replace_section(text, "Request", quoted(request))
    write(os.path.join(FEATURES, fid, "feature.md"), text)
    write(os.path.join(FEATURES, fid, "review.md"), template("review.md").replace("F-001", fid))
    return fid


def decisions_path():
    return os.path.join(ROOT, "DECISIONS.md")


def parse_decisions(text=None):
    p = decisions_path()
    if text is None:
        if not os.path.isfile(p): return []
        text = read(p)
    out = []
    for m in re.finditer(r"^## (D-\d+) · (\S+) · (\S+) · (\S+) · (\S+)\s*\n(.*?)(?=^## D-|\Z)", text, re.S | re.M):
        d = {"id": m.group(1), "date": m.group(2), "ticket": m.group(3), "by": m.group(4), "level": m.group(5)}
        for line in m.group(6).splitlines():
            mm = re.match(r"^- (\w[\w ]*): ?(.*)$", line.strip())
            if mm: d[mm.group(1).strip().lower().replace(" ", "_")] = mm.group(2).strip()
        out.append(d)
    return out


def decide(tid, *, question, decided, why, by, options="", level="standard", precedent="", dissent="", reversible="yes", overrides=""):
    """Append one entry and, for an override, mark the old one — built in memory and written once."""
    ensure_root()
    if not ID_RE.match(tid): fail(f"'{tid}' is not a ticket or feature id")
    fields = {k: one_line(v, f"--{k}") for k, v in (("question", question), ("decided", decided), ("why", why), ("options", options), ("precedent", precedent), ("dissent", dissent))}
    if by == "council" and level == "trivial": fail("a trivial question is the worker's to decide (--by worker); a panel is for standard or high")
    text = read(decisions_path()) if os.path.isfile(decisions_path()) else ""
    ds = parse_decisions(text)
    if overrides:
        old = next((d for d in ds if d["id"] == overrides), None)
        if not old: fail(f"unknown decision {overrides}")
        if old["by"] == "person" and by != "person": fail(f"{overrides} was a person's decision; only a person's rework overrides it (reversing a person is an escalation)")
    did = f"D-{(max(int(d['id'][2:]) for d in ds) + 1) if ds else 1:03d}"
    entry = (f"\n## {did} · {now('%Y-%m-%d')} · {tid} · {by} · {level}\n"
             f"- Question: {fields['question']}\n- Options: {fields['options'] or 'not listed'}\n- Decided: {fields['decided']}\n- Why: {fields['why']}\n"
             f"- Precedent: {fields['precedent'] or 'none'}\n- Dissent: {fields['dissent'] or 'none'}\n- Reversible: {reversible}\n")
    if overrides:
        entry += f"- Overrides: {overrides}\n"
        text = re.sub(rf"(^## {re.escape(overrides)} · .*?)(?=^## D-|\Z)", lambda m: m.group(1).rstrip("\n") + f"\n- Overridden by: {did}\n\n", text, count=1, flags=re.S | re.M)
    write(decisions_path(), text.rstrip("\n") + "\n" + entry)
    if tid.startswith("T-") and os.path.isdir(os.path.join(ROOT, tid)): note(tid, f"{did} ({by}): {fields['decided']}")
    return did


# ---------------------------------------------------------------- commands: tickets

def cmd_init(a):
    ensure_root(); print("tickets/ ready:", ", ".join(SHARED), "features/")


def cmd_config(a):
    print(json.dumps(config(), indent=2))


def cmd_new(a):
    tid = new_ticket(a.title, owns=a.owns, deliverable=a.deliverable, kind=a.kind, mode=a.mode, depends=a.depends, risk=a.risk, feature=a.feature, reviews=a.reviews)
    print(tid); print(f"created tickets/{tid}/ (status draft). Fill rd.md and eval.md, then: tickets.py ready {tid}")


def cmd_show(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    print(allt[a.id]["_text"])
    if os.path.isfile(os.path.join(ROOT, a.id, "notes.md")): print("## notes.md\n" + read(os.path.join(ROOT, a.id, "notes.md")))


def cmd_validate(a):
    allt = load_all(); ids = [a.id] if a.id else sorted(allt)
    if a.id and a.id not in allt: fail(f"unknown ticket {a.id}")
    bad = 0
    for tid in ids:
        problems = validate(tid, allt); bad += bool(problems)
        print(f"{tid}: " + ("ok" if not problems else "\n  - " + "\n  - ".join(problems)))
    sys.exit(2 if bad else 0)


def cmd_status(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    t = allt[a.id]; c = config(); cur = t.get("status")
    if a.status not in TRANSITIONS.get(cur, set()): fail(f"{a.id} is {cur}; it cannot go to {a.status} (allowed: {', '.join(sorted(TRANSITIONS.get(cur, []))) or 'none'})")
    if a.status in ("ready", "running"):
        problems = validate(a.id, allt, target=a.status)
        if problems: fail(f"{a.id} cannot be {a.status}:\n  - " + "\n  - ".join(problems))
    if a.status == "running":
        why = start_blockers(a.id, allt, c)
        if why: fail(f"{a.id} cannot start: " + "; ".join(why))
    if a.status == "done":
        word, why = compute_verdict(a.id, allt)
        if word != "approve": fail(f"{a.id} cannot be done: {why}")
    if a.status == "blocked" and not a.why: fail("blocked needs --why: the question or failure a person must see")
    body = t["_body"]
    if a.status == "blocked": body = replace_section(body, "Blocked", ((section(body, "Blocked") or "").strip() + f"\n- {now()}: {one_line(a.why, '--why')}").strip())
    fm, _ = split_frontmatter(t["_text"])
    save_record(t, set_frontmatter_value(join_frontmatter(fm, body), "status", a.status))
    note(a.id, f"status -> {a.status}" + (f": {a.why}" if a.why else ""))
    if t.get("feature"): feature_rollup(t["feature"], load_all())
    print(f"{a.id}: {a.status}")


def cmd_next(a):
    allt = load_all(); c = config()
    if c["paused"]: print("paused (tickets/CONFIG.md)"); return
    running = [t for t in allt.values() if t.get("status") == "running"]
    slots = max(c["concurrency"] - len(running), 0)
    out = []
    for tid, t in sorted(allt.items()):
        if t.get("status") != "ready" or start_blockers(tid, allt, c): continue
        if any(owns_overlap(t.get("owns", []), allt[o].get("owns", [])) for o in out): continue
        out.append(tid)
    if not out: print("nothing runnable: no ready ticket has its dependencies done and its paths free"); return
    for tid in out[:slots]:
        t = allt[tid]; budget = t.get("budget") if isinstance(t.get("budget"), dict) else {}
        print(f"{tid} ({t.get('kind')}, {t.get('mode')}, risk {t.get('risk')}, {budget.get('minutes','?')} min): {t.get('title')}")
    if len(out) > slots: print(f"({len(out) - slots} more wait for a slot: concurrency {c['concurrency']})")


def cmd_log(a):
    vals = {"Ticket": a.id, "Attempt": a.attempt, "Ended": now(), "Minutes": a.minutes, "Questions asked": a.questions, "Returned by checker": a.returned,
            "Defects found after acceptance": a.defects, "Restarts recovered": a.restarts, "Tokens (if known)": a.tokens or "", "Role": a.role}
    append(os.path.join(ROOT, "RUN.md"), "| " + " | ".join(str(vals.get(c, "")).replace("|", "/") for c in RUN_COLS) + " |\n"); print("logged", a.id)


# ---------------------------------------------------------------- commands: features

def cmd_feature_new(a):
    fid = new_feature(a.title, request=a.request, requested_by=a.requested_by)
    print(fid); print(f"created tickets/features/{fid}/ (status proposed). Decompose it: tickets.py new \"...\" --feature {fid} --owns ... --deliverable ...")


def cmd_feature_status(a):
    set_feature_status(load_feature(a.id), a.status); print(f"{a.id}: {a.status}")


def cmd_feature_list(a):
    allt = load_all()
    for fid in feature_ids():
        f = load_feature(fid); done = sum(1 for x in f["tickets"] if x in allt and allt[x].get("status") == "done")
        print(f"{fid} [{f.get('status')}] {f.get('title')} — {done}/{len(f['tickets'])} tickets done")


def cmd_feature_show(a):
    print(load_feature(a.id)["_text"])


def write_summary(fid):
    f = load_feature(fid); allt = load_all()
    ts = {x: allt[x] for x in f["tickets"] if x in allt}
    ds = [d for d in parse_decisions() if d.get("ticket") in set(ts) | {fid}]
    def prio(d):  # what a reviewer should look at first
        if d.get("overridden_by"): return 9
        if d.get("by") == "person": return 8
        if d.get("precedent", "none").lower().startswith("none") and d.get("by") != "worker": return 0
        if d.get("dissent", "none").lower() not in ("none", "none.", ""): return 1
        if d.get("by") == "worker": return 2
        return 3
    novel = [d for d in ds if prio(d) == 0]; diss = [d for d in ds if prio(d) == 1]; wk = [d for d in ds if prio(d) == 2]; prec = [d for d in ds if prio(d) == 3]; esc = [d for d in ds if d.get("by") == "person"]
    L = [f"# {fid} {f.get('title','')} · summary", "", f"Written {now()} from the ticket files. Feature status: {f.get('status')}. Read the first two sections first; they hold what is most likely to need rework.", "",
         "## What was built", "", "_(summarizer: three to six sentences from the reader's side — what they can now do, see or know; link the deliverables)_", ""]
    L += ["## Decisions to review first (no precedent to lean on)", ""]
    L += [f"- **{d['id']}** ({d['ticket']}): {d['question']} → **{d['decided']}** — {d['why']}" + (f" · dissent: {d['dissent']}" if d.get('dissent','none').lower() not in ('none','none.','') else "") for d in novel] or ["- none"]
    L += ["", "## Decisions with recorded dissent", ""]
    L += [f"- **{d['id']}** ({d['ticket']}): {d['question']} → **{d['decided']}** · dissent: {d['dissent']}" for d in diss] or ["- none"]
    L += ["", "## Assumptions workers made on their own", ""]
    L += [f"- **{d['id']}** ({d['ticket']}): {d['question']} → {d['decided']}" for d in wk] or ["- none"]
    L += ["", "## Decisions that followed precedent", ""]
    L += [f"- {d['id']} ({d['ticket']}): {d['decided']} · follows {d['precedent']}" for d in prec] or ["- none"]
    if esc: L += ["", "## Decisions a person made during the run", ""] + [f"- {d['id']} ({d['ticket']}): {d['question']} → {d['decided']}" for d in esc]
    L += ["", "## Tickets", "", "| Ticket | Title | Status | Risk | Checker | Votes | Evidence |", "|---|---|---|---|---|---|---|"]
    for tid, t in ts.items():
        ev = os.path.join(ROOT, tid, "evidence"); files = sorted(os.listdir(ev)) if os.path.isdir(ev) else []
        L.append(f"| {tid} | {t.get('title','')} | {t.get('status','')} | {t.get('risk','')} | {checker_verdict(tid) or ''} | {', '.join(v['role'] + ':' + v['vote'] for v in parse_votes(tid))} | {', '.join(files)} |")
    L += ["", "## What to look at", "", "_(summarizer: the three to five places a reviewer should open — a screen, a file, a test output — each with its path or evidence file)_", ""]
    L += ["## Run", "", stats_text(set(ts)), ""]
    L += ["## How to rework", "", f"Write what is wrong in `tickets/features/{fid}/review.md` (one line per item, name the decision id where there is one), then say \"factory: rework {fid}\" — or run `tickets.py rework {fid} --note \"...\" [--overrides D-0xx]`. A person's rework overrides the panel's decision and becomes the precedent the next panel follows.", ""]
    write(os.path.join(FEATURES, fid, "summary.md"), "\n".join(L))
    print(f"wrote tickets/features/{fid}/summary.md ({len(ds)} decisions, {len(ts)} tickets)")


def cmd_feature_summary(a):
    write_summary(a.id)


# ---------------------------------------------------------------- commands: decisions

def cmd_precedent(a):
    ds = parse_decisions(); by_id = {d["id"]: d for d in ds}
    words = {w for w in re.findall(r"[a-z0-9]{3,}", a.words.lower())} - {"the", "and", "for", "with", "should", "use", "that", "this", "what", "which"}
    scored = []
    for d in ds:
        hay = " ".join(d.get(k, "") for k in ("question", "options", "decided", "why")).lower()
        o = by_id.get(d.get("overrides", ""))
        if o: hay += " " + " ".join(o.get(k, "") for k in ("question", "options")).lower()  # an override answers the question it overturned
        score = sum(1 for w in words if w in hay)
        if score: scored.append((1 if d.get("overridden_by") else 0, 0 if d.get("by") == "person" else 1, -score, d))
    scored.sort(key=lambda x: (x[0], x[1], x[2], x[3]["id"]))
    if not scored: print("no precedent found; the panel decides"); return
    for _, _, s, d in scored[:5]:
        flag = " (OVERRIDDEN by " + d["overridden_by"] + ")" if d.get("overridden_by") else ""
        print(f"{d['id']} [{d['by']}, {d['ticket']}, matches {-s}]{flag}: {d.get('question','')} -> {d.get('decided','')} — {d.get('why','')}")


def cmd_decide(a):
    print(decide(a.id, question=a.question, decided=a.decided, why=a.why, by=a.by, options=a.options, level=a.level, precedent=a.precedent, dissent=a.dissent, reversible=a.reversible, overrides=a.overrides))


def cmd_resolve(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    d = next((x for x in parse_decisions() if x["id"] == a.decision), None)
    if not d: fail(f"unknown decision {a.decision}")
    t = allt[a.id]; qs = [q for q in open_questions(t) if not q.startswith("(")]
    if not qs: fail(f"{a.id} has no open questions")
    if a.number:
        if not 1 <= a.number <= len(qs): fail(f"--number must be 1..{len(qs)}")
        removed = [qs[a.number - 1]]; left = [q for i, q in enumerate(qs, 1) if i != a.number]
    elif a.all or len(qs) == 1: removed, left = qs, []
    else: fail(f"{a.id} has {len(qs)} open questions: say which with --number N, or --all")
    body = replace_section(t["_body"], "Open questions", "\n".join(left) if left else "None.")
    ctx = (section(body, "Context the worker needs") or "").rstrip("\n")
    body = replace_section(body, "Context the worker needs", ctx + f"\n- Decided {d['date']} ({d['id']}, {d['by']}): {d['decided']} — {d['why']}")
    save_body(t, body); note(a.id, f"resolved {len(removed)} question(s) with {d['id']}")
    print(f"{a.id}: {len(removed)} question(s) resolved by {d['id']}; {len(left)} left")


# ---------------------------------------------------------------- commands: gate, votes, verdict

def worktree_for(tid):
    r = sh(["git", "worktree", "list", "--porcelain"], check=False)
    for block in r.stdout.strip().split("\n\n"):
        lines = block.splitlines()
        if any(l.strip() == f"branch refs/heads/ticket/{tid}" for l in lines): return lines[0].split(" ", 1)[1]
    return None


def allowed_in_tickets(path, tid):
    return under(path, f"tickets/{tid}/evidence") or norm(path) == f"tickets/{tid}/notes.md"


def cmd_gate(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    d = a.worktree or worktree_for(a.id) or MAIN; c = config()
    ev = os.path.join(ROOT, a.id, "evidence"); os.makedirs(ev, exist_ok=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
    out = [f"gate for {a.id} in {d} at {now()}", f"HEAD: {head}", ""]; shown = []; ok = True
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=d, capture_output=True, text=True).stdout.strip()
    if dirty:
        line = "FAIL: the worktree has uncommitted changes; the gate judges commits only:\n" + dirty[:800]; out.append(line); shown.append(line); ok = False
    # the checks come from the integration branch, so a branch cannot edit the gate it is judged by
    src = subprocess.run(["git", "show", f"{c['branch']}:tickets/checks.sh"], cwd=d, capture_output=True, text=True)
    if src.returncode == 0 and src.stdout.strip():
        checks = os.path.join(ev, ".checks.sh"); write(checks, src.stdout)
        env = {**os.environ, "FACTORY_BRANCH": c["branch"]}
        r = subprocess.run(["bash", checks], cwd=d, capture_output=True, text=True, env=env)
        line = f"$ bash tickets/checks.sh (from {c['branch']})  (exit {r.returncode})"; out += [line, r.stdout[-6000:], r.stderr[-3000:]]; shown.append(line)
        if r.returncode != 0:  # one re-run with nothing changed tells a flaky check from a failing one
            r2 = subprocess.run(["bash", checks], cwd=d, capture_output=True, text=True, env=env)
            if r2.returncode == 0:
                out += ["", "re-run with no change passed: FLAKY check; counted as a pass and sent to INBOX.md"]; shown.append("flaky: passed on re-run; noted in INBOX.md")
                append(os.path.join(ROOT, "INBOX.md"), f"- {now()} flaky check in tickets/checks.sh seen on {a.id}: failed once, passed on re-run (see tickets/{a.id}/evidence/gate.txt)\n")
            else:
                out += ["", f"re-run also failed (exit {r2.returncode})"]; ok = False
                shown += (r.stderr or r.stdout).strip().splitlines()[-6:]
        os.remove(checks)
    else:
        line = f"FAIL: no tickets/checks.sh on {c['branch']}; the gate has nothing to run (tickets.py init writes one; fit it to the project and commit it)"; out.append(line); shown.append(line); ok = False
    owns = allt[a.id].get("owns", [])
    r = subprocess.run(["git", "diff", "--name-only", f"{c['branch']}...HEAD"], cwd=d, capture_output=True, text=True)
    if r.returncode == 0:
        files = r.stdout.split()
        stray = [f for f in files if not (any(under(f, o) for o in owns) or allowed_in_tickets(f, a.id))]
        line = f"$ git diff --name-only {c['branch']}...HEAD -> {len(files)} files; outside owns: {', '.join(stray) if stray else 'none'}"
        out += ["", line]; shown.append(line); ok = ok and not stray
        write(os.path.join(ev, "diff-files.txt"), r.stdout)
    else:
        line = f"FAIL: could not diff against {c['branch']}: {r.stderr.strip()}"; out += ["", line]; shown.append(line); ok = False
    out += ["", "RESULT: " + ("PASS" if ok else "FAIL")]
    write(os.path.join(ev, "gate.txt"), "\n".join(out)); note(a.id, f"gate {'PASS' if ok else 'FAIL'} at {head[:8]}")
    print("\n".join(shown + ["RESULT: " + ("PASS" if ok else "FAIL"), f"details: tickets/{a.id}/evidence/gate.txt"])); sys.exit(0 if ok else 2)


def gate_state(tid):
    """('pass'|'fail'|'missing'|'stale', reason) from evidence/gate.txt and the branch head."""
    p = os.path.join(ROOT, tid, "evidence", "gate.txt")
    if not os.path.isfile(p): return "missing", "the gate has not run (no evidence/gate.txt); run tickets.py gate first"
    lines = [l for l in read(p).splitlines() if l.strip()]
    if not lines or lines[-1].strip() != "RESULT: PASS": return "fail", "the gate did not pass (evidence/gate.txt)"
    m = re.search(r"^HEAD: ([0-9a-f]{7,40})$", "\n".join(lines[:3]), re.M)
    r = subprocess.run(["git", "rev-parse", f"ticket/{tid}"], cwd=MAIN, capture_output=True, text=True)
    if m and r.returncode == 0 and r.stdout.strip() != m.group(1): return "stale", f"the gate passed at {m.group(1)[:8]} but ticket/{tid} is now at {r.stdout.strip()[:8]}; run tickets.py gate again"
    return "pass", "gate passed"


def parse_votes(tid):
    if not os.path.isfile(eval_path(tid)): return []
    m = FRONTMATTER_RE.match(read(eval_path(tid))); text = m.group(2) if m else read(eval_path(tid))
    votes = []
    for r in (section(text, "Approval") or "").splitlines():
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[1] in ("approve", "changes"): votes.append({"role": cells[0], "vote": cells[1], "why": cells[2], "when": cells[3]})
    return votes


def checker_verdict(tid):
    """The verdict line inside the Checker's verdict section, and only with a named checker."""
    if not os.path.isfile(eval_path(tid)): return None
    s = section(read(eval_path(tid)), "Checker's verdict") or ""
    m = VERDICT_RE.search(s); who = CHECKED_BY_RE.search(s)
    return m.group(1) if m and who else None


def cmd_vote(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    if allt[a.id].get("status") not in ("running", "review"): fail(f"{a.id} is {allt[a.id].get('status')}; votes are cast while a ticket is running or in review")
    role = a.role.strip().lower(); allowed = allt[a.id].get("reviews", []) + ["arbiter"]
    if not re.match(r"^[a-z][a-z0-9-]*$", role) or role not in allowed: fail(f"role '{a.role}' is not one of this ticket's reviews ({', '.join(allowed)})")
    text = read(eval_path(a.id))
    if section(text, "Approval") is None: text = text.rstrip("\n") + "\n\n## Approval\n| Role | Verdict | Why | When |\n|---|---|---|---|\n"
    text = re.sub(r"(^## Approval\s*\n\| Role.*?\n\|---.*?\n(?:\|.*\n)*)", lambda m: m.group(1) + f"| {role} | {a.vote} | {one_line(a.why, '--why').replace('|', '/')} | {now()} |\n", text, count=1, flags=re.S | re.M)
    write(eval_path(a.id), text); note(a.id, f"vote {role}: {a.vote}"); print(f"{a.id}: {role} -> {a.vote}")


EXIT = {"approve": 0, "changes": 2, "escalate": 3}


def compute_verdict(tid, allt):
    """(word, reason) from the gate, the checker's verdict, the listed reviewers' votes and the rule for the ticket's risk."""
    t = allt[tid]; rule = config()["approval"].get(t.get("risk"), "unanimous")  # an unknown risk gets the strictest rule
    state, why = gate_state(tid)
    if state != "pass": return "changes", why
    cv = checker_verdict(tid)
    if cv != "accepted": return "changes", f"the checker's verdict is '{cv or 'missing or unsigned'}'; approval starts from an accepted evaluation with a named checker"
    wanted = t.get("reviews", []); votes = {}
    for v in parse_votes(tid): votes[v["role"]] = v  # the last vote per role stands
    if rule == "checker": return "approve", "low risk, checker accepted" + (f" ({len(votes)} reviewer votes recorded)" if votes else "")
    missing = [r for r in wanted if r not in votes]
    if missing: return "changes", f"waiting for reviews from {', '.join(missing)}"
    yes = [r for r in wanted if votes[r]["vote"] == "approve"]; no = [r for r in wanted if votes[r]["vote"] == "changes"]
    if rule == "unanimous":
        if no: return "escalate", f"high risk needs every reviewer; changes requested by {', '.join(no)}"
        return "approve", f"unanimous ({', '.join(yes) or 'checker only'})"
    if not wanted: return "approve", "checker accepted and no reviewers listed"
    if len(yes) > len(no): return "approve", f"majority {len(yes)}-{len(no)}" + (f"; dissent from {', '.join(no)} stays in eval.md" if no else "")
    if len(yes) == len(no):
        arb = votes.get("arbiter")
        if arb: return ("approve" if arb["vote"] == "approve" else "changes"), f"split {len(yes)}-{len(no)}; the arbiter ruled {arb['vote']}: {arb['why']}"
        return "escalate", f"split {len(yes)}-{len(no)}; the arbiter rules on the diff and the reasons"
    return "changes", f"{', '.join(no)} request changes"


def cmd_verdict(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    word, why = compute_verdict(a.id, allt); print(f"{word}: {why}"); sys.exit(EXIT[word])


# ---------------------------------------------------------------- commands: rework

def cmd_rework(a):
    allt = load_all(); ensure_root(); note_text = one_line(a.note, "--note")
    if a.id.startswith("F-"):
        f = load_feature(a.id); src = [allt[x] for x in f["tickets"] if x in allt]; feature = a.id; deliverable = ""
        if not src: fail(f"{a.id} has no tickets to rework")
        owns = parse_list(a.owns) if a.owns else sorted({o for t in src for o in t.get("owns", [])})
        risk = a.risk or max((t.get("risk", "low") for t in src), key=RISKS.index)
        kinds = [t.get("kind", "code") for t in src]; kind = a.kind or max(set(kinds), key=kinds.count)
        reviews = sorted({r for t in src for r in t.get("reviews", [])})
        ctx = f"- Rework of {a.id} {f.get('title','')} asked by a person on {now('%Y-%m-%d')}.\n- Their note, verbatim: {note_text}\n- Read tickets/features/{a.id}/summary.md and review.md first."
    elif a.id in allt:
        t = allt[a.id]; feature = t.get("feature", ""); deliverable = t.get("deliverable", "")
        owns = parse_list(a.owns) if a.owns else t.get("owns", []); risk = a.risk or t.get("risk", "low"); kind = a.kind or t.get("kind", "code"); reviews = t.get("reviews", [])
        ctx = f"- Rework of {a.id} {t.get('title','')} asked by a person on {now('%Y-%m-%d')}.\n- Their note, verbatim: {note_text}\n- Read tickets/{a.id}/rd.md, eval.md and notes.md first; keep what the note does not fault."
    else: fail(f"unknown feature or ticket {a.id}")
    tid = new_ticket(f"Rework {a.id}: {short(note_text)}", owns=",".join(owns), deliverable=deliverable, kind=kind, risk=risk, feature=feature, reviews=",".join(reviews))
    t = load(tid); body = replace_section(t["_body"], "Context the worker needs", ctx)
    body = replace_section(body, "Outcome", f"The note below is satisfied and nothing else about {a.id} changes: {note_text}")
    if risk == "high": body = replace_section(body, "Constraints", ((section(body, "Constraints") or "").strip() + "\n- High risk inherited from the source: stops for a person before any irreversible step.").strip())
    save_body(t, body)
    old_q = next((d.get("question", "") for d in parse_decisions() if d["id"] == a.overrides), "") if a.overrides else ""
    did = decide(tid, question=(f"Rework of {a.overrides}: {old_q}" if old_q else f"Rework of {a.id}"), decided=note_text, why="a person reviewed the result and asked for this", by="person", level="standard", reversible="yes", overrides=a.overrides)
    if feature: set_feature_status(load_feature(feature), "rework")
    print(tid); print(f"carries the rework note as {did}" + (f"; {a.overrides} is now overridden" if a.overrides else "") + f". Fill eval.md rows for the note, then: tickets.py ready {tid}")


# ---------------------------------------------------------------- scoring (judges grade evidence, by risk-weighted sampling)

def scorers():
    """tickets/scorers/<name>.md: frontmatter with labels (value, score), passingScore, agents, optional samplingRate."""
    d = os.path.join(ROOT, SCORERS_DIR); out = {}
    if not os.path.isdir(d): return out
    for name in sorted(os.listdir(d)):
        if not name.endswith(".md"): continue
        text = read(os.path.join(d, name)); m = FRONTMATTER_RE.match(text)
        if not m: continue
        fm, body = m.group(1), m.group(2)
        labels = {}
        for lm in re.finditer(r"^  - value: (\S+)\s*\n(?:    description: [^\n]*\n)?    score: ([0-9.]+)", fm, re.M):
            labels[lm.group(1)] = float(lm.group(2))
        meta = parse_frontmatter(re.sub(r"^labels:\n(?:  - .*\n|    .*\n)*", "", fm, flags=re.M))
        out[name[:-3]] = {"labels": labels, "passing": float(meta.get("passingScore") or 1), "agents": meta.get("agents", []) if isinstance(meta.get("agents"), list) else parse_list(meta.get("agents", "")),
                          "sampling": meta.get("samplingRate"), "body": body.strip(), "description": meta.get("description", "")}
    return out


def score_rows():
    p = os.path.join(ROOT, "SCORES.md")
    if not os.path.isfile(p): return []
    rows = []
    for r in read(p).splitlines():
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) >= 6 and re.match(r"T-\d+", cells[0]): rows.append({"ticket": cells[0], "scorer": cells[1], "label": cells[2], "score": cells[3], "passed": cells[4], "why": cells[5], "when": cells[6] if len(cells) > 6 else ""})
    return rows


def due_for_scoring(allt, c):
    """Done tickets with no score yet, chosen by a stable hash against the sampling rate for their risk; reworked tickets always."""
    scored = {r["ticket"] for r in score_rows()}
    overridden_tickets = {d["ticket"] for d in parse_decisions() if d.get("overridden_by")}
    due = []
    for tid, t in sorted(allt.items()):
        if t.get("status") != "done" or tid in scored: continue
        rate = int(c["scoring"].get(t.get("risk", "low"), 25))
        always = tid in overridden_tickets or any(x.get("title", "").startswith(f"Rework {tid}") for x in allt.values())
        bucket = int(tid[2:]) * 37 % 100  # stable: the same ticket is always in or out, whatever the day
        if always or bucket < rate: due.append((tid, "reworked" if always else f"{rate}% sample"))
    return due


def cmd_sample(a):
    allt = load_all(); c = config(); sc = scorers()
    if not sc: print("no scorers in tickets/scorers/ (tickets.py init copies the defaults)"); return
    due = due_for_scoring(allt, c)
    if not due: print("nothing due: every sampled done ticket is scored"); return
    for tid, why in due: print(f"{tid} ({why}): " + ", ".join(sc))


def cmd_score(a):
    allt = load_all(); sc = scorers()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    if a.scorer not in sc: fail(f"unknown scorer '{a.scorer}'; have: {', '.join(sc) or 'none'}")
    labels = sc[a.scorer]["labels"]
    if a.label not in labels: fail(f"label must be one of {', '.join(labels)}")
    val = labels[a.label]; passed = "yes" if val >= sc[a.scorer]["passing"] else "no"
    p = os.path.join(ROOT, "SCORES.md")
    if not os.path.isfile(p): write(p, template("SCORES.md") if os.path.isfile(os.path.join(TEMPLATES, "SCORES.md")) else "# Scores\n\n| Ticket | Scorer | Label | Score | Passed | Why | When |\n|---|---|---|---|---|---|---|\n")
    append(p, f"| {a.id} | {a.scorer} | {a.label} | {val:g} | {passed} | {one_line(a.why, '--why').replace('|', '/')} | {now()} |\n")
    note(a.id, f"scored {a.scorer}: {a.label} ({'pass' if passed == 'yes' else 'FAIL'})")
    if passed == "no": append(os.path.join(ROOT, "INBOX.md"), f"- {now()} score FAIL on {a.id} by {a.scorer}: {a.label} — {one_line(a.why, '--why')}\n")
    print(f"{a.id}: {a.scorer} -> {a.label} ({val:g}, {'pass' if passed == 'yes' else 'FAIL'})")


# ---------------------------------------------------------------- benchmarks (a finished ticket is a replayable task)

def bench_rows():
    p = os.path.join(ROOT, "BENCH.md")
    if not os.path.isfile(p): return []
    rows = []
    for r in read(p).splitlines():
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) >= 6 and re.match(r"T-\d+", cells[0]): rows.append({"ticket": cells[0], "model": cells[1], "passed": cells[2], "minutes": cells[3], "tokens": cells[4], "when": cells[5]})
    return rows


def cmd_bench(a):
    allt = load_all(); c = config(); bdir = os.path.join(ROOT, BENCH_DIR)
    if a.action == "add":
        if a.id not in allt: fail(f"unknown ticket {a.id}")
        t = allt[a.id]
        if t.get("status") != "done": fail(f"{a.id} is {t.get('status')}; a benchmark task is a done ticket")
        r = subprocess.run(["git", "log", "--format=%H", "--grep", f"^{a.id}:", "-n", "1", c["branch"]], cwd=MAIN, capture_output=True, text=True)
        merge = r.stdout.strip()
        if not merge: fail(f"no commit titled '{a.id}: …' on {c['branch']}; was it merged by the merger?")
        base = subprocess.run(["git", "rev-parse", f"{merge}^"], cwd=MAIN, capture_output=True, text=True).stdout.strip()
        d = os.path.join(bdir, a.id); os.makedirs(d, exist_ok=True)
        for f in ("rd.md", "eval.md"): shutil.copy(os.path.join(ROOT, a.id, f), os.path.join(d, f))
        checks = subprocess.run(["git", "show", f"{base}:tickets/checks.sh"], cwd=MAIN, capture_output=True, text=True)
        if checks.returncode == 0: write(os.path.join(d, "checks.sh"), checks.stdout)
        rows = [x for x in run_rows() if x["Ticket"] == a.id and x.get("Role", "worker") in ("worker", "")]
        budget = t.get("budget") if isinstance(t.get("budget"), dict) else {}
        orig = ", ".join(x["Minutes"] + " min, " + (x["Tokens (if known)"] or "tokens unknown") for x in rows) or "not logged"
        write(os.path.join(d, "task.md"), f"# Benchmark task {a.id}: {t.get('title','')}\n\n- Base commit: `{base}` (the integration branch before `{merge[:8]}`)\n- Kind: {t.get('kind')} · risk: {t.get('risk')} · budget: {budget.get('minutes','?')} min · owns: {', '.join(t.get('owns', []))}\n- Original run: {orig}\n\nReplay: `git worktree add -b bench/{a.id}-<model> <path> {base}`, run a worker on `rd.md` from this folder with the model under test, then `tickets.py gate` and the checker against this `eval.md`; record with `tickets.py bench record {a.id} --model <model> --passed <rows passed>/<rows> --minutes N --tokens N`.\n\n## Request\n\n{t['_body'].strip()}\n")
        print(a.id); print(f"benchmark task in tickets/bench/{a.id}/ (base {base[:8]})")
    elif a.action == "list":
        if not os.path.isdir(bdir) or not os.listdir(bdir): print("no benchmark tasks yet: tickets.py bench add T-0xx"); return
        rows = bench_rows()
        for tid in sorted(os.listdir(bdir)):
            runs = [x for x in rows if x["ticket"] == tid]
            print(f"{tid}: {len(runs)} replay(s)" + ("; " + ", ".join(f"{x['model']} {x['passed']} in {x['minutes']} min" for x in runs) if runs else ""))
    elif a.action == "record":
        if not os.path.isdir(os.path.join(bdir, a.id)): fail(f"{a.id} is not a benchmark task (tickets.py bench add {a.id})")
        if not re.match(r"^\d+/\d+$", a.passed): fail("--passed is rows passed over rows, like 7/8")
        p = os.path.join(ROOT, "BENCH.md")
        if not os.path.isfile(p): write(p, template("BENCH.md") if os.path.isfile(os.path.join(TEMPLATES, "BENCH.md")) else "# Benchmarks\n\n| Task | Model | Passed | Minutes | Tokens | When |\n|---|---|---|---|---|---|\n")
        append(p, f"| {a.id} | {a.model} | {a.passed} | {a.minutes} | {a.tokens or ''} | {now()} |\n"); print(f"recorded {a.id} on {a.model}: {a.passed}")
    else: fail("bench action must be add, list or record")


# ---------------------------------------------------------------- commands: stats, dashboard

def run_rows():
    p = os.path.join(ROOT, "RUN.md")
    if not os.path.isfile(p): return []
    rows = []
    for r in read(p).splitlines():
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) >= 9 and re.match(r"T-\d+", cells[0]): rows.append({c: (cells[i] if i < len(cells) else "") for i, c in enumerate(RUN_COLS)})
    return rows


def stats_text(only=None):
    allt = load_all(); ds = parse_decisions(); rows = run_rows()
    if only is not None: allt = {k: v for k, v in allt.items() if k in only}; ds = [d for d in ds if d.get("ticket") in only]; rows = [r for r in rows if r["Ticket"] in only]
    done = [t for t in allt.values() if t.get("status") == "done"]
    mins = [float(r["Minutes"]) for r in rows if re.match(r"^\d+(\.\d+)?$", r["Minutes"])]
    first_pass = sum(1 for r in rows if r["Returned by checker"] == "0")
    by = {}
    for d in ds: by[d["by"]] = by.get(d["by"], 0) + 1
    council = [d for d in ds if d["by"] in ("council", "arbiter")]; overridden = [d for d in council if d.get("overridden_by")]
    votes = [v for t in allt for v in parse_votes(t)]
    c = config(); price = c["price_per_million_tokens"]
    toks = [(r, float(r["Tokens (if known)"])) for r in rows if re.match(r"^\d+(\.\d+)?$", r["Tokens (if known)"] or "")]
    total_tokens = sum(v for _, v in toks)
    by_role = {}
    for r, v in toks: by_role[r.get("Role") or "worker"] = by_role.get(r.get("Role") or "worker", 0) + v
    merged = len(done) or 1
    cost_line = (f"- Tokens logged: {int(total_tokens):,} over {len(toks)} attempts" + (f" = ${total_tokens / 1e6 * price:,.2f} at ${price:g}/M; ${total_tokens / 1e6 * price / merged:,.2f} per merged ticket" if price else " (set price_per_million_tokens in CONFIG.md for money)")
                 + (" · by role: " + ", ".join(f"{k} {100 * v / total_tokens:.0f}%" for k, v in sorted(by_role.items(), key=lambda kv: -kv[1])) if total_tokens else "")) if toks else "- Tokens: none logged (merger: tickets.py log … --tokens N --role worker; panels and reviews log their own)"
    sc = score_rows(); sc_only = [r for r in sc if only is None or r["ticket"] in only]
    per = {}
    for r in sc_only: per.setdefault(r["scorer"], []).append(r["passed"] == "yes")
    score_line = "- Scores: " + (", ".join(f"{k} {sum(v)}/{len(v)} pass" for k, v in sorted(per.items())) if per else "none yet (tickets.py sample, then the scorer role)")
    feats = [load_feature(f) for f in feature_ids()] if only is None else []
    cyc = []
    for f in feats:
        if f.get("requested") and f.get("accepted"):
            try: cyc.append((datetime.date.fromisoformat(f["accepted"]) - datetime.date.fromisoformat(f["requested"])).days)
            except ValueError: pass
    cycle_line = f"- Cycle time, request to accepted: median {sorted(cyc)[len(cyc) // 2]} days over {len(cyc)} features" if cyc else "- Cycle time: no feature accepted yet"
    br = bench_rows()
    bench_line = ("- Benchmarks: " + ", ".join(f"{m} {sum(int(x['passed'].split('/')[0]) for x in br if x['model'] == m)}/{sum(int(x['passed'].split('/')[1]) for x in br if x['model'] == m)} rows" for m in sorted({x['model'] for x in br}))) if br else "- Benchmarks: none replayed yet (tickets.py bench add T-0xx)"
    return "\n".join([
        f"- Tickets: {len(allt)} total, {len(done)} done, {sum(1 for t in allt.values() if t.get('status') == 'blocked')} blocked",
        f"- Attempts logged: {len(rows)}; first-pass (no return by the checker): {first_pass}/{len(rows) or 1} = {100 * first_pass // (len(rows) or 1)}%",
        f"- Minutes per attempt: median {sorted(mins)[len(mins) // 2] if mins else '—'}, total {sum(mins) if mins else '—'}",
        f"- Decisions: {len(ds)} ({', '.join(f'{k} {v}' for k, v in sorted(by.items())) or 'none'})",
        f"- Panel decisions later overridden by a person: {len(overridden)}/{len(council) or 1} = {100 * len(overridden) // (len(council) or 1)}%  (the autonomy health number: high means the panel should escalate earlier in that area)",
        f"- Reviewer votes: {sum(1 for v in votes if v['vote'] == 'approve')} approve, {sum(1 for v in votes if v['vote'] == 'changes')} changes",
        score_line, cost_line, cycle_line, bench_line])


def cmd_stats(a):
    print(stats_text())


def cmd_dashboard(a):
    allt = load_all(); ds = parse_decisions(); c = config(); e = html.escape
    rows = "".join(f"<tr><td>{e(t)}</td><td>{e(str(x.get('feature','')))}</td><td>{e(x.get('title',''))}</td><td class='s-{e(x.get('status',''))}'>{e(x.get('status',''))}</td><td>{e(x.get('risk',''))}</td><td>{e(', '.join(x.get('owns',[])))}</td></tr>" for t, x in sorted(allt.items()))
    feats = "".join(f"<li><b>{e(fid)}</b> {e(load_feature(fid).get('title',''))} — {e(load_feature(fid).get('status',''))}" + (f" · <a href='features/{fid}/summary.md'>summary</a>" if os.path.isfile(os.path.join(FEATURES, fid, 'summary.md')) else "") + "</li>" for fid in feature_ids())
    decs = "".join(f"<tr><td>{e(d['id'])}</td><td>{e(d['date'])}</td><td>{e(d['ticket'])}</td><td>{e(d['by'])}</td><td>{e(d.get('question',''))}</td><td>{e(d.get('decided',''))}</td><td>{e(d.get('dissent','none'))}</td><td>{e(d.get('overridden_by',''))}</td></tr>" for d in reversed(ds))
    page = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Factory board</title>
<style>:root{{--bg:#fff;--fg:#1a1a1a;--mute:#666;--line:#ddd;--ok:#2a7;--warn:#c80;--bad:#c33}}@media(prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--mute:#999;--line:#333}}}}
body{{font:14px/1.5 system-ui,sans-serif;margin:0;padding:16px;background:var(--bg);color:var(--fg)}}table{{border-collapse:collapse;width:100%;margin:8px 0 24px}}td,th{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}th{{color:var(--mute);font-weight:600}}
.s-done{{color:var(--ok)}}.s-blocked{{color:var(--bad)}}.s-running,.s-review{{color:var(--warn)}}pre{{white-space:pre-wrap;background:rgba(127,127,127,.08);padding:12px;border-radius:8px}}h1,h2{{margin:16px 0 4px}}small{{color:var(--mute)}}</style></head><body>
<h1>Factory board <small>{e(now())} · branch {e(str(c['branch']))} · promote {e(str(c['promote']))} · concurrency {c['concurrency']}{' · PAUSED' if c['paused'] else ''}</small></h1>
<h2>Features</h2><ul>{feats or '<li>none yet</li>'}</ul>
<h2>Tickets</h2><table><tr><th>Ticket</th><th>Feature</th><th>Title</th><th>Status</th><th>Risk</th><th>Owns</th></tr>{rows}</table>
<h2>Run</h2><pre>{e(stats_text())}</pre>
<h2>Decisions <small>newest first</small></h2><table><tr><th>Id</th><th>Date</th><th>Ticket</th><th>By</th><th>Question</th><th>Decided</th><th>Dissent</th><th>Overridden by</th></tr>{decs}</table>
</body></html>"""
    write(os.path.join(ROOT, "dashboard.html"), page); print("wrote tickets/dashboard.html")


# ---------------------------------------------------------------- commands: github

def need_gh():
    if not shutil.which("gh"): fail("the GitHub CLI (gh) is not installed or not on PATH; install it and run `gh auth login`")


def allowlisted(handle):
    """True when the handle appears in the 'Handle or account' column of ALLOWLIST.md (exact, case-insensitive)."""
    p = os.path.join(ROOT, "ALLOWLIST.md")
    if not os.path.isfile(p): return True
    handles = set()
    for r in read(p).splitlines():
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].lower() not in ("name", "") and not cells[0].startswith("-"): handles.add(cells[1].lstrip("@").lower())
    return handle.lower() in handles


def cmd_import_issue(a):
    need_gh()
    issue = json.loads(sh(["gh", "issue", "view", str(a.number), "--json", "title,body,labels,url,author"]).stdout)
    labels = [l["name"] for l in issue.get("labels", [])]; author = (issue.get("author") or {}).get("login", "")
    if author and not allowlisted(author):
        append(os.path.join(ROOT, "INBOX.md"), f"- {now()} issue #{a.number} by {author} is not on the allowlist; recorded, not started: {issue['url']}\n")
        fail(f"author {author} is not in tickets/ALLOWLIST.md; recorded in INBOX.md")
    risk = "high" if "risk:high" in labels else "medium" if "risk:medium" in labels else "low"
    tid = new_ticket(issue["title"], owns="", deliverable="", kind=a.kind, risk=risk, feature=a.feature)
    t = load(tid)
    save_body(t, replace_section(t["_body"], "Context the worker needs", f"- From GitHub issue #{a.number}: {issue['url']}\n- Labels: {', '.join(labels) or 'none'}\n\n{quoted(issue.get('body') or '')}"))
    print(tid); print(f"drafted from issue #{a.number}; the intake fills owns, deliverable, eval rows and reviews before it is ready")


def cmd_pr(a):
    need_gh(); c = config(); allt = load_all()
    if a.id.startswith("F-"):
        rec = load_feature(a.id); title = f"{a.id}: {rec.get('title','')}"
        summ = os.path.join(FEATURES, a.id, "summary.md"); body = read(summ) if os.path.isfile(summ) else rec["_body"]
    elif a.id in allt:
        rec = allt[a.id]; title = f"{a.id}: {rec.get('title','')}"; body = rec["_body"]
    else: fail(f"unknown feature or ticket {a.id}")
    if rec.get("pr"): fail(f"{a.id} already has pull request {rec['pr']}")
    head = c["branch"]
    marker = os.path.join(ROOT, f".pr-{a.id}.pending"); write(marker, f"{now()} opening PR {head} -> {a.base} for {a.id}\n")  # the intent is on disk before the request exists
    sh(["git", "push", "-u", "origin", head], cwd=MAIN)
    subprocess.run(["gh", "label", "create", "factory", "--description", "Opened by the ticket factory", "--color", "5319e7"], cwd=MAIN, capture_output=True, text=True)  # exists already: fine
    r = sh(["gh", "pr", "create", "--base", a.base, "--head", head, "--title", title, "--label", "factory", "--body", body + f"\n\n---\nOpened by the factory from `{head}`. Review the summary; rework by writing in review.md."], cwd=MAIN)
    url = r.stdout.strip().splitlines()[-1]
    set_value(rec, "pr", url); os.remove(marker); print(url)


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create tickets/ from the templates").set_defaults(f=cmd_init)
    sub.add_parser("config", help="print the settings in force").set_defaults(f=cmd_config)
    fp = sub.add_parser("feature", help="features: new, status, list, show, summary"); fs = fp.add_subparsers(dest="action", required=True)
    s = fs.add_parser("new"); s.add_argument("title"); s.add_argument("--request", default="", help="the request, verbatim"); s.add_argument("--requested-by", default=""); s.set_defaults(f=cmd_feature_new)
    s = fs.add_parser("status"); s.add_argument("id"); s.add_argument("status", choices=FEATURE_STATUSES); s.set_defaults(f=cmd_feature_status)
    fs.add_parser("list").set_defaults(f=cmd_feature_list)
    s = fs.add_parser("show"); s.add_argument("id"); s.set_defaults(f=cmd_feature_show)
    s = fs.add_parser("summary"); s.add_argument("id"); s.set_defaults(f=cmd_feature_summary)
    s = sub.add_parser("new", help="create a draft ticket; prints its id"); s.add_argument("title"); s.add_argument("--owns", required=True, help="comma-separated paths the work may change"); s.add_argument("--deliverable", required=True, help="the output a reader opens"); s.add_argument("--kind", default="code", choices=KINDS); s.add_argument("--mode", default="solo", choices=["solo", "team"]); s.add_argument("--depends", default="", help="comma-separated ticket ids"); s.add_argument("--risk", default="low", choices=RISKS); s.add_argument("--feature", default=""); s.add_argument("--reviews", default="", help=f"comma-separated from {SURFACES}"); s.set_defaults(f=cmd_new)
    s = sub.add_parser("show", help="print a ticket's rd.md and notes"); s.add_argument("id"); s.set_defaults(f=cmd_show)
    s = sub.add_parser("validate", help="problems that keep tickets from ready; exit 2 if any"); s.add_argument("id", nargs="?"); s.set_defaults(f=cmd_validate)
    s = sub.add_parser("ready", help="validate, then set status ready"); s.add_argument("id"); s.set_defaults(f=lambda a: cmd_status(argparse.Namespace(id=a.id, status="ready", why="")))
    s = sub.add_parser("status", help="change a ticket's status, with the rules for ready, running, done and blocked"); s.add_argument("id"); s.add_argument("status", choices=STATUSES); s.add_argument("--why", default="", help="required for blocked: what a person must see"); s.set_defaults(f=cmd_status)
    sub.add_parser("next", help="tickets that can start now").set_defaults(f=cmd_next)
    sub.add_parser("board", help="rewrite tickets/BOARD.md").set_defaults(f=lambda a: print("board rewritten"))
    s = sub.add_parser("precedent", help="decisions that may already answer a question"); s.add_argument("words"); s.set_defaults(f=cmd_precedent)
    s = sub.add_parser("decide", help="append a decision to the ledger; prints its id"); s.add_argument("id", help="ticket or feature id"); s.add_argument("--question", required=True); s.add_argument("--decided", required=True); s.add_argument("--why", required=True); s.add_argument("--by", required=True, choices=DECIDERS); s.add_argument("--options", default="", help='"a | b | c"'); s.add_argument("--level", default="standard", choices=["trivial", "standard", "high"]); s.add_argument("--precedent", default="", help='"D-003 (followed)"'); s.add_argument("--dissent", default=""); s.add_argument("--reversible", default="yes", choices=["yes", "no"]); s.add_argument("--overrides", default="", help="the D- id this decision overturns"); s.set_defaults(f=cmd_decide)
    s = sub.add_parser("resolve", help="clear an open question with a recorded decision"); s.add_argument("id"); s.add_argument("--decision", required=True); s.add_argument("--number", type=int, default=0, help="which open question, 1-based"); s.add_argument("--all", action="store_true"); s.set_defaults(f=cmd_resolve)
    s = sub.add_parser("gate", help="run checks.sh (from the integration branch) and the owns check in the ticket's worktree; exit 2 on FAIL"); s.add_argument("id"); s.add_argument("--worktree", default="", help="path; found from git worktree list when omitted"); s.set_defaults(f=cmd_gate)
    s = sub.add_parser("vote", help="record a reviewer's vote in eval.md"); s.add_argument("id"); s.add_argument("--role", required=True, help="one of the ticket's reviews, or arbiter"); s.add_argument("--vote", required=True, choices=["approve", "changes"]); s.add_argument("--why", required=True); s.set_defaults(f=cmd_vote)
    s = sub.add_parser("verdict", help="approve (0) | changes (2) | escalate (3)"); s.add_argument("id"); s.set_defaults(f=cmd_verdict)
    s = sub.add_parser("rework", help="a new ticket carrying a person's note; overrides a decision"); s.add_argument("id", help="F- or T- id"); s.add_argument("--note", required=True, help="the person's words, verbatim"); s.add_argument("--overrides", default="", help="the D- id the note overturns"); s.add_argument("--owns", default=""); s.add_argument("--risk", default="", choices=[""] + RISKS); s.add_argument("--kind", default="", choices=[""] + KINDS); s.set_defaults(f=cmd_rework)
    s = sub.add_parser("log", help="append an attempt to RUN.md"); s.add_argument("id"); s.add_argument("--attempt", default=1, type=int); s.add_argument("--minutes", required=True); s.add_argument("--questions", default=0); s.add_argument("--returned", default=0); s.add_argument("--defects", default=0); s.add_argument("--restarts", default=0); s.add_argument("--tokens", default=""); s.add_argument("--role", default="worker", choices=ROLES); s.set_defaults(f=cmd_log)
    sub.add_parser("sample", help="done tickets due for scoring").set_defaults(f=cmd_sample)
    s = sub.add_parser("score", help="record a judge's label for a ticket"); s.add_argument("id"); s.add_argument("--scorer", required=True); s.add_argument("--label", required=True); s.add_argument("--why", required=True); s.set_defaults(f=cmd_score)
    bp = sub.add_parser("bench", help="benchmarks: add, list, record"); bs = bp.add_subparsers(dest="action", required=True)
    x = bs.add_parser("add"); x.add_argument("id"); x.set_defaults(f=cmd_bench)
    bs.add_parser("list").set_defaults(f=cmd_bench)
    x = bs.add_parser("record"); x.add_argument("id"); x.add_argument("--model", required=True); x.add_argument("--passed", required=True, help="rows passed over rows, like 7/8"); x.add_argument("--minutes", required=True); x.add_argument("--tokens", default=""); x.set_defaults(f=cmd_bench)
    sub.add_parser("stats", help="run figures").set_defaults(f=cmd_stats)
    sub.add_parser("dashboard", aliases=["html"], help="write tickets/dashboard.html").set_defaults(f=cmd_dashboard)
    s = sub.add_parser("import-issue", help="a draft ticket from a GitHub issue"); s.add_argument("number", type=int); s.add_argument("--kind", default="code", choices=KINDS); s.add_argument("--feature", default=""); s.set_defaults(f=cmd_import_issue)
    s = sub.add_parser("pr", help="push the integration branch and open the pull request"); s.add_argument("id", help="F- or T- id"); s.add_argument("--base", default="main"); s.set_defaults(f=cmd_pr)
    args = p.parse_args()
    if args.cmd in MUTATING:
        with lock():
            try: args.f(args)
            finally:
                if os.path.isdir(ROOT): write_board(load_all())  # the view is rebuilt once, after every primary write
    elif args.cmd == "board":
        with lock(): write_board(load_all()); args.f(args)
    else: args.f(args)


if __name__ == "__main__":
    main()
