#!/usr/bin/env bash
# Fix 2 regression test: a transient (generic, non-max-turns) failure of the
# `claude` invocation itself must be retried a few times with backoff before
# loop.sh gives up — it must not abandon the rest of the budget on the first
# non-zero exit.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"

# --- Case 1: transient failure then success -> run continues ---------------
WORKDIR1="$(mktemp -d)"
STATE_DIR1="$(mktemp -d)"
cp -r "$DIR/../submission/." "$WORKDIR1/"
mkdir -p "$WORKDIR1/bin"
cp "$DIR/fake_claude.sh" "$WORKDIR1/bin/claude"
chmod +x "$WORKDIR1/bin/claude" "$WORKDIR1/loop.sh"
echo "TESTQUESTIONMARKER — retry test 1." > "$WORKDIR1/QUESTION.md"

(
  cd "$WORKDIR1"
  export PATH="$WORKDIR1/bin:$PATH"
  # BUDGET set to land exactly on 60 (50+10) so the run ends cleanly via
  # "budget exhausted" right after the two intended loop iterations,
  # instead of making a 5th, unscripted invocation that would itself need
  # scripting (keeps this test focused on the retry behavior only).
  export BUDGET=60
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR1"
  # Call 1 (the invocation attempt) fails twice transiently, then succeeds
  # on its 3rd attempt; call 2 succeeds outright.
  export FAKE_CLAUDE_EXIT_SEQUENCE="1,1,0,0"
  export FAKE_CLAUDE_TURNS_SEQUENCE="0,0,50,10"
  bash loop.sh > "$STATE_DIR1/stdout.log" 2> "$STATE_DIR1/stderr.log"
)
loop_exit1=$?
calls1="$(cat "$STATE_DIR1/count")"
assert_eq "0" "$loop_exit1" "case 1: loop.sh exits cleanly (still running, budget not yet exhausted at test's scripted end)"
assert_eq "4" "$calls1" "case 1: fake_claude invoked 4 times total — 2 failed attempts + success for loop 0, then loop 1's success"
assert_contains "$(cat "$STATE_DIR1/stderr.log")" "retrying in" "case 1: loop.sh logs a retry message after the transient failures"
assert_contains "$(cat "$STATE_DIR1/stdout.log")" "loop 1 used 50 turns" "case 1: the retried call's turns are still counted once it succeeds"
assert_contains "$(cat "$STATE_DIR1/stdout.log")" "loop 2 used 10 turns" "case 1: the run continues past the retried call to the next loop"
rm -rf "$WORKDIR1" "$STATE_DIR1"

# --- Case 2: persistent failure -> loop.sh gives up cleanly ----------------
WORKDIR2="$(mktemp -d)"
STATE_DIR2="$(mktemp -d)"
cp -r "$DIR/../submission/." "$WORKDIR2/"
mkdir -p "$WORKDIR2/bin"
cp "$DIR/fake_claude.sh" "$WORKDIR2/bin/claude"
chmod +x "$WORKDIR2/bin/claude" "$WORKDIR2/loop.sh"
echo "TESTQUESTIONMARKER — retry test 2." > "$WORKDIR2/QUESTION.md"

(
  cd "$WORKDIR2"
  export PATH="$WORKDIR2/bin:$PATH"
  export BUDGET=133
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR2"
  # Every attempt fails transiently — never recovers.
  export FAKE_CLAUDE_EXIT_SEQUENCE="1,1,1,1,1,1"
  export FAKE_CLAUDE_TURNS_SEQUENCE="0,0,0,0,0,0"
  bash loop.sh > "$STATE_DIR2/stdout.log" 2> "$STATE_DIR2/stderr.log"
)
loop_exit2=$?
calls2="$(cat "$STATE_DIR2/count")"
assert_eq "1" "$loop_exit2" "case 2: loop.sh exits non-zero to signal a genuine failure (distinct from a clean budget-exhausted completion) once it gives up"
assert_eq "3" "$calls2" "case 2: fake_claude was attempted exactly INVOKE_MAX_ATTEMPTS=3 times before giving up, not retried forever"
assert_contains "$(cat "$STATE_DIR2/stderr.log")" "gave up" "case 2: loop.sh logs a clear give-up message"
rm -rf "$WORKDIR2" "$STATE_DIR2"

summary
exit $?
