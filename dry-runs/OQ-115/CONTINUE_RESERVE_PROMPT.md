You have {{REMAINING}} assistant turns left of your {{BUDGET}}-turn budget,
and you have now entered your reserve — the point at which stabilizing and
verifying what you have matters more than adding scope.

Do the following, in order, spending only what each step needs:

1. Commit your current state if you haven't. Make sure README.md accurately
   describes what you actually built, not what you intended to build.
2. Dispatch a fresh subagent (use your Task tool) with no prior context of
   this session, and instruct it to adversarially audit this repository —
   telling it explicitly that `loop.sh`, `CLAUDE.md`, `FAILURE-CLASSES.md`,
   `lib/`, and the `FIRST_PROMPT.md`/`CONTINUE_*_PROMPT.md` files are harness
   scaffolding provided by the assessment, not part of the deliverable, so
   neither the audit's findings nor README.md should describe or critique
   the harness itself — only the submission built inside this repository.
   Give it two things:
   a. The general mandate: find the single most examination-averse claim in
      what has been shipped, verify it against actual execution (not by
      reading), and check whether any comparison claim has a real steelman
      baseline to stand against rather than an easy strawman.
   b. The checklist in FAILURE-CLASSES.md — six specific failure patterns to
      check for explicitly, even if none surface from (a).
   Have it report concrete findings back to you.
3. Fix what it found, by severity, and re-verify by actually re-running
   whatever you fixed — do not just re-read the diff.
4. If, after finishing a full round of steps 2-3, you have more than roughly
   {{MIN_ROUND}} turns left and the audit found real issues, repeat steps 2-3
   once more on the updated state.
5. If instead you have turns left and step 2's audit found nothing further,
   spend the remainder on ONE deliberate improvement that raises the ambition
   of the submission (e.g. broader test coverage, an additional real
   comparison, hardening) rather than stopping early — commit it
   incrementally.
6. Before you run out, do a final honesty pass: update README.md to name the
   single weakest remaining claim precisely, and make a final commit.
