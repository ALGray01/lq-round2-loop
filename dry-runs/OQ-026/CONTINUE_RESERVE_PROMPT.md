You have {{REMAINING}} assistant turns left of your {{BUDGET}}-turn budget,
and you have now entered your reserve — the point at which stabilizing and
verifying what you have matters more than adding scope.

Do the following, in order, spending only what each step needs:

1. Commit your current state if you haven't. Make sure README.md accurately
   describes what you actually built, not what you intended to build.
2. Dispatch three fresh subagents (use your Task tool three times in the
   same response, so they run in parallel rather than one after another —
   subagent dispatch has proven turn-cheap regardless of how much internal
   work each one does, so there is no budget reason to run them serially).
   None should have prior context of this session. Tell each one explicitly
   that `loop.sh`, `CLAUDE.md`, `FAILURE-CLASSES.md`, `lib/`, and the
   `FIRST_PROMPT.md`/`CONTINUE_*_PROMPT.md` files are harness scaffolding
   provided by the assessment, not part of the deliverable, so neither its
   findings nor README.md should describe or critique the harness itself —
   only the submission built inside this repository.

   All three share the same underlying mandate: find the single most
   examination-averse claim in what's been shipped and verify it against
   actual execution, not by reading — FAILURE-CLASSES.md's checklist and
   the three roles below are how that's split up and operationalized in
   parallel. Keep each subagent's own investigation focused: a rough,
   quickly-built comparison or a handful of concrete attack attempts is
   enough — none of the three should become its own open-ended project.
   Where any subagent needs scratch files for its own work (test scripts,
   attack payloads, a baseline implementation), use clearly separate,
   uniquely-named locations (e.g., `_attacker_`, `_skeptic_`, `_baseline_`
   prefixes) so three simultaneous writers don't collide. None should commit
   anything themselves; you'll decide what's worth keeping and commit it
   in step 3.

   Give each a distinct mandate, all three checking against actual execution, not by reading:
   a. **Attacker**: attack every security-relevant surface (access control,
      permissions, anything reaching a filesystem path or rendered output)
      with crafted input, per FAILURE-CLASSES.md item 5 — and check item 7
      wherever the attack surface involves an external protocol or API.
   b. **Verification skeptic**: hunt for hollow or circular verification —
      FAILURE-CLASSES.md items 1, 2, 3, 4, and 6 — anything claimed
      "tested" or "verified" that doesn't actually prove what it claims.
   c. **Baseline builder**: find the single strongest "this beats /
      is better than / is sufficient versus X" claim in what's been
      shipped so far — whether or not the brief explicitly asked for a
      comparison — and build a genuine boring/naive alternative to test it
      against, honestly reporting the result even if it undercuts the
      claim. If nothing shipped makes an implicit or explicit comparative
      claim, build the naive/boring version of this submission's own core
      approach instead and compare the two directly (every submission
      implicitly claims its approach is worth its complexity over something
      simpler). Also apply FAILURE-CLASSES.md item 7 broadly: is the
      strongest verification evidence anywhere in this repo "I wrote both
      sides of this test"?
   Have each report concrete findings back to you — your three-persona audit.
3. Address what this audit found: fix any defects by severity and re-verify by
   actually re-running what you fixed (do not just re-read the diff); for any
   comparison results or baselines the Baseline builder found, write them
   honestly into README.md — including results that favor the naive/boring
   alternative over what's already shipped, not just findings that are bad news.
4. If, after finishing a full round of steps 2-3, you have more than roughly
   {{MIN_ROUND}} turns left and this audit found real issues, repeat steps 2-3
   once more on the updated state. (On the second round, the Baseline builder
   should look for a different comparison worth making, or attack the validity
   of the first one harder, rather than rebuild the same comparison.)
5. If instead you have turns left and this audit found nothing further,
   spend the remainder on ONE deliberate improvement that raises the ambition
   of the submission (e.g. broader test coverage, an additional real
   comparison, hardening) rather than stopping early — commit it
   incrementally.
6. Before you run out, do a final honesty pass: add a short "Reflection"
   section to README.md (near the end) answering these directly and
   specifically — precise and checkable, not generic reassurance:
   - A recall check: without re-reading the code, write down from memory
     what you built and how the key pieces work — then go verify each
     specific factual claim in that recollection against the actual
     code/output, and correct anything your memory got wrong before
     finalizing this section. This exists to catch confidently
     misremembered behavior you never actually re-confirmed.
   - The single weakest remaining claim in what you've shipped, named
     precisely: which part, why it's weak, how someone could catch it.
   - The single most consequential design decision you made, defended
     against the specific alternative you rejected and why you didn't take
     it.
   - What you actually ran to verify this works, versus what you never got
     to verify — concrete (commands, what you observed), not asserted
     confidence.
   - With another 30 minutes of budget, the first thing you'd do next, and
     why that over anything else.
   Then make a final commit.
