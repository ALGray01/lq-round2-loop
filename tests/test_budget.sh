#!/usr/bin/env bash
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"
source "$DIR/../submission/lib/budget.sh"

assert_eq "34" "$(compute_reserve 133)" "reserve for 133-turn budget (ceil(133*25/100))"
assert_eq "49" "$(compute_reserve 196)" "reserve for 196-turn budget"
assert_eq "57" "$(compute_reserve 226)" "reserve for 226-turn budget"
assert_eq "60" "$(compute_reserve 237)" "reserve for 237-turn budget"

assert_eq "12" "$(compute_min_round 133)" "min_round is flat regardless of budget (133)"
assert_eq "12" "$(compute_min_round 237)" "min_round is flat regardless of budget (237)"

assert_eq "build" "$(phase_for 100 34)" "well above reserve is build phase"
assert_eq "reserve" "$(phase_for 34 34)" "exactly at reserve is reserve phase"
assert_eq "reserve" "$(phase_for 5 34)" "below reserve is reserve phase"

summary
exit $?
