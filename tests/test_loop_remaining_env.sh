#!/usr/bin/env bash
# Fix 5 regression test: loop.sh must initialize `spent` from $REMAINING
# (when set and different from $BUDGET), not always assume the full budget
# is untouched — otherwise a runner-side restart mid-question (relaunching
# loop.sh with $REMAINING already below $BUDGET) would wrongly believe it
# has the full budget again.
#
# BUDGET=133, REMAINING=10 simulates a restart with 123 turns already
# spent. RESERVE for BUDGET=133 is 34, so remaining=10 is already inside
# the reserve phase (10 <= 34) — the single scripted call is capped at
# --max-turns=9 (reserve-phase cap = remaining-1, the headroom fix for the
# real CLI's num_turns=cap+1 cutoff-reporting quirk — see loop.sh), not
# 133. FAKE_CLAUDE_ENFORCE_MAX_TURNS is not set here, so fake_claude still
# reports the full scripted 10 turns regardless of the 9 passed on argv —
# this test isn't exercising the clamp itself (test_loop_reserve_cap.sh
# does that), only that --max-turns reflects $REMAINING, not $BUDGET. If
# spent were wrongly reset to 0 (the pre-fix bug), --max-turns would be
# capped near 99 (133-34, build phase) instead, and far more than 9-10
# turns of budget would appear available.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"

WORKDIR="$(mktemp -d)"
STATE_DIR="$(mktemp -d)"
cp -r "$DIR/../submission/." "$WORKDIR/"
mkdir -p "$WORKDIR/bin"
cp "$DIR/fake_claude.sh" "$WORKDIR/bin/claude"
chmod +x "$WORKDIR/bin/claude" "$WORKDIR/loop.sh"
echo "TESTQUESTIONMARKER — REMAINING-env resume test." > "$WORKDIR/QUESTION.md"

(
  cd "$WORKDIR"
  export PATH="$WORKDIR/bin:$PATH"
  export BUDGET=133
  export REMAINING=10
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR"
  export FAKE_CLAUDE_TURNS_SEQUENCE="10"
  bash loop.sh > "$STATE_DIR/stdout.log" 2> "$STATE_DIR/stderr.log"
)
loop_exit=$?
assert_eq "0" "$loop_exit" "loop.sh exits cleanly once the (already mostly-spent) budget is exhausted"

calls="$(cat "$STATE_DIR/count")"
assert_eq "1" "$calls" "only 1 call happens — spent correctly started at 123 (133-10), not 0"

call1="$(cat "$STATE_DIR/calls.log")"
call1_max_turns="$(printf '%s\n' "$call1" | awk '/--max-turns/{getline; print; exit}')"
assert_eq "9" "$call1_max_turns" "call 1's --max-turns is capped to REMAINING-1=9 (reserve phase, since 10<=RESERVE=27), proving spent was seeded from \$REMAINING rather than reset to 0"

assert_contains "$(cat "$STATE_DIR/stdout.log")" "budget exhausted (133/133 turns spent over 1 loop(s))" "loop.sh correctly accounts the pre-existing 123 spent turns plus this call's 10"

rm -rf "$WORKDIR" "$STATE_DIR"
summary
exit $?
