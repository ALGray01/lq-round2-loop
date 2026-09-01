#!/usr/bin/env bash
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"

# scripts/dry_run.sh sources each question from LegalQuants' public baselines
# repository, which it expects checked out alongside this one. That is an
# optional external dependency, not part of this repo — so if it isn't there,
# skip rather than fail. A missing optional dependency is not a defect, and a
# red result here would tell a reader something untrue about the harness.
BASELINES_REPO="$DIR/../lq-assess-machine-baselines"
if [ ! -d "$BASELINES_REPO/run" ]; then
  echo "SKIP: $BASELINES_REPO not present."
  echo "      To run this test:  git clone https://github.com/LegalQuants/lq-assess-machine-baselines"
  echo "      (from the directory containing this repository)"
  exit 0
fi

out="$("$DIR/../scripts/dry_run.sh" OQ-008 133 --check 2>&1)"
status=$?
assert_eq "0" "$status" "dry_run.sh --check exits 0 for a known question"
assert_contains "$out" "--check mode, not invoking claude" "dry_run.sh --check does not invoke claude"

out2="$("$DIR/../scripts/dry_run.sh" OQ-999-nonexistent 133 --check 2>&1)"
status2=$?
assert_eq "1" "$status2" "dry_run.sh fails fast for an unknown OQ id"

summary
exit $?
