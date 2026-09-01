#!/usr/bin/env bash
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"
SUB="$DIR/../submission"

# ENTRY.md (the submission metadata file: name, GitHub handle, email) was
# part of the submitted package but is not published here, so it is not
# checked for.
for f in CLAUDE.md FAILURE-CLASSES.md FIRST_PROMPT.md CONTINUE_BUILD_PROMPT.md CONTINUE_RESERVE_PROMPT.md; do
  assert_eq "0" "$( [ -s "$SUB/$f" ] && echo 0 || echo 1 )" "$f exists and is non-empty"
done

failure_classes="$(cat "$SUB/FAILURE-CLASSES.md")"
for marker in "hardcoded match" "circular by construction" "solved backward" "wrong in its own favor" "actually been attacked" "never actually run" "genuinely independent real counterpart"; do
  assert_contains "$failure_classes" "$marker" "FAILURE-CLASSES.md covers: $marker"
done

claude_md="$(cat "$SUB/CLAUDE.md")"
assert_contains "$claude_md" "FAILURE-CLASSES.md" "CLAUDE.md references FAILURE-CLASSES.md"
assert_contains "$claude_md" "lib/retry.sh" "CLAUDE.md references lib/retry.sh"
assert_contains "$claude_md" "retry" "CLAUDE.md mentions the retry helper by name"

first="$(cat "$SUB/FIRST_PROMPT.md")"
assert_contains "$first" "{{BUDGET}}" "FIRST_PROMPT.md has a {{BUDGET}} token"

build="$(cat "$SUB/CONTINUE_BUILD_PROMPT.md")"
assert_contains "$build" "{{REMAINING}}" "CONTINUE_BUILD_PROMPT.md has a {{REMAINING}} token"

reserve="$(cat "$SUB/CONTINUE_RESERVE_PROMPT.md")"
assert_contains "$reserve" "{{REMAINING}}" "CONTINUE_RESERVE_PROMPT.md has a {{REMAINING}} token"
assert_contains "$reserve" "{{MIN_ROUND}}" "CONTINUE_RESERVE_PROMPT.md has a {{MIN_ROUND}} token"
assert_contains "$reserve" "FAILURE-CLASSES.md" "CONTINUE_RESERVE_PROMPT.md references FAILURE-CLASSES.md"
assert_contains "$reserve" "Task tool" "CONTINUE_RESERVE_PROMPT.md instructs using the Task tool"
assert_contains "$reserve" "Reflection" "CONTINUE_RESERVE_PROMPT.md instructs a Reflection section in README.md"
assert_contains "$reserve" "weakest remaining claim" "CONTINUE_RESERVE_PROMPT.md covers the weakness question"
assert_contains "$reserve" "most consequential design decision" "CONTINUE_RESERVE_PROMPT.md covers the decision-defense question"
assert_contains "$reserve" "you never got" "CONTINUE_RESERVE_PROMPT.md covers the verification question"
assert_contains "$reserve" "another 30 minutes" "CONTINUE_RESERVE_PROMPT.md covers the counterfactual question"
assert_contains "$reserve" "recall check" "CONTINUE_RESERVE_PROMPT.md covers the recall-check question"
assert_contains "$reserve" "three fresh subagents" "CONTINUE_RESERVE_PROMPT.md dispatches three parallel subagents, not one"
assert_contains "$reserve" "same response" "CONTINUE_RESERVE_PROMPT.md instructs dispatching the three subagents in parallel, not serially"
assert_contains "$reserve" "Baseline builder" "CONTINUE_RESERVE_PROMPT.md's audit includes a persona dedicated to proactively building a steelman baseline"
assert_contains "$reserve" "Attacker" "CONTINUE_RESERVE_PROMPT.md's audit includes a dedicated security-attack persona"
assert_contains "$reserve" "Verification skeptic" "CONTINUE_RESERVE_PROMPT.md's audit includes a dedicated hollow-verification-hunting persona"

# Reflection-crowding fix (real dry runs OQ-130, OQ-112 both lost the
# Reflection section to a final-call cutoff): the Reflection must now be
# drafted immediately, before the audit is dispatched, not saved entirely
# for a final step that a cutoff can erase.
assert_contains "$reserve" "write and commit a" "CONTINUE_RESERVE_PROMPT.md instructs writing a Reflection draft, not just describing one"
assert_contains "$reserve" "Commit this draft before moving on to step 3" "CONTINUE_RESERVE_PROMPT.md commits the Reflection draft before dispatching the audit"
assert_contains "$reserve" "never leave a stub heading" "CONTINUE_RESERVE_PROMPT.md forbids a placeholder/stub Reflection heading"
assert_contains "$reserve" "already stands and is" "CONTINUE_RESERVE_PROMPT.md treats the early draft as sufficient on its own if the final refine step is never reached"

# The draft-Reflection step must appear before the audit-dispatch step in
# the file (line order), not just be present somewhere in the text --
# that ordering is the entire point of the fix.
draft_line="$(grep -n 'write and commit a' "$SUB/CONTINUE_RESERVE_PROMPT.md" | head -1 | cut -d: -f1)"
dispatch_line="$(grep -n 'Dispatch three fresh subagents' "$SUB/CONTINUE_RESERVE_PROMPT.md" | head -1 | cut -d: -f1)"
assert_eq "0" "$( [ "$draft_line" -lt "$dispatch_line" ] && echo 0 || echo 1 )" "CONTINUE_RESERVE_PROMPT.md drafts the Reflection (line $draft_line) before dispatching the audit (line $dispatch_line)"

summary
exit $?
