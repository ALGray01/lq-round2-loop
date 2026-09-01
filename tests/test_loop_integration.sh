#!/usr/bin/env bash
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"

WORKDIR="$(mktemp -d)"
STATE_DIR="$(mktemp -d)"

cp -r "$DIR/../submission/." "$WORKDIR/"
mkdir -p "$WORKDIR/bin"
cp "$DIR/fake_claude.sh" "$WORKDIR/bin/claude"
chmod +x "$WORKDIR/bin/claude" "$WORKDIR/loop.sh"

echo "TESTQUESTIONMARKER123 — a fake brief for integration testing." > "$WORKDIR/QUESTION.md"

(
  cd "$WORKDIR"
  export PATH="$WORKDIR/bin:$PATH"
  export BUDGET=133
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR"
  export FAKE_CLAUDE_TURNS_SEQUENCE="50,50,20,10,3"
  bash loop.sh
)
loop_exit=$?
assert_eq "0" "$loop_exit" "loop.sh exits cleanly once budget is exhausted"

calls="$(cat "$STATE_DIR/count")"
assert_eq "5" "$calls" "fake_claude was invoked exactly 5 times for this sequence (50+50+20+10+3=130, then a final 3-turn call reaches 133)"

log="$STATE_DIR/calls.log"
call1="$(awk '/=== call 1 ===/{f=1;next}/=== call 2 ===/{f=0}f' "$log")"
call2="$(awk '/=== call 2 ===/{f=1;next}/=== call 3 ===/{f=0}f' "$log")"
call3="$(awk '/=== call 3 ===/{f=1;next}/=== call 4 ===/{f=0}f' "$log")"
call4="$(awk '/=== call 4 ===/{f=1;next}/=== call 5 ===/{f=0}f' "$log")"
call5="$(awk '/=== call 5 ===/{f=1;next}f' "$log")"

assert_contains "$call1" "TESTQUESTIONMARKER123" "call 1 (first prompt) includes the question brief"
assert_not_contains "$call1" "-c" "call 1 does not pass -c (fresh session)"

assert_contains "$call2" "-c" "call 2 passes -c (continuation)"
assert_contains "$call2" "Keep building" "call 2 (remaining=83, above reserve=34) uses the build-phase prompt"
assert_contains "$call3" "FAILURE-CLASSES.md" "call 3 (remaining=33, at/below reserve=34) uses the reserve-phase prompt"

assert_contains "$call4" "FAILURE-CLASSES.md" "call 4 (remaining=13, at/below reserve=34) uses the reserve-phase prompt"
assert_contains "$call5" "FAILURE-CLASSES.md" "call 5 (remaining=3, at/below reserve=34) uses the reserve-phase prompt"

rm -rf "$WORKDIR" "$STATE_DIR"
summary
exit $?
