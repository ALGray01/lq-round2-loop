# Failure classes to check for

Six specific, real patterns that recur in AI-built software submissions —
checked here explicitly because a general "review adversarially" instruction
can still miss a familiar-looking trap. This supplements, and never
replaces, the general mandate: find the single most examination-averse claim
in what has been shipped and verify it against actual execution.

1. **Verification that's secretly a hardcoded match dressed up as
   reasoning.** Does anything claimed as "verified" or "checked by a
   model/test" actually just match a literal string or fixed pattern planted
   for the demo, rather than genuinely evaluating the input? Look at the
   actual conditional logic, not the function name.

2. **A self-graded eval or test set that's circular by construction.** Was
   the ground truth (expected answers, labels, scenarios) written by the same
   process, in the same sitting, as the thing being evaluated against it? If
   so, a high score proves the two agree with each other, not that either is
   correct.

3. **A demo or test case "solved backward."** Was the expected output
   computed or decided before the test/scenario input was written, rather
   than the input being run through the real logic to produce the output? If
   so, "it passes" is close to tautological.

4. **A grader/scorer that could be wrong in its own favor.** If there is any
   code that decides pass/fail or computes a score, has it been checked
   against a case it should fail? A scorer that's never been shown a true
   negative can silently overstate results.

5. **A security-relevant gap assumed rather than attacked.** For anything
   involving access control, permissions, or user-supplied input reaching a
   filesystem path or rendered output: has it actually been attacked with a
   crafted input (e.g. a path-traversal string, an unescaped payload, a
   missing-parameter request), not just reasoned about?

6. **A verification/scoring script that exists but was never actually run.**
   Search for any script whose entire purpose is to produce a number or a
   pass/fail verdict. Has it been executed at least once, with its real
   output inspected? A script that compiles but was never invoked proves
   nothing.
