#!/usr/bin/env bash
# Fix 1 regression test: a build-phase invocation must be capped at the
# distance to the reserve threshold (remaining - RESERVE), not at the full
# remaining budget — otherwise a single long build-phase call can consume
# the entire remaining budget in one shot and skip the reserve phase (and
# the fresh-context audit it triggers) entirely.
#
# We simulate "the model would have kept going well past the reserve
# boundary if allowed" by scripting a "desired" turn count for the second
# call that is far larger than what a properly-capped --max-turns would
# allow. fake_claude.sh, with FAKE_CLAUDE_ENFORCE_MAX_TURNS=1, clamps its
# reported num_turns to whatever --max-turns value loop.sh actually passed
# (mirroring the real `claude` CLI's observed behavior: exit 1, subtype
# "error_max_turns", when a call is cut off at its own cap — see
# final-fix-report.md for the empirical trace this mirrors).
#
# BUDGET=133 -> RESERVE=34 (ceil(133*25/100)).
#   call 1 (loop_num=0): remaining=133, build phase, cap=133-34=99.
#     desired=50 <= 99 -> finishes naturally, spent=50, remaining=83.
#   call 2 (loop_num=1): remaining=83, build phase, cap=83-34=49.
#     desired=500 > 49 -> clamped to 49 (exit 1, error_max_turns).
#     UNCAPPED (old) code would instead pass --max-turns=83 here, and
#     fake_claude would clamp to 83 instead of 49 — spent would jump to
#     50+83=133, remaining=0, and the loop would exit "budget exhausted"
#     WITHOUT ever sending the reserve-phase prompt. Old code also had no
#     special-case for exit-code-1-with-error_max_turns, so it would
#     additionally just `break` on call 2's non-zero exit — either way,
#     call 3 below never happens under the old code.
#   call 3 (loop_num=2): remaining=133-99=34, reserve phase (34<=34) ->
#     CONTINUE_RESERVE_PROMPT.md is used. This is the assertion that proves
#     the reserve phase was actually reached before the budget ran out.
#     Reserve-phase cap is remaining-1=33 (see loop.sh), not the full
#     remaining=34 — a defensive headroom fix for a confirmed real-CLI
#     reporting quirk where a genuine --max-turns cutoff reports
#     num_turns=cap+1, which could otherwise push cumulative spent one turn
#     over BUDGET on the run's final call (observed in real dry runs
#     OQ-009-v2 and OQ-008: 227/226 and 134/133).
#     desired=34 > cap=33 -> clamped to 33, spent=132, remaining=1.
#   call 4 (loop_num=3): remaining=1, reserve phase, cap=max(1-1,1)=1.
#     desired=1 -> finishes naturally, spent=133, remaining=0, loop exits
#     cleanly.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"

WORKDIR="$(mktemp -d)"
STATE_DIR="$(mktemp -d)"

cp -r "$DIR/../submission/." "$WORKDIR/"
mkdir -p "$WORKDIR/bin"
cp "$DIR/fake_claude.sh" "$WORKDIR/bin/claude"
chmod +x "$WORKDIR/bin/claude" "$WORKDIR/loop.sh"

echo "TESTQUESTIONMARKER — reserve-cap straddle test." > "$WORKDIR/QUESTION.md"

(
  cd "$WORKDIR"
  export PATH="$WORKDIR/bin:$PATH"
  export BUDGET=133
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR"
  export FAKE_CLAUDE_ENFORCE_MAX_TURNS=1
  export FAKE_CLAUDE_TURNS_SEQUENCE="50,500,34,1"
  bash loop.sh
)
loop_exit=$?
assert_eq "0" "$loop_exit" "loop.sh exits cleanly once budget is exhausted"

calls="$(cat "$STATE_DIR/count")"
assert_eq "4" "$calls" "all 4 scripted calls happened (old/uncapped code would have stopped after 2, and pre-headroom-fix code would have stopped after 3)"

log="$STATE_DIR/calls.log"
call2="$(awk '/=== call 2 ===/{f=1;next}/=== call 3 ===/{f=0}f' "$log")"
call3="$(awk '/=== call 3 ===/{f=1;next}/=== call 4 ===/{f=0}f' "$log")"
call4="$(awk '/=== call 4 ===/{f=1;next}f' "$log")"

# The critical assertion: call 2's --max-turns argument must be capped to
# the reserve boundary (49), not the full remaining budget (83).
call2_max_turns="$(printf '%s\n' "$call2" | awk '/--max-turns/{getline; print; exit}')"
assert_eq "49" "$call2_max_turns" "call 2 (remaining=83, build phase) is capped to remaining-RESERVE=49, not the full remaining=83"

assert_contains "$call3" "-c" "call 3 passes -c (continuation)"
assert_contains "$call3" "FAILURE-CLASSES.md" "call 3 (remaining=34, at reserve=34) uses the reserve-phase prompt — proving control returned to loop.sh before the budget ran out"

# The headroom-fix assertion: call 3's --max-turns must be capped to
# remaining-1=33, not the full remaining=34 — this is what forces a 4th call
# to exist at all, and is what prevents a genuine cutoff here from reporting
# num_turns=35 (one over what "remaining=34" would allow).
call3_max_turns="$(printf '%s\n' "$call3" | awk '/--max-turns/{getline; print; exit}')"
assert_eq "33" "$call3_max_turns" "call 3 (remaining=34, reserve phase) is capped to remaining-1=33, not the full remaining=34"

assert_contains "$call4" "-c" "call 4 passes -c (continuation)"
assert_contains "$call4" "FAILURE-CLASSES.md" "call 4 (remaining=1, still <= reserve=34) uses the reserve-phase prompt"
call4_max_turns="$(printf '%s\n' "$call4" | awk '/--max-turns/{getline; print; exit}')"
assert_eq "1" "$call4_max_turns" "call 4 (remaining=1, reserve phase) has cap floored at 1, not 0"

rm -rf "$WORKDIR" "$STATE_DIR"
summary
exit $?
