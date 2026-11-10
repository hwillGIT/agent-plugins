# F-001 review

Yours to write after reading `summary.md`. One line per item. Name the decision id (D-0xx) when you are overturning one; that makes your line the precedent the next panel follows. Leave the file as it is to accept the feature.

Examples of lines that work:

- D-014 is wrong: exports stay CSV; finance opens them in Excel.
- The settings screen hides the save button on a phone (see evidence/after.png in T-007); it must stay visible.
- T-009 went further than asked: remove the audit log; nobody asked for it.

Then say "factory: rework F-001" (or run `tickets.py rework F-001 --note "..." --overrides D-014` per line).

## Rework notes
-
