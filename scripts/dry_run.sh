#!/usr/bin/env bash
# Run submission/loop.sh for real, against one cloned baseline question, at
# real API cost. NOT invoked automatically by any test — this spends real
# money against the real `claude` CLI.
# See docs/superpowers/specs/2026-07-27-round2-loop-design.md,
# "Local testing / validation plan".
#
# Usage: scripts/dry_run.sh <OQ-id> <budget> [--check]
#   --check: validate setup and print the plan without invoking claude at all.
set -u
set -o pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OQ="${1:?usage: dry_run.sh <OQ-id> <budget> [--check]}"
BUDGET="${2:?usage: dry_run.sh <OQ-id> <budget> [--check]}"
CHECK_ONLY="${3:-}"

BASELINES_REPO="$DIR/lq-assess-machine-baselines"
QUESTION_SRC="$BASELINES_REPO/run/$OQ"
if [ ! -d "$QUESTION_SRC" ]; then
  echo "dry_run.sh: no run/$OQ directory in $BASELINES_REPO" >&2
  exit 1
fi

RUNDIR="$(mktemp -d)"
cp -r "$DIR/submission/." "$RUNDIR/"
chmod +x "$RUNDIR/loop.sh"

# Deliberately manual: paste the exact brief for $OQ from ROUND2-REFERENCE.md
# §3 into QUESTION.md before running for real. Not scraped automatically —
# the reference doc is the reviewed, corrected source; a script pulling from
# the raw transcript again could silently drift from it.
cat > "$RUNDIR/QUESTION.md" <<EOF
(paste the exact brief for $OQ from ROUND2-REFERENCE.md §3 here)
EOF

echo "dry_run.sh: prepared $RUNDIR for $OQ, BUDGET=$BUDGET"
echo "dry_run.sh: edit $RUNDIR/QUESTION.md with the real brief before proceeding."

if [ "$CHECK_ONLY" = "--check" ]; then
  echo "dry_run.sh: --check mode, not invoking claude. $RUNDIR is deleted after this check — re-run without --check to actually populate and inspect a run directory."
  rm -rf "$RUNDIR"
  exit 0
fi

(
  cd "$RUNDIR"
  export BUDGET
  # stdbuf -oL -eL: force loop.sh's own stdout/stderr to line-buffer rather
  # than the fully-buffered default bash uses once output isn't a terminal.
  # Confirmed via real dry runs (ROUND2-REFERENCE.md §9.3/§9.5): on long
  # runs (~70min+), a plain `> run.log 2>&1` redirect came back completely
  # empty despite the run clearly succeeding — the buffered output was lost
  # entirely, most likely because it was never flushed before the process
  # ended. Line-buffering writes each `echo` to disk immediately, so even an
  # abrupt end leaves everything logged up to that point. Piping through
  # `tee` (rather than a plain `>` redirect) keeps loop.sh's live output
  # visible in this terminal too, not just written to the file.
  stdbuf -oL -eL bash loop.sh 2>&1 | tee run.log
)
rc=$?
echo "dry_run.sh: run finished (loop.sh exit $rc). Inspect $RUNDIR for the result (run.log has the full log even if this shell's own history doesn't)."
exit $rc
