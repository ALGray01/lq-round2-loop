#!/usr/bin/env bash
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"

OUT="$(mktemp -u).zip"
"$DIR/../scripts/package.sh" "$OUT"
status=$?
assert_eq "0" "$status" "package.sh exits 0"

listing="$(unzip -l "$OUT")"
wrapper_name="$(basename "$OUT" .zip)"
assert_contains "$listing" "$wrapper_name/" "zip wraps its contents in a top-level folder matching its own basename (mirrors starter-kit (1).zip's real structure)"
assert_contains "$listing" "$wrapper_name/loop.sh" "loop.sh sits inside the wrapper folder, not at the archive root"
assert_contains "$listing" "loop.sh" "zip contains loop.sh"
assert_contains "$listing" "CLAUDE.md" "zip contains CLAUDE.md"
assert_contains "$listing" "FAILURE-CLASSES.md" "zip contains FAILURE-CLASSES.md"
assert_contains "$listing" "budget.sh" "zip contains lib/budget.sh"
assert_not_contains "$listing" "test_" "zip does not leak dev test files"

loop_perm_line="$(unzip -Z "$OUT" | grep 'loop\.sh$')"
assert_contains "$loop_perm_line" "rwx" "loop.sh keeps its executable bit inside the zip"

rm -f "$OUT"
summary
exit $?
