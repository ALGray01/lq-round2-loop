#!/usr/bin/env bash
# Runs every tests/test_*.sh file in this directory and prints a summary.
# Self-maintaining: a new test_*.sh file is picked up automatically without
# needing to be added to any documented run command by hand.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

total=0
failed=0
failed_names=()

for f in "$DIR"/test_*.sh; do
  [ -e "$f" ] || continue
  name="$(basename "$f")"
  total=$(( total + 1 ))
  echo "=== $name ==="
  if bash "$f"; then
    echo "--- $name: PASS ---"
  else
    echo "--- $name: FAIL ---"
    failed=$(( failed + 1 ))
    failed_names+=("$name")
  fi
  echo
done

echo "============================================"
echo "run_all.sh: $((total - failed))/$total test files passed"
if [ "$failed" -gt 0 ]; then
  echo "run_all.sh: FAILED files: ${failed_names[*]}"
  exit 1
fi
exit 0
