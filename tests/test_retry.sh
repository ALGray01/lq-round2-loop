#!/usr/bin/env bash
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"
source "$DIR/../submission/lib/retry.sh"

# Case 1: succeeds on the 3rd attempt
COUNTER_FILE="$(mktemp)"
echo 0 > "$COUNTER_FILE"
flaky_command() {
  local n
  n=$(cat "$COUNTER_FILE")
  n=$(( n + 1 ))
  echo "$n" > "$COUNTER_FILE"
  [ "$n" -ge 3 ]
}
retry 5 0 -- flaky_command
assert_eq "0" "$?" "retry succeeds once flaky_command starts returning success"
assert_eq "3" "$(cat "$COUNTER_FILE")" "flaky_command was called exactly 3 times"
rm -f "$COUNTER_FILE"

# Case 2: never succeeds, gives up after max_attempts
COUNTER_FILE2="$(mktemp)"
echo 0 > "$COUNTER_FILE2"
always_fail() {
  local n
  n=$(cat "$COUNTER_FILE2")
  n=$(( n + 1 ))
  echo "$n" > "$COUNTER_FILE2"
  return 1
}
retry 3 0 -- always_fail
assert_eq "1" "$?" "retry gives up and returns failure after max attempts"
assert_eq "3" "$(cat "$COUNTER_FILE2")" "always_fail was attempted exactly max_attempts times"
rm -f "$COUNTER_FILE2"

# Case 3: verify exponential backoff delay doubling
SLEEP_LOG="$(mktemp)"
# Stub sleep function to capture delay arguments instead of actually sleeping
sleep() {
  echo "$1" >> "$SLEEP_LOG"
}
export -f sleep

COUNTER_FILE3="$(mktemp)"
echo 0 > "$COUNTER_FILE3"
delays_test_command() {
  local n
  n=$(cat "$COUNTER_FILE3")
  n=$(( n + 1 ))
  echo "$n" > "$COUNTER_FILE3"
  [ "$n" -ge 3 ]
}
retry 5 1 -- delays_test_command
assert_eq "0" "$?" "retry with nonzero delay succeeds"
assert_eq "3" "$(cat "$COUNTER_FILE3")" "command was called exactly 3 times"
# Verify sleep was called with 1 and 2 (base_delay=1, then 1*2=2)
sleep_calls="$(cat "$SLEEP_LOG" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
assert_eq "1 2" "$sleep_calls" "exponential backoff delays are 1 then 2"
rm -f "$COUNTER_FILE3" "$SLEEP_LOG"

summary
exit $?
