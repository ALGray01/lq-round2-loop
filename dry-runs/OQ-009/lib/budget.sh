#!/usr/bin/env bash
# Pure budget/threshold math for loop.sh. No side effects, no I/O beyond
# stdout. RESERVE_PCT sizes the tail of the budget set aside for the
# stabilize/audit/fix "reserve phase" (see loop.sh); MIN_ROUND_TURNS is the
# flat floor of turns considered enough to safely fit one more full
# dispatch-audit-fix-verify-commit round within that reserve. Both are
# starting estimates, meant to be validated and adjusted via local dry runs,
# not locked.

RESERVE_PCT=20
MIN_ROUND_TURNS=12

compute_reserve() {
  # $1 = BUDGET (integer > 0). Prints ceil(BUDGET * RESERVE_PCT / 100).
  local budget="$1"
  echo $(( (budget * RESERVE_PCT + 99) / 100 ))
}

compute_min_round() {
  # $1 = BUDGET (accepted for signature stability; unused today — kept in
  # case a future tuning pass wants MIN_ROUND to scale with budget instead
  # of being a flat constant).
  echo "$MIN_ROUND_TURNS"
}

phase_for() {
  # $1 = remaining, $2 = reserve. Prints "build" or "reserve".
  local remaining="$1" reserve="$2"
  if [ "$remaining" -le "$reserve" ]; then
    echo "reserve"
  else
    echo "build"
  fi
}
