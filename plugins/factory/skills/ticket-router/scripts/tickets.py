#!/usr/bin/env python3
"""tickets.py — the only writer of ticket state. Standard library only. Run from the repository root.

State lives in tickets/: one folder per ticket (rd.md, eval.md, notes.md, evidence/), one folder per
feature (tickets/features/F-001/feature.md, summary.md, review.md), and the shared files CONFIG.md,
DECISIONS.md, BOARD.md, RUN.md, ALLOWLIST.md, INBOX.md, checks.sh.

  init                                        create tickets/ from the templates (idempotent)
  config                                      print the settings in force
  feature new "Title" [--request "..."] [--by name]
  feature status F-001 <proposed|decomposed|running|review|accepted|rework>
  feature list | feature show F-001
  feature summary F-001                       write summary.md skeleton from tickets, decisions, votes, evidence
  new "Title" [--kind code|document|analysis|operations] [--mode solo|team] [--depends T-001,T-002]
              [--owns src/a/,tests/a/] [--deliverable path] [--risk low|medium|high] [--feature F-001]
              [--reviews quality,security]
  validate [T-003] | ready T-003 | status T-003 <draft|ready|running|review|done|blocked> | next | board
  precedent "words to match"                  decisions that may already answer a question (person-made first)
  decide T-003 --question "..." --decided "..." --why "..." --by council|worker|person|arbiter
         [--options "a | b"] [--level trivial|standard|high] [--precedent D-003] [--dissent "..."]
         [--reversible yes|no] [--overrides D-014]
  resolve T-003 --decision D-014 [--question N]  remove the open question, record the decision in Context
  gate T-003 [--dir path]                     run tickets/checks.sh in the ticket's worktree; evidence/gate.txt
  vote T-003 --role security --verdict approve|changes --why "..."
  verdict T-003                               approve | changes | escalate, from votes, risk and CONFIG.md
  rework F-001|T-003 --note "..." [--overrides D-014] [--owns ...]   a new ticket carrying the person's note
  log T-003 --minutes 23 [--questions 1 --returned 0 --defects 0 --restarts 0 --tokens N]
  stats                                       throughput, first-pass rate, decisions by maker, override rate
  html                                        write tickets/dashboard.html
  import-issue 42 [--kind ...]                a draft ticket from a GitHub issue (gh CLI)
  pr F-001|T-003                              open the pull request from the integration branch (gh CLI)
"""
import argparse, datetime, html, json, os, re, shutil, subprocess, sys

ROOT = os.path.join(os.getcwd(), "tickets")
FEATURES = os.path.join(ROOT, "features")
STATUSES = ["draft", "ready", "running", "review", "done", "blocked"]
FEATURE_STATUSES = ["proposed", "decomposed", "running", "review", "accepted", "rework"]
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates") if os.path.isdir(os.path.join(HERE, "templates")) else os.path.join(HERE, "..", "templates")
SHARED = ["CONFIG.md", "DECISIONS.md", "BOARD.md", "RUN.md", "ALLOWLIST.md", "INBOX.md", "checks.sh"]


# ---------------------------------------------------------------- small helpers

def fail(msg):
    print("error:", msg, file=sys.stderr); sys.exit(1)


def now(fmt="%Y-%m-%d %H:%M"):
    return datetime.datetime.now().strftime(fmt)


def read(p):
    return open(p, encoding="utf-8").read()


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(text)


def append(p, text):
    with open(p, "a", encoding="utf-8") as f: f.write(text)


def template(name):
    p = os.path.join(TEMPLATES, name)
    if not os.path.isfile(p): fail(f"template {name} missing beside the script")
    return read(p)


def split_frontmatter(text, what="file"):
    m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
    if not m: fail(f"{what} has no frontmatter block")
    return m.group(1), m.group(2)


def parse_list(v):
    return [x.strip() for x in v.strip("[]").split(",") if x.strip()]


def parse_frontmatter(fm):
    """Flat keys, `- ` lists, inline [lists], and one level of nested blocks (budget:, models:, ...)."""
    data, key, nested = {}, None, None
    for raw in fm.splitlines():
        line = raw.split("  #", 1)[0].rstrip() if raw.lstrip().startswith("- ") else raw.split("#", 1)[0].rstrip()
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
            if v == "": data[k] = None  # decided by the next line: list or dict
            elif v.startswith("["): data[k] = parse_list(v)
            else: data[k] = v
        else:
            if not isinstance(data.get(key), dict): data[key] = {}
            nested = key
            data[key][k] = parse_list(v) if v.startswith("[") else (int(v) if v.isdigit() else v)
    for k, v in list(data.items()):
        if v is None: data[k] = []
        elif isinstance(v, dict) and "_items" in v: data[k] = v["_items"]
    return data


def set_frontmatter_value(text, k, v):
    fm, body = split_frontmatter(text)
    new, done = [], False
    for line in fm.splitlines():
        if re.match(rf"^{re.escape(k)}:", line) and not done:
            comment = ("  #" + line.split("#", 1)[1]) if "#" in line else ""
            new.append(f"{k}: {v}{comment}"); done = True
        else: new.append(line)
    if not done: new.append(f"{k}: {v}")
    return "---\n" + "\n".join(new) + "\n---\n" + body


def set_frontmatter_list(text, k, items):
    fm, body = split_frontmatter(text)
    block = f"{k}:\n" + "".join(f"  - {i}\n" for i in items)
    if re.search(rf"^{re.escape(k)}:[^\n]*\n(?:  - [^\n]*\n)*", fm + "\n", re.M):
        fm = re.sub(rf"^{re.escape(k)}:[^\n]*\n(?:  - [^\n]*\n)*", block, fm + "\n", count=1, flags=re.M).rstrip("\n")
    else: fm = fm + "\n" + block.rstrip("\n")
    return "---\n" + fm + "\n---\n" + body


def section(body, heading):
    m = re.search(rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    return m.group(1) if m else None


def replace_section(body, heading, content):
    if section(body, heading) is None: return body.rstrip("\n") + f"\n\n## {heading}\n{content}\n"
    return re.sub(rf"(^## {re.escape(heading)}\s*\n)(.*?)(?=^## |\Z)", lambda m: m.group(1) + content + "\n\n", body, count=1, flags=re.S | re.M)


def sh(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True)
    if check and r.returncode != 0: fail(f"{cmd if isinstance(cmd, str) else ' '.join(cmd)}\n{r.stderr.strip()}")
    return r


# ---------------------------------------------------------------- config

DEFAULT_CONFIG = {"branch": "integration", "promote": "pr", "concurrency": 3, "paused": "false",
                  "approval": {"low": "checker", "medium": "majority", "high": "unanimous"}}


def config():
    p = os.path.join(ROOT, "CONFIG.md")
    if not os.path.isfile(p): return dict(DEFAULT_CONFIG)
    m = re.search(r"```yaml\n(.*?)\n```", read(p), re.S)
    if not m: return dict(DEFAULT_CONFIG)
    c = dict(DEFAULT_CONFIG); c.update(parse_frontmatter(m.group(1)))
    if isinstance(c.get("approval"), dict): c["approval"] = {**DEFAULT_CONFIG["approval"], **c["approval"]}
    return c


# ---------------------------------------------------------------- tickets

def ticket_ids():
    if not os.path.isdir(ROOT): return []
    return sorted(d for d in os.listdir(ROOT) if re.match(r"T-\d{3,}$", d))


def load(tid):
    p = os.path.join(ROOT, tid, "rd.md")
    if not os.path.isfile(p): fail(f"{tid}: rd.md missing")
    text = read(p); fm, body = split_frontmatter(text, f"{tid}/rd.md")
    d = parse_frontmatter(fm); d["_body"], d["_path"], d["_text"] = body, p, text
    return d


def load_all():
    return {t: load(t) for t in ticket_ids()}


def save_ticket(t, text):
    write(t["_path"], text); t["_text"] = text; t["_body"] = split_frontmatter(text)[1]


def owns_overlap(a, b):
    return any(x.rstrip("/").startswith(y.rstrip("/")) or y.rstrip("/").startswith(x.rstrip("/")) for x in a for y in b)


def open_questions(t):
    s = section(t["_body"], "Open questions") or ""
    qs = [l.strip() for l in s.strip().splitlines() if l.strip()]
    return [] if not qs or qs[0].lower() in ("none", "none.") else qs


def eval_rows(tid):
    p = os.path.join(ROOT, tid, "eval.md")
    if not os.path.isfile(p): return None
    return [[c.strip() for c in r.strip("|").split("|")] for r in read(p).splitlines() if re.match(r"^\|\s*\d+\s*\|", r)]


def note(tid, text):
    append(os.path.join(ROOT, tid, "notes.md"), f"- {now()} {text}\n")


def validate(tid, allt, quiet=False, target=None):
    t = allt[tid]; problems = []; status = target or t.get("status")
    rows = eval_rows(tid)
    if rows is None: problems.append("eval.md missing")
    elif not rows: problems.append("eval.md has no numbered check rows")
    else:
        for cells in rows:
            if len(cells) < 4 or not cells[2] or not cells[3]: problems.append(f"eval row {cells[0]} lacks a how-to-verify or an evidence file")
    if t.get("status") not in STATUSES: problems.append(f"status '{t.get('status')}' is not one of {STATUSES}")
    if t.get("mode") not in ("solo", "team"): problems.append("mode must be solo or team")
    if t.get("kind") not in ("code", "document", "analysis", "operations"): problems.append("kind must be code, document, analysis or operations")
    if not t.get("deliverable"): problems.append("deliverable is empty: name the output a reader opens")
    if not t.get("owns"): problems.append("owns is empty: a ticket must name the paths it may change")
    if any(o.rstrip("/") == "tickets" or o.startswith("tickets/") for o in t.get("owns", [])): problems.append("owns must not include tickets/: only the script writes there")
    for d in t.get("depends", []):
        if d not in allt: problems.append(f"depends on unknown ticket {d}")
    if open_questions(t) and status in ("ready", "running"): problems.append("has open questions; decide them first (tickets.py decide + resolve)")
    if t.get("risk") == "high" and not re.search(r"stops? for a person|needs a person|escalat", t["_body"], re.I):
        problems.append("risk is high but the ticket does not say where it stops for a person")
    if t.get("feature") and not os.path.isdir(os.path.join(FEATURES, t["feature"])): problems.append(f"feature {t['feature']} does not exist")
    def visit(n, path):
        if n in path: problems.append("dependency cycle: " + " -> ".join(path + [n])); return
        for d in allt.get(n, {}).get("depends", []):
            if d in allt: visit(d, path + [n])
    visit(tid, [])
    if not quiet: print(f"{tid}: " + ("ok" if not problems else "\n  - " + "\n  - ".join(problems)))
    return problems


def write_board(allt):
    c = config()
    lines = ["# Board", "", f"Source of truth is each ticket's `rd.md` frontmatter; this file is the view. Integration branch `{c['branch']}` · promote `{c['promote']}` · concurrency {c['concurrency']}" + (" · **paused**" if str(c.get("paused")).lower() == "true" else ""), "",
             "| Ticket | Feature | Title | Status | Kind | Risk | Reviews | Depends | Owns | Budget (min) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for tid in sorted(allt):
        t = allt[tid]
        lines.append(f"| {tid} | {t.get('feature','')} | {t.get('title','')} | {t.get('status','')} | {t.get('kind','')} | {t.get('risk','')} | {', '.join(t.get('reviews',[]) if isinstance(t.get('reviews'), list) else [])} | {', '.join(t.get('depends',[]))} | {', '.join(t.get('owns',[]))} | {t.get('budget',{}).get('minutes','') if isinstance(t.get('budget'), dict) else ''} |")
    lines += ["", "## Waiting on a person", "", "Only what the panel could not settle: no consensus, an irreversible step, or a decision a person made that would be reversed.", "", "| Ticket | Why | Since |", "|---|---|---|"]
    for tid in sorted(allt):
        t = allt[tid]
        if t.get("status") == "blocked":
            why = (section(t["_body"], "Blocked") or "see notes.md").strip().splitlines()[0] if section(t["_body"], "Blocked") else "see notes.md"
            lines.append(f"| {tid} | {why} | |")
    feats = feature_ids()
    if feats:
        lines += ["", "## Features", "", "| Feature | Title | Status | Tickets done | Summary |", "|---|---|---|---|---|"]
        for fid in feats:
            f = load_feature(fid); ts = [allt[x] for x in f.get("tickets", []) if x in allt]
            done = sum(1 for x in ts if x.get("status") == "done")
            lines.append(f"| {fid} | {f.get('title','')} | {f.get('status','')} | {done}/{len(ts)} | {'features/' + fid + '/summary.md' if os.path.isfile(os.path.join(FEATURES, fid, 'summary.md')) else ''} |")
    lines += ["", "Run log: `tickets/RUN.md` · Decisions: `tickets/DECISIONS.md` · Dashboard: `python3 tickets.py html`", ""]
    write(os.path.join(ROOT, "BOARD.md"), "\n".join(lines))


def ensure_root():
    os.makedirs(FEATURES, exist_ok=True)
    for name in SHARED:
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            src = os.path.join(TEMPLATES, name)
            if os.path.exists(src): shutil.copy(src, p)
            elif name == "INBOX.md": write(p, "# Inbox\n\nTwo-line notes from workers about problems outside their ticket. The reproducer turns these into draft tickets.\n")
    gi = os.path.join(ROOT, ".gitignore")
    if not os.path.exists(gi): write(gi, "dashboard.html\n")


def cmd_init(a):
    ensure_root(); write_board(load_all()); print("tickets/ ready:", ", ".join(SHARED), "features/")


def cmd_config(a):
    print(json.dumps(config(), indent=2))


def cmd_new(a):
    ensure_root()
    ids = ticket_ids(); n = (int(ids[-1][2:]) + 1) if ids else 1
    tid = f"T-{n:03d}"; folder = os.path.join(ROOT, tid); os.makedirs(os.path.join(folder, "evidence"))
    rd = template("rd.md").replace("T-001", tid)
    rd = set_frontmatter_value(rd, "title", a.title).replace(f"# {tid} Short name of the deliverable", f"# {tid} {a.title}")
    rd = set_frontmatter_value(rd, "mode", a.mode).replace("depends: []", f"depends: [{a.depends or ''}]")
    rd = set_frontmatter_value(rd, "risk", a.risk); rd = set_frontmatter_value(rd, "kind", a.kind)
    if a.deliverable: rd = set_frontmatter_value(rd, "deliverable", a.deliverable)
    if a.owns: rd = set_frontmatter_list(rd, "owns", [p.strip() for p in a.owns.split(",") if p.strip()])
    if a.feature:
        if not os.path.isdir(os.path.join(FEATURES, a.feature)): fail(f"feature {a.feature} does not exist")
        rd = set_frontmatter_value(rd, "feature", a.feature)
    if a.reviews: rd = set_frontmatter_value(rd, "reviews", "[" + ", ".join(x.strip() for x in a.reviews.split(",") if x.strip()) + "]")
    write(os.path.join(folder, "rd.md"), rd)
    write(os.path.join(folder, "eval.md"), template("eval.md").replace("T-001", tid))
    if a.feature: feature_add(a.feature, tid)
    note(tid, "created")
    print(f"created {tid} in tickets/{tid}/ (status draft). Fill rd.md and eval.md, then: tickets.py ready {tid}")


def cmd_status(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    if a.status not in STATUSES: fail(f"status must be one of {STATUSES}")
    t = allt[a.id]; c = config()
    if a.status in ("ready", "running") and validate(a.id, allt, quiet=True, target=a.status): validate(a.id, allt, target=a.status); fail(f"fix the problems above before marking {a.status}")
    if a.status == "running":
        if str(c.get("paused")).lower() == "true": fail("CONFIG.md says paused: true; nothing starts")
        for d in t.get("depends", []):
            if allt[d].get("status") != "done": fail(f"{a.id} depends on {d}, which is {allt[d].get('status')}")
        running = [o for o, ot in allt.items() if ot.get("status") == "running"]
        if len(running) >= int(c.get("concurrency", 3)): fail(f"concurrency {c.get('concurrency')} reached: {', '.join(running)} are running")
        for o in running:
            if owns_overlap(t.get("owns", []), allt[o].get("owns", [])): fail(f"{a.id} shares owned paths with running ticket {o}")
    if a.status == "done":
        word, why = compute_verdict(a.id, allt)
        if word != "approve": fail(f"{a.id} cannot be done: {why}")
    save_ticket(t, set_frontmatter_value(t["_text"], "status", a.status)); allt[a.id]["status"] = a.status
    write_board(allt); note(a.id, f"status -> {a.status}")
    if t.get("feature"): feature_rollup(t["feature"], allt)
    print(f"{a.id}: {a.status}")


def cmd_next(a):
    allt = load_all(); c = config()
    if str(c.get("paused")).lower() == "true": print("paused (tickets/CONFIG.md)"); return
    running = [t for t in allt.values() if t.get("status") == "running"]
    slots = int(c.get("concurrency", 3)) - len(running)
    out = []
    for tid, t in sorted(allt.items()):
        if t.get("status") != "ready": continue
        if any(allt[d].get("status") != "done" for d in t.get("depends", []) if d in allt): continue
        if any(owns_overlap(t.get("owns", []), r.get("owns", [])) for r in running): continue
        if any(owns_overlap(t.get("owns", []), allt[o].get("owns", [])) for o in out): continue
        out.append(tid)
    if not out: print("nothing runnable: no ready ticket has its dependencies done and its paths free"); return
    for tid in out[:max(slots, 0)]:
        t = allt[tid]; print(f"{tid} ({t.get('kind')}, {t.get('mode')}, risk {t.get('risk')}, {t.get('budget',{}).get('minutes','?')} min): {t.get('title')}")
    if len(out) > max(slots, 0): print(f"({len(out) - max(slots, 0)} more wait for a slot: concurrency {c.get('concurrency')})")


def cmd_log(a):
    row = f"| {a.id} | {a.attempt} | | {now()} | {a.minutes} | {a.questions} | {a.returned} | {a.defects} | {a.restarts} | {a.tokens or ''} |\n"
    append(os.path.join(ROOT, "RUN.md"), row); print("logged", a.id)


# ---------------------------------------------------------------- features

def feature_ids():
    if not os.path.isdir(FEATURES): return []
    return sorted(d for d in os.listdir(FEATURES) if re.match(r"F-\d{3,}$", d))


def load_feature(fid):
    p = os.path.join(FEATURES, fid, "feature.md")
    if not os.path.isfile(p): fail(f"{fid}: feature.md missing")
    text = read(p); fm, body = split_frontmatter(text, f"{fid}/feature.md")
    d = parse_frontmatter(fm); d["_body"], d["_path"], d["_text"] = body, p, text
    if not isinstance(d.get("tickets"), list): d["tickets"] = []
    return d


def feature_add(fid, tid):
    f = load_feature(fid)
    if tid not in f["tickets"]:
        write(f["_path"], set_frontmatter_list(f["_text"], "tickets", f["tickets"] + [tid]))


def feature_rollup(fid, allt):
    f = load_feature(fid); ts = [allt[x] for x in f["tickets"] if x in allt]
    if not ts: return
    if all(x.get("status") == "done" for x in ts) and f.get("status") not in ("review", "accepted"):
        write(f["_path"], set_frontmatter_value(f["_text"], "status", "review")); print(f"{fid}: every ticket is done -> review (write the summary: tickets.py feature summary {fid})")
    elif any(x.get("status") in ("running", "review") for x in ts) and f.get("status") in ("proposed", "decomposed", "rework", "accepted"):
        write(f["_path"], set_frontmatter_value(f["_text"], "status", "running"))


def cmd_feature(a):
    ensure_root()
    if a.action == "new":
        ids = feature_ids(); n = (int(ids[-1][2:]) + 1) if ids else 1
        fid = f"F-{n:03d}"
        text = template("feature.md").replace("F-001", fid)
        text = set_frontmatter_value(text, "title", a.title).replace(f"# {fid} Feature title", f"# {fid} {a.title}")
        text = set_frontmatter_value(text, "requested_by", a.by or "")
        text = set_frontmatter_value(text, "requested", now("%Y-%m-%d"))
        if a.request: text = replace_section(text, "Request", a.request.strip())
        write(os.path.join(FEATURES, fid, "feature.md"), text)
        write(os.path.join(FEATURES, fid, "review.md"), template("review.md").replace("F-001", fid))
        print(f"created {fid} in tickets/features/{fid}/ (status proposed). Decompose it: tickets.py new \"...\" --feature {fid}")
    elif a.action == "status":
        f = load_feature(a.title)
        if a.value not in FEATURE_STATUSES: fail(f"status must be one of {FEATURE_STATUSES}")
        write(f["_path"], set_frontmatter_value(f["_text"], "status", a.value)); write_board(load_all()); print(f"{a.title}: {a.value}")
    elif a.action == "list":
        allt = load_all()
        for fid in feature_ids():
            f = load_feature(fid); done = sum(1 for x in f["tickets"] if x in allt and allt[x].get("status") == "done")
            print(f"{fid} [{f.get('status')}] {f.get('title')} — {done}/{len(f['tickets'])} tickets done")
    elif a.action == "show":
        f = load_feature(a.title); print(f["_text"])
    elif a.action == "summary":
        write_summary(a.title)
    else: fail("feature action must be new, status, list, show or summary")


def decisions_for(tids):
    return [d for d in parse_decisions() if d.get("ticket") in tids]


def write_summary(fid):
    f = load_feature(fid); allt = load_all(); c = config()
    ts = {x: allt[x] for x in f["tickets"] if x in allt}
    ds = decisions_for(set(ts) | {fid})
    rank = {"person": 0, "escalated": 0, "council": 1, "arbiter": 1, "worker": 2}
    def prio(d):  # what a reviewer should look at first
        if d.get("overridden_by"): return 9
        if d.get("by") == "person": return 8
        if d.get("precedent", "none").lower().startswith("none") and d.get("by") != "worker": return 0
        if d.get("dissent", "none").lower() not in ("none", "none.", ""): return 1
        if d.get("by") == "worker": return 2
        return 3
    L = [f"# {fid} {f.get('title','')} · summary", "", f"Written {now()} from the ticket files. Status at writing: {f.get('status')}. Read the first two sections first; they hold what is most likely to need rework.", "",
         "## What was built", "", "_(summarizer: three to six sentences from the reader's side — what they can now do, see or know; link the deliverables)_", ""]
    novel = [d for d in ds if prio(d) == 0]; diss = [d for d in ds if prio(d) == 1]; wk = [d for d in ds if prio(d) == 2]; prec = [d for d in ds if prio(d) == 3]; esc = [d for d in ds if d.get("by") == "person"]
    L += ["## Decisions to review first (no precedent to lean on)", ""]
    L += [f"- **{d['id']}** ({d['ticket']}): {d['question']} → **{d['decided']}** — {d['why']}" + (f" · dissent: {d['dissent']}" if d.get('dissent','none').lower() not in ('none','none.','') else "") for d in novel] or ["- none"]
    L += ["", "## Decisions with recorded dissent", ""]
    L += [f"- **{d['id']}** ({d['ticket']}): {d['question']} → **{d['decided']}** · dissent: {d['dissent']}" for d in diss] or ["- none"]
    L += ["", "## Assumptions workers made on their own", ""]
    L += [f"- **{d['id']}** ({d['ticket']}): {d['question']} → {d['decided']}" for d in wk] or ["- none"]
    L += ["", "## Decisions that followed precedent", ""]
    L += [f"- {d['id']} ({d['ticket']}): {d['decided']} · follows {d['precedent']}" for d in prec] or ["- none"]
    if esc: L += ["", "## Decisions a person made during the run", ""] + [f"- {d['id']} ({d['ticket']}): {d['question']} → {d['decided']}" for d in esc]
    L += ["", "## Tickets", "", "| Ticket | Title | Status | Risk | Verdict | Votes | Evidence |", "|---|---|---|---|---|---|---|"]
    for tid, t in ts.items():
        votes = parse_votes(tid); ev = os.path.join(ROOT, tid, "evidence")
        files = sorted(os.listdir(ev)) if os.path.isdir(ev) else []
        L.append(f"| {tid} | {t.get('title','')} | {t.get('status','')} | {t.get('risk','')} | {checker_verdict(tid) or ''} | {', '.join(v['role'] + ':' + v['verdict'] for v in votes)} | {', '.join(files)} |")
    L += ["", "## What to look at", "", "_(summarizer: the three to five places a reviewer should open — a screen, a file, a test output — each with its path or evidence file)_", ""]
    L += ["## Run", "", stats_text(set(ts)), ""]
    L += ["## How to rework", "", f"Write what is wrong in `tickets/features/{fid}/review.md` (one line per item, name the decision id where there is one), then say \"factory: rework {fid}\" — or run `tickets.py rework {fid} --note \"...\" [--overrides D-0xx]`. A person's rework overrides the panel's decision and becomes the precedent the next panel follows.", ""]
    write(os.path.join(FEATURES, fid, "summary.md"), "\n".join(L))
    if f.get("status") not in ("review", "accepted", "rework"): write(f["_path"], set_frontmatter_value(f["_text"], "status", "review"))
    write_board(allt); print(f"wrote tickets/features/{fid}/summary.md ({len(ds)} decisions, {len(ts)} tickets)")


# ---------------------------------------------------------------- decisions

def decisions_path():
    return os.path.join(ROOT, "DECISIONS.md")


def parse_decisions():
    p = decisions_path()
    if not os.path.isfile(p): return []
    out = []
    for m in re.finditer(r"^## (D-\d+) · (\S+) · (\S+) · (\S+) · (\S+)\s*\n(.*?)(?=^## D-|\Z)", read(p), re.S | re.M):
        d = {"id": m.group(1), "date": m.group(2), "ticket": m.group(3), "by": m.group(4), "level": m.group(5)}
        for line in m.group(6).splitlines():
            mm = re.match(r"^- (\w[\w ]*): ?(.*)$", line.strip())
            if mm: d[mm.group(1).strip().lower().replace(" ", "_")] = mm.group(2).strip()
        out.append(d)
    return out


def cmd_precedent(a):
    ds = parse_decisions()
    words = {w for w in re.findall(r"[a-z0-9]{3,}", a.words.lower())} - {"the", "and", "for", "with", "should", "use", "that", "this", "what", "which"}
    scored = []
    for d in ds:
        hay = " ".join(d.get(k, "") for k in ("question", "options", "decided", "why")).lower()
        score = sum(1 for w in words if w in hay)
        if score: scored.append((0 if d.get("by") == "person" else 1, -score, d))
    scored.sort(key=lambda x: (x[0], x[1], x[2]["id"]))
    if not scored: print("no precedent found; the panel decides"); return
    for _, s, d in scored[:5]:
        flag = " (OVERRIDDEN by " + d["overridden_by"] + ")" if d.get("overridden_by") else ""
        print(f"{d['id']} [{d['by']}, {d['ticket']}, matches {-s}]{flag}: {d.get('question','')} -> {d.get('decided','')} — {d.get('why','')}")


def cmd_decide(a):
    ensure_root(); ds = parse_decisions()
    n = (max(int(d["id"][2:]) for d in ds) + 1) if ds else 1; did = f"D-{n:03d}"
    if a.by not in ("council", "worker", "person", "arbiter", "escalated"): fail("--by must be council, worker, person, arbiter or escalated")
    if a.by == "council" and a.level == "trivial": fail("a trivial question is the worker's to decide (--by worker); a panel is for standard or high")
    body = (f"## {did} · {now('%Y-%m-%d')} · {a.id} · {a.by} · {a.level}\n"
            f"- Question: {a.question}\n- Options: {a.options or 'not listed'}\n- Decided: {a.decided}\n- Why: {a.why}\n"
            f"- Precedent: {a.precedent or 'none'}\n- Dissent: {a.dissent or 'none'}\n- Reversible: {a.reversible}\n")
    if a.overrides: body += f"- Overrides: {a.overrides}\n"
    append(decisions_path(), "\n" + body)
    if a.overrides:
        text = read(decisions_path())
        text = re.sub(rf"(^## {re.escape(a.overrides)} · .*?)(?=^## D-|\Z)", lambda m: m.group(1).rstrip("\n") + f"\n- Overridden by: {did}\n\n", text, count=1, flags=re.S | re.M)
        write(decisions_path(), text)
    if a.id.startswith("T-") and os.path.isdir(os.path.join(ROOT, a.id)): note(a.id, f"{did} ({a.by}): {a.decided}")
    print(did)


def cmd_resolve(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    d = next((x for x in parse_decisions() if x["id"] == a.decision), None)
    if not d: fail(f"unknown decision {a.decision}")
    t = allt[a.id]; qs = open_questions(t)
    if not qs: fail(f"{a.id} has no open questions")
    if a.question:
        if not 1 <= a.question <= len(qs): fail(f"question must be 1..{len(qs)}")
        removed = [qs[a.question - 1]]; left = [q for i, q in enumerate(qs, 1) if i != a.question]
    else: removed, left = qs, []
    body = replace_section(t["_body"], "Open questions", "\n".join(left) if left else "None.")
    ctx = (section(body, "Context the worker needs") or "").rstrip("\n")
    body = replace_section(body, "Context the worker needs", ctx + f"\n- Decided {d['date']} ({d['id']}, {d['by']}): {d['decided']} — {d['why']}")
    fm, _ = split_frontmatter(t["_text"]); save_ticket(t, "---\n" + fm + "\n---\n" + body)
    note(a.id, f"resolved {len(removed)} question(s) with {d['id']}"); print(f"{a.id}: {len(removed)} question(s) resolved by {d['id']}; {len(left)} left")


# ---------------------------------------------------------------- gate, votes, verdict

def worktree_for(tid):
    r = sh(["git", "worktree", "list", "--porcelain"], check=False)
    path = None
    for block in r.stdout.strip().split("\n\n"):
        lines = block.splitlines()
        if any(l.strip() == f"branch refs/heads/ticket/{tid}" for l in lines):
            path = lines[0].split(" ", 1)[1]
    return path


def cmd_gate(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    d = a.dir or worktree_for(a.id) or os.getcwd()
    checks = os.path.join(d, "tickets", "checks.sh")
    ev = os.path.join(ROOT, a.id, "evidence"); os.makedirs(ev, exist_ok=True)
    out = [f"gate for {a.id} in {d} at {now()}", ""]
    ok = True
    if os.path.isfile(checks):
        env = {**os.environ, "FACTORY_BRANCH": config()["branch"]}
        r = subprocess.run(["bash", checks], cwd=d, capture_output=True, text=True, env=env)
        out += [f"$ bash tickets/checks.sh  (exit {r.returncode})", r.stdout[-6000:], r.stderr[-3000:]]
        if r.returncode != 0:  # one re-run with nothing changed tells a flaky check from a failing one
            r2 = subprocess.run(["bash", checks], cwd=d, capture_output=True, text=True, env=env)
            if r2.returncode == 0:
                out += ["", "re-run with no change passed: FLAKY check; counted as a pass and sent to INBOX.md"]
                append(os.path.join(ROOT, "INBOX.md"), f"- {now()} flaky check in tickets/checks.sh seen on {a.id}: failed once, passed on re-run; find and fix the flake (see tickets/{a.id}/evidence/gate.txt)\n")
            else:
                out += ["", f"re-run also failed (exit {r2.returncode})"]; ok = False
    else: out.append("no tickets/checks.sh: nothing deterministic to run (add one; see templates/checks.sh)")
    owns = allt[a.id].get("owns", []); base = config()["branch"]
    r = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=d, capture_output=True, text=True)
    if r.returncode == 0:
        stray = [f for f in r.stdout.split() if not any(f == o.rstrip("/") or f.startswith(o.rstrip("/") + "/") for o in owns)]
        out += ["", f"$ git diff --name-only {base}...HEAD -> {len(r.stdout.split())} files; outside owns: {', '.join(stray) if stray else 'none'}"]
        ok = ok and not stray
        write(os.path.join(ev, "diff-files.txt"), r.stdout)
    else: out += ["", f"could not diff against {base}: {r.stderr.strip()}"]
    out += ["", "RESULT: " + ("PASS" if ok else "FAIL")]
    write(os.path.join(ev, "gate.txt"), "\n".join(out)); note(a.id, f"gate {'PASS' if ok else 'FAIL'}")
    print("\n".join(out[-3:])); sys.exit(0 if ok else 2)


def eval_path(tid):
    return os.path.join(ROOT, tid, "eval.md")


def parse_votes(tid):
    p = eval_path(tid)
    if not os.path.isfile(p): return []
    s = section(split_frontmatter_safe(read(p)), "Approval") or ""
    votes = []
    for r in s.splitlines():
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[1] in ("approve", "changes") and cells[0].lower() not in ("role",):
            votes.append({"role": cells[0], "verdict": cells[1], "why": cells[2], "when": cells[3]})
    return votes


def split_frontmatter_safe(text):
    m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
    return m.group(2) if m else text


def checker_verdict(tid):
    p = eval_path(tid)
    if not os.path.isfile(p): return None
    m = re.search(r"^- Verdict:\s*(accepted|returned)\s*$", read(p), re.M)  # the template's "accepted | returned" placeholder does not match
    return m.group(1) if m else None


def cmd_vote(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    if a.verdict not in ("approve", "changes"): fail("--verdict must be approve or changes")
    text = read(eval_path(a.id))
    if section(text, "Approval") is None:
        text = text.rstrip("\n") + "\n\n## Approval\n| Role | Verdict | Why | When |\n|---|---|---|---|\n"
    text = re.sub(r"(^## Approval\s*\n\| Role.*?\n\|---.*?\n(?:\|.*\n)*)", lambda m: m.group(1) + f"| {a.role} | {a.verdict} | {a.why.replace('|', '/')} | {now()} |\n", text, count=1, flags=re.S | re.M)
    write(eval_path(a.id), text); note(a.id, f"vote {a.role}: {a.verdict}"); print(f"{a.id}: {a.role} -> {a.verdict}")


EXIT = {"approve": 0, "changes": 2, "escalate": 3}


def compute_verdict(tid, allt):
    """(word, reason) from the gate, the checker's verdict, the votes and the approval rule for the ticket's risk."""
    t = allt[tid]; rule = config()["approval"].get(t.get("risk", "low"), "majority")
    cv = checker_verdict(tid)
    if cv != "accepted": return "changes", f"the checker's verdict is '{cv or 'missing'}'; approval starts from an accepted evaluation"
    gate = os.path.join(ROOT, tid, "evidence", "gate.txt")
    if os.path.isfile(gate) and "RESULT: PASS" not in read(gate): return "changes", "the gate did not pass (evidence/gate.txt)"
    votes = {}
    for v in parse_votes(tid): votes[v["role"]] = v  # the last vote per role stands
    wanted = t.get("reviews", []) if isinstance(t.get("reviews"), list) else []
    missing = [r for r in wanted if r not in votes]
    if rule == "checker": return "approve", "low risk, checker accepted" + (f" ({len(votes)} reviewer votes recorded)" if votes else "")
    if missing: return "changes", f"waiting for reviews from {', '.join(missing)}"
    yes = [r for r, v in votes.items() if v["verdict"] == "approve"]; no = [r for r, v in votes.items() if v["verdict"] == "changes"]
    if rule == "unanimous":
        if no: return "escalate", f"high risk needs every reviewer; changes requested by {', '.join(no)}"
        return "approve", f"unanimous ({', '.join(yes) or 'checker only'})"
    if not votes: return "approve", "checker accepted and no reviewers listed"
    if len(yes) > len(no): return "approve", f"majority {len(yes)}-{len(no)}" + (f"; dissent from {', '.join(no)} stays in eval.md" if no else "")
    if len(yes) == len(no): return "escalate", f"split {len(yes)}-{len(no)}; the arbiter rules on the diff and the reasons"
    return "changes", f"{', '.join(no)} request changes"


def cmd_verdict(a):
    allt = load_all()
    if a.id not in allt: fail(f"unknown ticket {a.id}")
    word, why = compute_verdict(a.id, allt); print(f"{word}: {why}"); sys.exit(EXIT[word])


# ---------------------------------------------------------------- rework

def short(text, n=60):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def cmd_rework(a):
    allt = load_all(); ensure_root()
    if a.id.startswith("F-"):
        f = load_feature(a.id); src_tickets = [allt[x] for x in f["tickets"] if x in allt]; feature = a.id
        owns = a.owns.split(",") if a.owns else sorted({o for t in src_tickets for o in t.get("owns", [])})
        title = f"Rework {a.id}: {short(a.note)}"
        ctx = f"- Rework of {a.id} {f.get('title','')} asked by a person on {now('%Y-%m-%d')}.\n- Their note, verbatim: {a.note}\n- Read tickets/features/{a.id}/summary.md and review.md first."
    elif a.id in allt:
        t = allt[a.id]; feature = t.get("feature", ""); owns = a.owns.split(",") if a.owns else t.get("owns", [])
        title = f"Rework {a.id}: {short(a.note)}"
        ctx = f"- Rework of {a.id} {t.get('title','')} asked by a person on {now('%Y-%m-%d')}.\n- Their note, verbatim: {a.note}\n- Read tickets/{a.id}/rd.md, eval.md and notes.md first; keep what the note does not fault."
    else: fail(f"unknown feature or ticket {a.id}")
    ns = argparse.Namespace(title=title, mode="solo", depends="", owns=",".join(o.strip() for o in owns), risk="low", kind=(allt[a.id].get("kind") if a.id in allt else "code"), deliverable="", feature=feature or "", reviews="")
    before = set(ticket_ids()); cmd_new(ns); tid = sorted(set(ticket_ids()) - before)[0]
    t = load(tid); body = replace_section(t["_body"], "Context the worker needs", ctx)
    body = replace_section(body, "Outcome", f"The note below is satisfied and nothing else about {a.id} changes: {a.note}")
    fm, _ = split_frontmatter(t["_text"]); save_ticket(t, "---\n" + fm + "\n---\n" + body)
    if a.overrides:
        cmd_decide(argparse.Namespace(id=tid, question=f"Rework of {a.overrides}", decided=a.note, why="a person reviewed the result and asked for this", by="person", options="", level="standard", precedent="", dissent="", reversible="yes", overrides=a.overrides))
    if feature:
        f = load_feature(feature); write(f["_path"], set_frontmatter_value(f["_text"], "status", "rework"))
    write_board(load_all()); print(f"{tid} carries the rework note" + (f"; {a.overrides} is now overridden" if a.overrides else ""))


# ---------------------------------------------------------------- stats, html

def run_rows():
    p = os.path.join(ROOT, "RUN.md")
    if not os.path.isfile(p): return []
    rows = []
    for r in read(p).splitlines():
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) >= 9 and re.match(r"T-\d+", cells[0]): rows.append(cells)
    return rows


def stats_text(only=None):
    allt = load_all(); ds = parse_decisions(); rows = run_rows()
    if only is not None: allt = {k: v for k, v in allt.items() if k in only}; ds = [d for d in ds if d.get("ticket") in only]; rows = [r for r in rows if r[0] in only]
    done = [t for t in allt.values() if t.get("status") == "done"]
    mins = [float(r[4]) for r in rows if re.match(r"^\d+(\.\d+)?$", r[4])]
    first_pass = sum(1 for r in rows if r[6] == "0"); ret = sum(1 for r in rows if r[6] != "0")
    by = {}
    for d in ds: by[d["by"]] = by.get(d["by"], 0) + 1
    council = [d for d in ds if d["by"] in ("council", "arbiter")]
    overridden = [d for d in council if d.get("overridden_by")]
    votes = [v for t in allt for v in parse_votes(t)]
    L = [f"- Tickets: {len(allt)} total, {len(done)} done, {sum(1 for t in allt.values() if t.get('status') == 'blocked')} blocked",
         f"- Attempts logged: {len(rows)}; first-pass (no return by the checker): {first_pass}/{len(rows) or 1} = {100 * first_pass // (len(rows) or 1)}%",
         f"- Minutes per attempt: median {sorted(mins)[len(mins) // 2] if mins else '—'}, total {sum(mins) if mins else '—'}",
         f"- Decisions: {len(ds)} ({', '.join(f'{k} {v}' for k, v in sorted(by.items())) or 'none'})",
         f"- Panel decisions later overridden by a person: {len(overridden)}/{len(council) or 1} = {100 * len(overridden) // (len(council) or 1)}%  (the autonomy health number: high means the panel should escalate earlier in that area)",
         f"- Reviewer votes: {sum(1 for v in votes if v['verdict'] == 'approve')} approve, {sum(1 for v in votes if v['verdict'] == 'changes')} changes"]
    return "\n".join(L)


def cmd_stats(a):
    print(stats_text())


def cmd_html(a):
    allt = load_all(); ds = parse_decisions(); c = config()
    e = html.escape
    rows = "".join(f"<tr><td>{e(t)}</td><td>{e(x.get('feature',''))}</td><td>{e(x.get('title',''))}</td><td class='s-{e(x.get('status',''))}'>{e(x.get('status',''))}</td><td>{e(x.get('risk',''))}</td><td>{e(', '.join(x.get('owns',[])))}</td></tr>" for t, x in sorted(allt.items()))
    feats = "".join(f"<li><b>{e(fid)}</b> {e(load_feature(fid).get('title',''))} — {e(load_feature(fid).get('status',''))}" + (f" · <a href='features/{fid}/summary.md'>summary</a>" if os.path.isfile(os.path.join(FEATURES, fid, 'summary.md')) else "") + "</li>" for fid in feature_ids())
    decs = "".join(f"<tr><td>{e(d['id'])}</td><td>{e(d['date'])}</td><td>{e(d['ticket'])}</td><td>{e(d['by'])}</td><td>{e(d.get('question',''))}</td><td>{e(d.get('decided',''))}</td><td>{e(d.get('dissent','none'))}</td><td>{e(d.get('overridden_by',''))}</td></tr>" for d in reversed(ds))
    page = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Factory board</title>
<style>:root{{--bg:#fff;--fg:#1a1a1a;--mute:#666;--line:#ddd;--ok:#2a7;--warn:#c80;--bad:#c33}}@media(prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--mute:#999;--line:#333}}}}
body{{font:14px/1.5 system-ui,sans-serif;margin:0;padding:16px;background:var(--bg);color:var(--fg)}}table{{border-collapse:collapse;width:100%;margin:8px 0 24px}}td,th{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}th{{color:var(--mute);font-weight:600}}
.s-done{{color:var(--ok)}}.s-blocked{{color:var(--bad)}}.s-running,.s-review{{color:var(--warn)}}pre{{white-space:pre-wrap;background:rgba(127,127,127,.08);padding:12px;border-radius:8px}}h1,h2{{margin:16px 0 4px}}small{{color:var(--mute)}}</style></head><body>
<h1>Factory board <small>{e(now())} · branch {e(str(c['branch']))} · promote {e(str(c['promote']))} · concurrency {e(str(c['concurrency']))}{' · PAUSED' if str(c.get('paused')).lower() == 'true' else ''}</small></h1>
<h2>Features</h2><ul>{feats or '<li>none yet</li>'}</ul>
<h2>Tickets</h2><table><tr><th>Ticket</th><th>Feature</th><th>Title</th><th>Status</th><th>Risk</th><th>Owns</th></tr>{rows}</table>
<h2>Run</h2><pre>{e(stats_text())}</pre>
<h2>Decisions <small>newest first</small></h2><table><tr><th>Id</th><th>Date</th><th>Ticket</th><th>By</th><th>Question</th><th>Decided</th><th>Dissent</th><th>Overridden by</th></tr>{decs}</table>
</body></html>"""
    write(os.path.join(ROOT, "dashboard.html"), page); print("wrote tickets/dashboard.html")


# ---------------------------------------------------------------- github

def need_gh():
    if not shutil.which("gh"): fail("the GitHub CLI (gh) is not installed or not on PATH; install it and run `gh auth login`")


def cmd_import_issue(a):
    need_gh()
    r = sh(["gh", "issue", "view", str(a.number), "--json", "title,body,labels,url,author"])
    issue = json.loads(r.stdout); labels = [l["name"] for l in issue.get("labels", [])]
    allow = os.path.join(ROOT, "ALLOWLIST.md")
    if os.path.isfile(allow) and issue.get("author", {}).get("login") and issue["author"]["login"] not in read(allow):
        append(os.path.join(ROOT, "INBOX.md"), f"- {now()} issue #{a.number} by {issue['author']['login']} is not on the allowlist; recorded, not started: {issue['url']}\n")
        fail(f"author {issue['author']['login']} is not in tickets/ALLOWLIST.md; recorded in INBOX.md")
    ns = argparse.Namespace(title=issue["title"], mode="solo", depends="", owns="", risk=("high" if "risk:high" in labels else "medium" if "risk:medium" in labels else "low"), kind=a.kind, deliverable="", feature=a.feature or "", reviews="")
    before = set(ticket_ids()); cmd_new(ns); tid = sorted(set(ticket_ids()) - before)[0]
    t = load(tid); body = replace_section(t["_body"], "Context the worker needs", f"- From GitHub issue #{a.number}: {issue['url']}\n- Labels: {', '.join(labels) or 'none'}\n\n{(issue.get('body') or '').strip()}")
    fm, _ = split_frontmatter(t["_text"]); save_ticket(t, "---\n" + fm + "\n---\n" + body)
    print(f"{tid} drafted from issue #{a.number}; the intake fills owns, deliverable, eval rows and reviews before it is ready")


def cmd_pr(a):
    need_gh(); c = config(); allt = load_all()
    if a.id.startswith("F-"):
        f = load_feature(a.id); title = f"{a.id}: {f.get('title','')}"
        summ = os.path.join(FEATURES, a.id, "summary.md"); body = read(summ) if os.path.isfile(summ) else f.get("_body", "")
        if f.get("pr"): fail(f"{a.id} already has pull request {f['pr']}")
    elif a.id in allt:
        t = allt[a.id]; title = f"{a.id}: {t.get('title','')}"; body = t["_body"]
        if t.get("pr"): fail(f"{a.id} already has pull request {t['pr']}")
    else: fail(f"unknown feature or ticket {a.id}")
    base = a.base or "main"; head = c["branch"]
    # record the intent before the request exists, so a crash between the two steps leaves a trace
    marker = os.path.join(ROOT, f".pr-{a.id}.pending"); write(marker, f"{now()} opening PR {head} -> {base} for {a.id}\n")
    sh(["git", "push", "-u", "origin", head])
    r = sh(["gh", "pr", "create", "--base", base, "--head", head, "--title", title, "--body", body + f"\n\n---\nOpened by the factory from `{head}`. Review the summary; rework by writing in review.md."])
    url = r.stdout.strip().splitlines()[-1]
    if a.id.startswith("F-"): write(f["_path"], set_frontmatter_value(f["_text"], "pr", url))
    else: save_ticket(t, set_frontmatter_value(t["_text"], "pr", url))
    os.remove(marker); print(url)


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(f=cmd_init)
    sub.add_parser("config").set_defaults(f=cmd_config)
    s = sub.add_parser("feature"); s.add_argument("action"); s.add_argument("title", nargs="?"); s.add_argument("value", nargs="?"); s.add_argument("--request", default=""); s.add_argument("--by", default=""); s.set_defaults(f=cmd_feature)
    s = sub.add_parser("new"); s.add_argument("title"); s.add_argument("--mode", default="solo", choices=["solo", "team"]); s.add_argument("--depends", default=""); s.add_argument("--owns", default=""); s.add_argument("--risk", default="low", choices=["low", "medium", "high"]); s.add_argument("--kind", default="code", choices=["code", "document", "analysis", "operations"]); s.add_argument("--deliverable", default=""); s.add_argument("--feature", default=""); s.add_argument("--reviews", default=""); s.set_defaults(f=cmd_new)
    s = sub.add_parser("validate"); s.add_argument("id", nargs="?"); s.set_defaults(f=lambda a: [validate(t, allt) for allt in [load_all()] for t in ([a.id] if a.id else sorted(allt))])
    s = sub.add_parser("ready"); s.add_argument("id"); s.set_defaults(f=lambda a: cmd_status(argparse.Namespace(id=a.id, status="ready")))
    s = sub.add_parser("status"); s.add_argument("id"); s.add_argument("status"); s.set_defaults(f=cmd_status)
    sub.add_parser("next").set_defaults(f=cmd_next)
    sub.add_parser("board").set_defaults(f=lambda a: write_board(load_all()) or print("board rewritten"))
    s = sub.add_parser("precedent"); s.add_argument("words"); s.set_defaults(f=cmd_precedent)
    s = sub.add_parser("decide"); s.add_argument("id"); s.add_argument("--question", required=True); s.add_argument("--decided", required=True); s.add_argument("--why", required=True); s.add_argument("--by", required=True); s.add_argument("--options", default=""); s.add_argument("--level", default="standard", choices=["trivial", "standard", "high"]); s.add_argument("--precedent", default=""); s.add_argument("--dissent", default=""); s.add_argument("--reversible", default="yes", choices=["yes", "no"]); s.add_argument("--overrides", default=""); s.set_defaults(f=cmd_decide)
    s = sub.add_parser("resolve"); s.add_argument("id"); s.add_argument("--decision", required=True); s.add_argument("--question", type=int, default=0); s.set_defaults(f=cmd_resolve)
    s = sub.add_parser("gate"); s.add_argument("id"); s.add_argument("--dir", default=""); s.set_defaults(f=cmd_gate)
    s = sub.add_parser("vote"); s.add_argument("id"); s.add_argument("--role", required=True); s.add_argument("--verdict", required=True); s.add_argument("--why", required=True); s.set_defaults(f=cmd_vote)
    s = sub.add_parser("verdict"); s.add_argument("id"); s.set_defaults(f=cmd_verdict)
    s = sub.add_parser("rework"); s.add_argument("id"); s.add_argument("--note", required=True); s.add_argument("--overrides", default=""); s.add_argument("--owns", default=""); s.set_defaults(f=cmd_rework)
    s = sub.add_parser("log"); s.add_argument("id"); s.add_argument("--attempt", default=1, type=int); s.add_argument("--minutes", required=True); s.add_argument("--questions", default=0); s.add_argument("--returned", default=0); s.add_argument("--defects", default=0); s.add_argument("--restarts", default=0); s.add_argument("--tokens", default=""); s.set_defaults(f=cmd_log)
    sub.add_parser("stats").set_defaults(f=cmd_stats)
    sub.add_parser("html").set_defaults(f=cmd_html)
    s = sub.add_parser("import-issue"); s.add_argument("number", type=int); s.add_argument("--kind", default="code", choices=["code", "document", "analysis", "operations"]); s.add_argument("--feature", default=""); s.set_defaults(f=cmd_import_issue)
    s = sub.add_parser("pr"); s.add_argument("id"); s.add_argument("--base", default=""); s.set_defaults(f=cmd_pr)
    args = p.parse_args(); args.f(args)


if __name__ == "__main__":
    main()
