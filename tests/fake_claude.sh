#!/usr/bin/env bash
# Stub replacement for the `claude` CLI. Used only by
# tests/test_loop_integration.sh and friends — never part of the submission.
#
# Env vars (all optional except FAKE_CLAUDE_STATE_DIR / TURNS_SEQUENCE):
#   FAKE_CLAUDE_STATE_DIR        (required) scratch dir for call count/log.
#   FAKE_CLAUDE_TURNS_SEQUENCE   (required) comma list of "desired" turn
#                                counts, one per call, 1-indexed by call
#                                number.
#   FAKE_CLAUDE_ENFORCE_MAX_TURNS=1
#                                opt-in: clamp the reported num_turns to the
#                                actual `--max-turns` value passed on argv
#                                whenever the scripted "desired" turns for
#                                this call exceeds it — mimicking the real
#                                `claude` CLI's observed behavior of exiting
#                                1 with subtype "error_max_turns" when a call
#                                is cut off at its own --max-turns cap.
#                                Off by default so existing tests that don't
#                                care about capping behavior are unaffected.
#   FAKE_CLAUDE_EXIT_SEQUENCE    comma list of exit codes, one per call
#                                (1-indexed). A nonzero entry makes this call
#                                simulate a generic (non-max-turns) invocation
#                                failure: no valid JSON on stdout, an error
#                                message on stderr, exit with that code. A
#                                missing/blank/"0" entry (or running past the
#                                end of the list) falls through to normal
#                                turns-sequence behavior.
set -u
STATE_DIR="${FAKE_CLAUDE_STATE_DIR:?FAKE_CLAUDE_STATE_DIR must be set}"
COUNT_FILE="$STATE_DIR/count"
LOG_FILE="$STATE_DIR/calls.log"
[ -f "$COUNT_FILE" ] || echo 0 > "$COUNT_FILE"

n=$(cat "$COUNT_FILE")
n=$(( n + 1 ))
echo "$n" > "$COUNT_FILE"

{
  echo "=== call $n ==="
  printf '%s\n' "$@"
} >> "$LOG_FILE"

# Pull --max-turns's value off argv, if present, for the enforce-cap path.
max_turns_arg=""
prev=""
for a in "$@"; do
  if [ "$prev" = "--max-turns" ]; then
    max_turns_arg="$a"
  fi
  prev="$a"
done

idx=$(( n - 1 ))

# Optional scripted generic-failure path (Fix 2 retry testing).
if [ -n "${FAKE_CLAUDE_EXIT_SEQUENCE:-}" ]; then
  IFS=',' read -r -a exit_seq <<< "$FAKE_CLAUDE_EXIT_SEQUENCE"
  if [ "$idx" -lt "${#exit_seq[@]}" ]; then
    ec="${exit_seq[$idx]}"
    if [ -n "$ec" ] && [ "$ec" != "0" ]; then
      echo "fake_claude: simulated generic invocation failure (call $n, exit $ec)" >&2
      exit "$ec"
    fi
  fi
fi

IFS=',' read -r -a turns_seq <<< "${FAKE_CLAUDE_TURNS_SEQUENCE:?FAKE_CLAUDE_TURNS_SEQUENCE must be set}"
if [ "$idx" -ge "${#turns_seq[@]}" ]; then
  echo "fake_claude: no more scripted turns for call $n" >&2
  exit 1
fi
turns="${turns_seq[$idx]}"

if [ "${FAKE_CLAUDE_ENFORCE_MAX_TURNS:-}" = "1" ] && [ -n "$max_turns_arg" ] && [ "$turns" -gt "$max_turns_arg" ]; then
  # Simulate hitting the real claude CLI's own --max-turns cutoff.
  printf '{"num_turns": %s, "result": "fake cut off", "subtype": "error_max_turns", "terminal_reason": "max_turns", "is_error": true, "total_cost_usd": 0.01, "usage": {"cache_read_input_tokens": 100, "cache_creation_input_tokens": 10, "input_tokens": 5, "output_tokens": 50}}\n' "$max_turns_arg"
  exit 1
fi

printf '{"num_turns": %s, "result": "fake ok", "subtype": "success", "terminal_reason": "completed", "is_error": false, "total_cost_usd": 0.01, "usage": {"cache_read_input_tokens": 100, "cache_creation_input_tokens": 10, "input_tokens": 5, "output_tokens": 50}}\n' "$turns"
exit 0
