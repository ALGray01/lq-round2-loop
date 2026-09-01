#!/usr/bin/env bash
# Hand-rolled test harness — no bats installed. Source this, then call
# assert_eq/assert_contains/assert_not_contains, then summary at the end.
set -u
PASS=0
FAIL=0

assert_eq() {
  local expected="$1" actual="$2" msg="${3:-}"
  if [ "$expected" = "$actual" ]; then
    PASS=$(( PASS + 1 ))
  else
    FAIL=$(( FAIL + 1 ))
    echo "FAIL: $msg — expected [$expected], got [$actual]"
  fi
}

assert_contains() {
  local haystack="$1" needle="$2" msg="${3:-}"
  if printf '%s' "$haystack" | grep -qF -- "$needle"; then
    PASS=$(( PASS + 1 ))
  else
    FAIL=$(( FAIL + 1 ))
    echo "FAIL: $msg — expected to find [$needle]"
  fi
}

assert_not_contains() {
  local haystack="$1" needle="$2" msg="${3:-}"
  if printf '%s' "$haystack" | grep -qF -- "$needle"; then
    FAIL=$(( FAIL + 1 ))
    echo "FAIL: $msg — did not expect to find [$needle]"
  else
    PASS=$(( PASS + 1 ))
  fi
}

summary() {
  echo "$PASS passed, $FAIL failed"
  [ "$FAIL" -eq 0 ]
}
