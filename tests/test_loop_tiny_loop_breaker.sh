#!/usr/bin/env bash
# Regression test for the tiny-consecutive-loop circuit breaker ported from
# the machine's own reference runner (run-baseline.ts:154). The
# continue-vs-retry logic in loop.sh trusts ANY positive num_turns as real
# progress, regardless of exit_code/is_error/terminal_reason (see
# final-fix-report.md) — which is correct for a genuine --max-turns cutoff,
# but means a persistent tiny-turn response (e.g. is_error:true with
# num_turns:1 — a real shape) would otherwise read as normal progress
# forever and silently churn through the whole remaining budget one turn at
# a time, with no backoff and no give-up (the retry path is only reachable
# when turns<=0, never for a small-but-positive turn count). This test
# doesn't need to reproduce the exact is_error:true/nonzero-exit shape to
# prove the fix: the breaker's logic only looks at `turns`, not exit_code or
# is_error, so a plain scripted small-turns sequence exercises the exact
# same code path.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"

# --- Case A: two consecutive tiny loops -> loop.sh stops early -------------
WORKDIR1="$(mktemp -d)"
STATE_DIR1="$(mktemp -d)"
cp -r "$DIR/../submission/." "$WORKDIR1/"
mkdir -p "$WORKDIR1/bin"
cp "$DIR/fake_claude.sh" "$WORKDIR1/bin/claude"
chmod +x "$WORKDIR1/bin/claude" "$WORKDIR1/loop.sh"
echo "TESTQUESTIONMARKER — tiny-loop breaker test A." > "$WORKDIR1/QUESTION.md"

(
  cd "$WORKDIR1"
  export PATH="$WORKDIR1/bin:$PATH"
  export BUDGET=133
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR1"
  # Two consecutive 1-turn "loops" — the stuck-session shape.
  export FAKE_CLAUDE_TURNS_SEQUENCE="1,1"
  bash loop.sh > "$STATE_DIR1/stdout.log" 2> "$STATE_DIR1/stderr.log"
)
loop_exit1=$?
calls1="$(cat "$STATE_DIR1/count")"
assert_eq "1" "$loop_exit1" "case A: loop.sh exits non-zero once it detects 2 consecutive tiny loops"
assert_eq "2" "$calls1" "case A: loop.sh stopped after exactly 2 calls — it did not keep churning through the rest of the 133-turn budget one turn at a time"
assert_contains "$(cat "$STATE_DIR1/stderr.log")" "two consecutive tiny" "case A: loop.sh logs a clear circuit-breaker message"
rm -rf "$WORKDIR1" "$STATE_DIR1"

# --- Case B: one tiny loop, then a normal loop -> counter resets, no trip --
WORKDIR2="$(mktemp -d)"
STATE_DIR2="$(mktemp -d)"
cp -r "$DIR/../submission/." "$WORKDIR2/"
mkdir -p "$WORKDIR2/bin"
cp "$DIR/fake_claude.sh" "$WORKDIR2/bin/claude"
chmod +x "$WORKDIR2/bin/claude" "$WORKDIR2/loop.sh"
echo "TESTQUESTIONMARKER — tiny-loop breaker test B." > "$WORKDIR2/QUESTION.md"

(
  cd "$WORKDIR2"
  export PATH="$WORKDIR2/bin:$PATH"
  export BUDGET=133
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR2"
  # tiny, normal (resets the counter), tiny, tiny (trips on the 4th call —
  # proves a single tiny loop followed by a normal one does NOT trip the
  # breaker, while two genuinely *consecutive* tiny loops still does).
  export FAKE_CLAUDE_TURNS_SEQUENCE="1,50,1,1"
  bash loop.sh > "$STATE_DIR2/stdout.log" 2> "$STATE_DIR2/stderr.log"
)
loop_exit2=$?
calls2="$(cat "$STATE_DIR2/count")"
assert_eq "1" "$loop_exit2" "case B: loop.sh eventually exits non-zero once 2 genuinely consecutive tiny loops occur"
assert_eq "4" "$calls2" "case B: all 4 scripted calls happened — the single tiny loop at call 1, followed by a normal call 2, did not trip the breaker early"
stdout2="$(cat "$STATE_DIR2/stdout.log")"
assert_contains "$stdout2" "loop 1 used 1 turns" "case B: call 1's tiny turn count was still counted normally"
assert_contains "$stdout2" "loop 2 used 50 turns" "case B: call 2 (the counter-resetting normal loop) ran and was counted"
assert_contains "$(cat "$STATE_DIR2/stderr.log")" "two consecutive tiny" "case B: the breaker still fires once calls 3 and 4 are genuinely consecutive tiny loops"
rm -rf "$WORKDIR2" "$STATE_DIR2"

# --- Case C: reserve-boundary cap ("turns == cap") must NOT count as tiny --
# Reproduces the interaction bug caught by re-review: a build-phase call
# right at the reserve boundary can legitimately get `cap` as small as 1,
# and the real CLI reports `turns == cap` when cut off at that self-imposed
# limit — indistinguishable from a "tiny" loop by raw turn count alone, but
# not evidence of anything being stuck; the model just ran out of the small
# allowance loop.sh itself gave it. A naturally-short reserve-phase call
# right after (e.g. "audit found nothing, already committed, done" — a
# healthy outcome) must not combine with that capped call to falsely trip
# the breaker.
#
# BUDGET=15 -> RESERVE=ceil(15*25/100)=4.
#   loop 0: remaining=15, build phase, cap=15-4=11. desired=10<=11, no
#     clamp, turns=10 (spent=10, remaining=5).
#   loop 1: remaining=5, build phase, cap=5-4=1. desired=50>1, CLAMPED to
#     cap=1 (the reserve-boundary cap in action) -> turns=1, turns==cap, so
#     the fix's `turns < cap` guard must exclude this from the tiny count
#     (spent=11, remaining=4).
#   loop 2: remaining=4, reserve phase (4<=4), cap=remaining-1=3 (headroom
#     fix — see loop.sh). desired=1, strictly < cap(3) — a genuinely
#     voluntary tiny result, not a boundary clamp. Excluded from the tiny
#     count purely by the remaining_after gate: spent=12, remaining_after=3
#     is not > MIN_ROUND_TURNS(12) (spent=12, remaining=3).
#   loop 3: remaining=3, reserve phase, cap=3-1=2. desired=50>2, CLAMPED to
#     cap=2, turns==cap, excluded via the turns<cap guard (spent=14,
#     remaining=1).
#   loop 4: remaining=1, reserve phase, cap=max(1-1,1)=1. desired=1, not >
#     cap(1), no clamp, turns=1==cap again (boundary-capped) (spent=15,
#     remaining=0 -> budget exhausted, clean exit).
# The breaker must never fire anywhere in this sequence.
WORKDIR3="$(mktemp -d)"
STATE_DIR3="$(mktemp -d)"
cp -r "$DIR/../submission/." "$WORKDIR3/"
mkdir -p "$WORKDIR3/bin"
cp "$DIR/fake_claude.sh" "$WORKDIR3/bin/claude"
chmod +x "$WORKDIR3/bin/claude" "$WORKDIR3/loop.sh"
echo "TESTQUESTIONMARKER — tiny-loop breaker test C (reserve-boundary reproduction)." > "$WORKDIR3/QUESTION.md"

(
  cd "$WORKDIR3"
  export PATH="$WORKDIR3/bin:$PATH"
  export BUDGET=15
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR3"
  export FAKE_CLAUDE_ENFORCE_MAX_TURNS=1
  export FAKE_CLAUDE_TURNS_SEQUENCE="10,50,1,50,1"
  bash loop.sh > "$STATE_DIR3/stdout.log" 2> "$STATE_DIR3/stderr.log"
)
loop_exit3=$?
calls3="$(cat "$STATE_DIR3/count")"
assert_eq "0" "$loop_exit3" "case C: loop.sh completes cleanly (budget exhausted) — a perfectly healthy run is NOT killed by the breaker right as it enters the reserve phase"
assert_eq "5" "$calls3" "case C: all 5 calls happened — neither the build-boundary-capped call nor the reserve-phase calls were treated as evidence of a stuck session"

log3="$STATE_DIR3/calls.log"
call2_max_turns="$(printf '%s\n' "$(awk '/=== call 2 ===/{f=1;next}/=== call 3 ===/{f=0}f' "$log3")" | awk '/--max-turns/{getline; print; exit}')"
assert_eq "1" "$call2_max_turns" "case C: call 2's --max-turns was indeed capped to 1 by the reserve-boundary logic (remaining=5, RESERVE=4), reproducing the exact scenario"

stdout3="$(cat "$STATE_DIR3/stdout.log")"
assert_contains "$stdout3" "loop 2 used 1 turns" "case C: the boundary-capped call's 1 turn was still counted toward spent normally"
assert_contains "$stdout3" "budget exhausted (15/15 turns spent over 5 loop(s))" "case C: the run used its full budget rather than being cut short"
assert_not_contains "$(cat "$STATE_DIR3/stderr.log")" "two consecutive tiny" "case C: the circuit breaker never fires anywhere in this sequence"
rm -rf "$WORKDIR3" "$STATE_DIR3"


# --- Case D: two genuine tiny loops with little budget left -> must NOT trip
# Reproduces the real OQ-009 dry run (ROUND2-REFERENCE.md §9.3): two
# consecutive genuine (not reserve-boundary-capped) tiny replies, each the
# model correctly and deliberately declining to start work it might not
# finish, this late in the budget. That's good judgment, not a stuck
# session, and it only actually happened once `remaining` had already
# dropped below MIN_ROUND_TURNS (12) — below that point stopping early
# costs almost nothing anyway. Distinct from Case C: these turns are
# strictly LESS than their cap (genuinely voluntary), not equal to it
# (boundary-capped) — this exercises the new remaining_after>MIN_ROUND gate
# specifically, not the existing turns<cap guard.
#
# BUDGET=50 -> RESERVE=ceil(50*25/100)=13 (now slightly ABOVE
# MIN_ROUND_TURNS=12, so — unlike before the RESERVE_PCT increase — merely
# entering reserve phase no longer guarantees remaining is already below
# MIN_ROUND. The build/first-reserve calls below drain a bit further before
# the genuine-tiny pair this case exists to test. Cap values use the
# headroom-fixed reserve-phase formula (cap=remaining-1, floored at 1 — see
# loop.sh) but FAKE_CLAUDE_ENFORCE_MAX_TURNS is not set in this case, so
# fake_claude never clamps to it regardless — the exact cap value passed as
# --max-turns has no effect on this test's outcome.
#   loop 0: remaining=50, build, cap=37. turns=37 (spent=37, remaining=13).
#   loop 1: remaining=13, reserve (13<=13), cap=12. turns=6 (a normal,
#     non-tiny call that drains remaining below MIN_ROUND_TURNS before the
#     genuine-tiny pair below) (spent=43, remaining=7).
#   loop 2: remaining=7, reserve, cap=6. turns=2 (genuine, 2<6). spent=45,
#     remaining_after=5 (not >12) -> excluded from the tiny count by the new
#     gate, even though turns<=2 and turns<cap both hold.
#   loop 3: remaining=5, reserve, cap=4. turns=2 (genuine, 2<4). spent=47,
#     remaining_after=3 (not >12) -> also excluded. Pre-fix, this pair (loops
#     2 and 3) would have counted as 2 consecutive tiny loops and tripped the
#     breaker here.
#   loop 4: remaining=3, reserve, cap=2. turns=2 (==cap, boundary-excluded by
#     the turns<cap guard regardless) (spent=49, remaining=1).
#   loop 5: remaining=1, reserve, cap=1. turns=1 (==cap, boundary-excluded)
#     (spent=50 -> budget exhausted, clean exit, 6 calls total).
WORKDIR4="$(mktemp -d)"
STATE_DIR4="$(mktemp -d)"
cp -r "$DIR/../submission/." "$WORKDIR4/"
mkdir -p "$WORKDIR4/bin"
cp "$DIR/fake_claude.sh" "$WORKDIR4/bin/claude"
chmod +x "$WORKDIR4/bin/claude" "$WORKDIR4/loop.sh"
echo "TESTQUESTIONMARKER — tiny-loop breaker test D (low-budget genuine-tiny reproduction)." > "$WORKDIR4/QUESTION.md"

(
  cd "$WORKDIR4"
  export PATH="$WORKDIR4/bin:$PATH"
  export BUDGET=50
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR4"
  export FAKE_CLAUDE_TURNS_SEQUENCE="37,6,2,2,2,1"
  bash loop.sh > "$STATE_DIR4/stdout.log" 2> "$STATE_DIR4/stderr.log"
)
loop_exit4=$?
calls4="$(cat "$STATE_DIR4/count")"
assert_eq "0" "$loop_exit4" "case D: loop.sh completes cleanly (budget exhausted) — two genuine tiny loops late in the budget do NOT trip the breaker"
assert_eq "6" "$calls4" "case D: all 6 calls happened — pre-fix, the genuine-tiny pair here would have tripped the breaker"
assert_contains "$(cat "$STATE_DIR4/stdout.log")" "budget exhausted (50/50 turns spent over 6 loop(s))" "case D: the run used its full budget rather than being cut short"
assert_not_contains "$(cat "$STATE_DIR4/stderr.log")" "two consecutive tiny" "case D: the circuit breaker never fires in this sequence"
rm -rf "$WORKDIR4" "$STATE_DIR4"

summary
exit $?
