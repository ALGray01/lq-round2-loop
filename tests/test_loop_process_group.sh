#!/usr/bin/env bash
# Verifies the process-group-kill fix in submission/loop.sh's deadline path:
# `set -m` + `kill -TERM -- -$bg_pid` must kill everything forked inside the
# backgrounded `( ... ) &` job, not just the wrapper subshell's own PID.
#
# This mirrors loop.sh's exact structure —
#   ( claude ...; echo $? > exit_file ) &
#   bg_pid=$!
#   ... kill "$bg_pid" on deadline ...
# — where `claude` runs as a forked child of the subshell (the subshell has
# a second statement to run afterward, so bash can't exec-replace it into
# `claude` directly). Killing only $bg_pid signals the subshell wrapper but
# leaves `claude` itself orphaned and running. We can't practically wait out
# loop.sh's real 120-minute deadline in a test, so instead we exercise the
# identical set -m / negative-PID-kill mechanism directly: background a
# subshell that forks a lingering "grandchild" (standing in for `claude`),
# then kill the group early and assert the grandchild died too.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/harness.sh"

STATE_DIR="$(mktemp -d)"
GRANDCHILD_PID_FILE="$STATE_DIR/grandchild.pid"

set -m
(
  # Stand-in for `claude`: a long-lived process forked inside the wrapper
  # subshell, exactly as `claude` is forked inside loop.sh's `( ... ) &`.
  sleep 100 &
  echo $! > "$GRANDCHILD_PID_FILE"
  wait
) &
bg_pid=$!
set +m

# Give the subshell a moment to fork its grandchild and record the pid —
# mirrors loop.sh's own poll-then-decide structure, just on a much shorter
# horizon than the real 120-minute deadline.
deadline=$(( $(date +%s) + 10 ))
while [ ! -s "$GRANDCHILD_PID_FILE" ] && [ "$(date +%s)" -lt "$deadline" ]; do
  sleep 1
done

grandchild_pid="$(cat "$GRANDCHILD_PID_FILE" 2>/dev/null || echo "")"
pid_captured="0"
[ -n "$grandchild_pid" ] && pid_captured="1"
assert_eq "1" "$pid_captured" "grandchild pid was captured before the kill (setup sanity check)"

grandchild_alive_before="0"
if [ -n "$grandchild_pid" ] && kill -0 "$grandchild_pid" 2>/dev/null; then
  grandchild_alive_before="1"
fi
assert_eq "1" "$grandchild_alive_before" "grandchild process is confirmed running before the kill"

# The fix under test, verbatim from loop.sh's deadline-timeout path.
kill -TERM -- "-$bg_pid" 2>/dev/null || true
sleep 2
kill -KILL -- "-$bg_pid" 2>/dev/null || true
sleep 1

grandchild_alive_after="0"
if [ -n "$grandchild_pid" ] && kill -0 "$grandchild_pid" 2>/dev/null; then
  grandchild_alive_after="1"
fi
assert_eq "0" "$grandchild_alive_after" "killing -TERM/-KILL the negative (group) PID also kills the grandchild — not just the wrapper subshell"

# Belt-and-suspenders cleanup in case the assertion above ever fails.
[ -n "$grandchild_pid" ] && kill -KILL "$grandchild_pid" 2>/dev/null
kill -KILL -- "-$bg_pid" 2>/dev/null
rm -rf "$STATE_DIR"

summary
exit $?
