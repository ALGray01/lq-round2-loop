#!/usr/bin/env bash
# Generic retry-with-backoff wrapper.
# Usage: retry <max_attempts> <base_delay_seconds> -- cmd [args...]
# Returns the command's success (0) once it succeeds, or 1 once attempts
# are exhausted. Delay doubles after each failed attempt.

retry() {
  local max_attempts="$1" base_delay="$2"
  shift 2
  if [ "${1:-}" = "--" ]; then shift; fi

  local attempt=1
  local delay="$base_delay"
  while true; do
    if "$@"; then
      return 0
    fi
    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "retry: giving up after $attempt attempts: $*" >&2
      return 1
    fi
    echo "retry: attempt $attempt failed, retrying in ${delay}s: $*" >&2
    sleep "$delay"
    attempt=$(( attempt + 1 ))
    delay=$(( delay * 2 ))
  done
}
