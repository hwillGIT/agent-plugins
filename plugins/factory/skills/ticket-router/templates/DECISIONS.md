# Decisions

The ledger every panel reads before it argues and every worker reads before it asks. One entry per question settled, written only by `tickets.py decide`. Precedent order when entries conflict: a person's decision, then a panel decision that followed precedent, then a panel decision on a new question, then a worker's own call. An entry a person later overrode keeps its text and gains an `Overridden by` line; the override is the precedent from then on.

Entry shape (the script writes it; shown here so a reader knows the fields):

```
## D-nnn · <date> · T-nnn · <by> · <level>
- Question: what was asked, in one sentence
- Options: a | b | c
- Decided: the option taken
- Why: the reasons that carried it — precedent cited, standard cited, pattern observed in the code or history
- Precedent: D-nnn (followed) | none
- Dissent: who disagreed and on what, or none
- Reversible: yes | no
```

`by` is one of: council (a panel reached consensus), arbiter (a split panel, ruled on the reasons), worker (a trivial call, noted), person (asked or reworked), escalated (the panel could not settle it and a person answered).
