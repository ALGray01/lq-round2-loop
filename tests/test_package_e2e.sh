#!/usr/bin/env bash
# End-to-end packaging test: builds the real zip via scripts/package.sh,
# extracts it into a fresh temp directory (no reference back to
# submission/ at all from this point on), drops in a QUESTION.md and the
# fake_claude.sh stub, and runs the *extracted* loop.sh against a scripted
# turn sequence — the same technique tests/test_loop_integration.sh uses
# against the unpackaged submission/ directly. This is the one test that
# would catch a stray/missing file in the packaging step, or a permission
# (e.g. loop.sh's executable bit) that didn't survive the zip round-trip.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"

ZIP="$(mktemp -u).zip"
"$DIR/../scripts/package.sh" "$ZIP"
pkg_status=$?
assert_eq "0" "$pkg_status" "package.sh exits 0"

EXTRACT_DIR="$(mktemp -d)"
unzip -q "$ZIP" -d "$EXTRACT_DIR"
unzip_status=$?
assert_eq "0" "$unzip_status" "the packaged zip extracts cleanly"

# The zip wraps everything in one top-level folder, matching the real
# starter-kit (1).zip's actual internal structure (confirmed via
# `unzip -l`) — find that folder rather than assuming a flat layout.
WRAPPED_DIRS="$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 -type d)"
wrapped_count="$(printf '%s\n' "$WRAPPED_DIRS" | grep -c .)"
assert_eq "1" "$wrapped_count" "extraction produces exactly one top-level wrapper folder"

RUN_DIR="$WRAPPED_DIRS"
expected_wrapper_name="$(basename "$ZIP" .zip)"
actual_wrapper_name="$(basename "$RUN_DIR")"
assert_eq "$expected_wrapper_name" "$actual_wrapper_name" "wrapper folder name matches the zip's own basename, mirroring starter-kit.zip -> starter-kit/"

# loop.sh must retain its executable bit through the zip round-trip.
loop_is_exec="0"
[ -x "$RUN_DIR/loop.sh" ] && loop_is_exec="1"
assert_eq "1" "$loop_is_exec" "extracted loop.sh kept its executable bit through the zip round-trip"

STATE_DIR="$(mktemp -d)"
mkdir -p "$RUN_DIR/bin"
cp "$DIR/fake_claude.sh" "$RUN_DIR/bin/claude"
chmod +x "$RUN_DIR/bin/claude" "$RUN_DIR/loop.sh"

echo "TESTQUESTIONMARKER123 — a fake brief for e2e packaging testing." > "$RUN_DIR/QUESTION.md"

(
  cd "$RUN_DIR"
  export PATH="$RUN_DIR/bin:$PATH"
  export BUDGET=133
  export FAKE_CLAUDE_STATE_DIR="$STATE_DIR"
  export FAKE_CLAUDE_TURNS_SEQUENCE="50,50,20,10,3"
  bash loop.sh
)
loop_exit=$?
assert_eq "0" "$loop_exit" "the extracted, packaged loop.sh exits cleanly once budget is exhausted"

calls="$(cat "$STATE_DIR/count")"
assert_eq "5" "$calls" "the extracted loop.sh invoked fake_claude exactly 5 times for this sequence, matching the unpackaged integration test"

log="$STATE_DIR/calls.log"
call1="$(awk '/=== call 1 ===/{f=1;next}/=== call 2 ===/{f=0}f' "$log")"
call4="$(awk '/=== call 4 ===/{f=1;next}/=== call 5 ===/{f=0}f' "$log")"

assert_contains "$call1" "TESTQUESTIONMARKER123" "call 1 (first prompt) includes the question brief, from the packaged loop.sh"
assert_contains "$call4" "FAILURE-CLASSES.md" "call 4 (remaining=13, at/below reserve=34) uses the reserve-phase prompt, from the packaged loop.sh"

rm -f "$ZIP"
rm -rf "$EXTRACT_DIR" "$STATE_DIR"
summary
exit $?
