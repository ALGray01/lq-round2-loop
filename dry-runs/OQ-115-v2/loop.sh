#!/usr/bin/env bash
# Round 2 loop orchestrator — FULL CONTROL lane.
# QUESTION.md is on disk; $BUDGET is the total turn budget for this question.
#
# Turn-budget flow (see the design spec for full rationale — not shipped in
# this package, so summarized here): the loop runs continuation turns in a
# "build" phase until remaining turns drop to RESERVE (~25% of BUDGET, a
# starting estimate meant to be tuned via local dry runs, not locked), then
# switches to a "reserve" phase that stabilizes the repo, dispatches three
# parallel fresh-context auditor subagents against FAILURE-CLASSES.md, and
# fixes what they find — repeating additional audit rounds as long as
# enough turns remain (MIN_ROUND_TURNS) for one full round to safely
# complete. RESERVE was raised from an initial 20% after a real dry run
# (OQ-130) showed the heavier three-persona audit could consume an entire
# tight reserve window and never reach the final Reflection pass.
set -u
set -o pipefail
set -m # job control on: each backgrounded `( ... ) &` below gets its own
       # process group (PGID == its own PID), so on a deadline timeout we
       # can kill -TERM -- -$bg_pid to signal `claude` too, not just the
       # wrapper subshell that forked it.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib/budget.sh"
source "$DIR/lib/retry.sh"

BUDGET="${BUDGET:?BUDGET env var required}"

RESERVE="$(compute_reserve "$BUDGET")"
MIN_ROUND="$(compute_min_round "$BUDGET")"

# Guard against a silently empty brief: better to fail loudly here than to
# spend turns on a session with no question to answer.
[ -s QUESTION.md ] || { echo "loop.sh: QUESTION.md missing or empty — refusing to start" >&2; exit 1; }

render_prompt() {
  # $1 = template file, $2 = remaining. Prints the template with
  # {{BUDGET}}/{{REMAINING}}/{{MIN_ROUND}} substituted.
  local file="$1" remaining="$2"
  sed \
    -e "s/{{BUDGET}}/$BUDGET/g" \
    -e "s/{{REMAINING}}/$remaining/g" \
    -e "s/{{MIN_ROUND}}/$MIN_ROUND/g" \
    "$file"
}

parse_result() {
  # $1 = json output file. Sets globals: turns, subtype, terminal_reason,
  # is_err, cache_read, cache_create, in_tok, out_tok, cost_usd. Never
  # fails — defaults everything to 0/"" if the file is missing or invalid
  # JSON, so callers can always trust these vars are set.
  local file="$1" line
  # FORCE_COLOR=0 pinned explicitly: if the calling shell exports
  # FORCE_COLOR (any nonzero value), Node's console.log wraps numeric
  # output in ANSI color escapes even when stdout is redirected to a file
  # (this is an explicit override honored regardless of TTY detection, and
  # NO_COLOR alone does not undo it once FORCE_COLOR is set) — which would
  # then break the tab-separated parsing below and the arithmetic that
  # follows. Setting FORCE_COLOR=0 on this specific invocation wins over
  # whatever the parent shell has exported.
  line="$(FORCE_COLOR=0 node -e '
    try {
      const o = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
      const u = o.usage || {};
      const fields = [
        Number(o.num_turns) || 0,
        o.subtype || "",
        o.terminal_reason || "",
        o.is_error ? "1" : "0",
        Number(u.cache_read_input_tokens) || 0,
        Number(u.cache_creation_input_tokens) || 0,
        Number(u.input_tokens) || 0,
        Number(u.output_tokens) || 0,
        (typeof o.total_cost_usd === "number") ? o.total_cost_usd : 0,
      ];
      console.log(fields.join("\t"));
    } catch (e) {
      console.log(["0","","","0","0","0","0","0","0"].join("\t"));
    }
  ' "$file" 2>/dev/null)"
  IFS=$'\t' read -r turns subtype terminal_reason is_err cache_read cache_create in_tok out_tok cost_usd <<< "$line"
}

looks_like_budget_refusal() {
  # Best-effort heuristic: the FULL CONTROL contract says the real `claude`
  # command is "metered and model-pinned; it refuses once budget is gone" —
  # but we have no local sample of what that refusal actually looks like, so
  # this greps for plausible wording rather than a confirmed exact match.
  # Deliberately conservative (never seen a real sample) — false negatives
  # here just fall through to the ordinary transient-retry path, which is
  # the safer failure mode.
  local f
  for f in "$@"; do
    [ -f "$f" ] || continue
    if grep -qiE 'budget.*(exceed|exhaust|refus|deplet|gone|out of)|quota.*(exceed|exhaust)|out of budget' "$f"; then
      return 0
    fi
  done
  return 1
}

spent=0
if [ -n "${REMAINING:-}" ] && [ "$REMAINING" != "$BUDGET" ]; then
  # A runner-side restart mid-question may re-launch loop.sh with $REMAINING
  # already below $BUDGET — don't act as if the full budget were untouched.
  spent=$(( BUDGET - REMAINING ))
  [ "$spent" -lt 0 ] && spent=0
fi
loop_num=0
tiny=0 # consecutive-tiny-loop counter — see the check after each loop below

INVOKE_MAX_ATTEMPTS=3
INVOKE_BASE_DELAY=5

while :; do
  remaining=$(( BUDGET - spent ))
  if [ "$remaining" -le 0 ]; then
    echo "loop.sh: budget exhausted ($spent/$BUDGET turns spent over $loop_num loop(s))"
    exit 0
  fi

  phase="$(phase_for "$remaining" "$RESERVE")"
  if [ "$phase" = "build" ]; then
    # Cap this invocation at the distance to the reserve threshold, not the
    # full remaining budget — otherwise a single long build-phase call can
    # run straight past the reserve boundary and exhaust the whole budget
    # before the reserve-phase prompt (and the fresh-context audit it
    # triggers) is ever sent. Capping here forces control back to this
    # loop at (or very near) the reserve line so the phase check above can
    # re-evaluate before any one call can blow through it.
    cap=$(( remaining - RESERVE )); [ "$cap" -lt 1 ] && cap=1
  else
    # Real dry runs (OQ-009, OQ-008) showed cumulative spent landing one turn
    # OVER budget (e.g. 134/133) on the run's final call. Root cause: the real
    # `claude` CLI, when actually cut off by --max-turns=N, reports
    # num_turns=N+1 (see final-fix-report.md) — a reporting quirk, confirmed
    # against the machine's own reference runner, which shows the identical
    # pattern in its own meta.json files. Build-phase calls never trip this
    # because their cap is already at least RESERVE below remaining, so
    # cap+1 <= remaining there always. The reserve phase's cap was the exposed
    # case: capping at the full "remaining" meant a cutoff there could report
    # remaining+1, one turn over BUDGET. Capping one lower here cancels it:
    # a cutoff now reports at most (remaining-1)+1 = remaining. The one
    # unavoidable edge case is remaining==1, where cap floors back up to 1 and
    # a cutoff there still reports 2 — a residual, minimal, and honestly
    # documented limitation rather than a claim of a perfect guarantee.
    #
    # This -1 adjustment only cancels the CUTOFF quirk specifically (a call
    # that hits --max-turns=N and gets reported as N+1) — every one of the
    # cutoffs observed across all real dry runs matches this exactly, with
    # no exceptions. A separate, non-error NATURAL finish (the model just
    # stops on its own — is_error:false, terminal_reason:"completed") has
    # also been observed to overrun its own --max-turns value by more than
    # one turn (a build-phase call in OQ-130 finished naturally at 109
    # against a cap of 106) — a different, apparently non-fixed-size
    # mechanism this adjustment does not specifically target. It has only
    # ever been observed on build-phase calls so far, which already carry a
    # full RESERVE-sized cushion; raising RESERVE_PCT (see lib/budget.sh)
    # was partly motivated by giving this variance more room to be absorbed
    # wherever it occurs, reserve phase included, since no hard bound on its
    # size has been established from the data collected so far.
    cap=$(( remaining - 1 )); [ "$cap" -lt 1 ] && cap=1
  fi

  if [ "$loop_num" -eq 0 ]; then
    prompt="$(render_prompt "$DIR/FIRST_PROMPT.md" "$remaining")
$(cat QUESTION.md)"
    cont_flag=()
  else
    if [ "$phase" = "build" ]; then
      prompt="$(render_prompt "$DIR/CONTINUE_BUILD_PROMPT.md" "$remaining")"
    else
      prompt="$(render_prompt "$DIR/CONTINUE_RESERVE_PROMPT.md" "$remaining")"
    fi
    cont_flag=(-c)
  fi

  attempt=1
  delay="$INVOKE_BASE_DELAY"

  while :; do
    out_file="/tmp/loop_${loop_num}_${attempt}.out"
    err_file="/tmp/loop_${loop_num}_${attempt}.err"
    exit_file="/tmp/loop_${loop_num}_${attempt}.exit"
    rm -f "$exit_file"

    # Detached + sentinel-poll: a foreground await can die on a long silent
    # stream — the same issue the machine's own runner works around.
    (
      claude -p "$prompt" "${cont_flag[@]}" --output-format json \
        --dangerously-skip-permissions \
        --max-turns "$cap" \
        > "$out_file" 2> "$err_file"
      echo $? > "$exit_file"
    ) &

    bg_pid=$!
    deadline=$(( $(date +%s) + 120 * 60 ))
    while [ ! -f "$exit_file" ] && [ "$(date +%s)" -lt "$deadline" ]; do
      sleep 20
    done

    if [ ! -f "$exit_file" ]; then
      echo "loop.sh: loop $loop_num deadline hit — killing and stopping" >&2
      # Signal the whole process group (negative PID), not just the wrapper
      # subshell's own PID — `claude` runs as a forked child of that subshell
      # (it has a second statement, `echo $? > exit_file`, to run afterward,
      # so bash can't exec-replace it), so killing only $bg_pid would leave
      # the actual `claude --dangerously-skip-permissions` process orphaned
      # and still running/committing after loop.sh has returned control.
      kill -TERM -- "-$bg_pid" 2>/dev/null || true
      sleep 2
      kill -KILL -- "-$bg_pid" 2>/dev/null || true
      # Not retried: a hang is not obviously transient, and retrying a
      # 120-minute deadline up to INVOKE_MAX_ATTEMPTS times risks burning
      # hours of real budget on a repeat hang rather than stopping cleanly.
      exit 1
    fi

    exit_code="$(cat "$exit_file")"
    parse_result "$out_file"

    # Empirically (see final-fix-report.md), the real `claude` CLI exits 1
    # with subtype "error_max_turns" when a call is cut off at its own
    # --max-turns cap — but still reports a fully valid, non-zero num_turns
    # in the JSON. The machine's own reference runner (run-baseline.ts,
    # which this detached+sentinel-poll pattern is explicitly copied from)
    # never even looks at exitCode for this decision — it only checks
    # whether a usable turn count came back. We match that: if we got a
    # valid positive turn count, treat this as a normal, accountable
    # invocation regardless of exit code or subtype (covers the max-turns
    # cutoff case, and is robust to future claude CLI wording changes
    # without depending on an exact subtype string match).
    if [ -n "$turns" ] && [ "$turns" -gt 0 ]; then
      if [ "$exit_code" != "0" ]; then
        echo "loop.sh: loop $loop_num invocation exited $exit_code (subtype=${subtype:-none}) but returned a valid turn count ($turns) — treating as a normal cutoff, continuing" >&2
      fi
      break
    fi

    # No usable turn count came back. Distinguish a genuine, terminal
    # refusal (the metered `claude` command is documented to "refuse once
    # budget is gone" upstream — not retryable) from an ordinary transient
    # invocation failure (retryable a few times with backoff).
    if looks_like_budget_refusal "$err_file" "$out_file"; then
      echo "loop.sh: loop $loop_num — claude invocation refused, budget appears genuinely exhausted upstream — stopping (not retrying)" >&2
      cat "$err_file" >&2
      exit 1
    fi

    if [ "$attempt" -ge "$INVOKE_MAX_ATTEMPTS" ]; then
      echo "loop.sh: loop $loop_num gave up after $attempt attempt(s) with no usable turn count (last exit code $exit_code) — stopping" >&2
      cat "$err_file" >&2
      exit 1
    fi

    echo "loop.sh: loop $loop_num attempt $attempt exited $exit_code with no usable turn count — retrying in ${delay}s" >&2
    cat "$err_file" >&2
    sleep "$delay"
    attempt=$(( attempt + 1 ))
    delay=$(( delay * 2 ))
  done

  spent=$(( spent + turns ))
  loop_num=$(( loop_num + 1 ))
  remaining_after=$(( BUDGET - spent ))
  echo "loop.sh: loop $loop_num used $turns turns ($spent/$BUDGET)"
  echo "loop.sh: loop $loop_num usage — cache_read=$cache_read cache_creation=$cache_create input=$in_tok output=$out_tok cost_usd=$cost_usd" >&2

  # Circuit breaker ported from the machine's own reference runner
  # (run-baseline.ts:154): trusting any positive turn count as progress
  # (above) is exactly what that runner does too, but it pairs that
  # permissiveness with this check — otherwise a persistent tiny-turn
  # response (e.g. is_error:true with num_turns:1, a real shape per the
  # empirical trace in final-fix-report.md) reads as normal progress
  # forever: spent increments by 1 each time, the retry path never fires
  # (only reachable when turns<=0), and the loop silently churns through
  # the whole remaining budget one turn at a time with no backoff and no
  # give-up. Two consecutive loops of <=2 turns is the same threshold the
  # reference runner uses ("the machine has stopped working").
  #
  # `&& [ "$turns" -lt "$cap" ]` guards against a real interaction with the
  # Fix-1 reserve-boundary cap: a build-phase call right at the boundary can
  # legitimately get `cap` as small as 1, and the real CLI reports
  # `turns == cap` when it's cut off at that self-imposed limit (not because
  # the model gave up — it just ran out of the small allowance *we* gave
  # it). That is not a stuckness signal and must not count toward `tiny`,
  # even though the raw turn count is <=2. `$cap` here is still the same
  # value used for this call's --max-turns above — it isn't recomputed until
  # the top of the next outer-loop iteration. A genuinely stuck session
  # (e.g. persistent 1-turn error responses) still trips the breaker
  # correctly: `cap` in that case is whatever's left of the real budget,
  # normally far larger than the tiny `turns` actually returned, since
  # nothing artificially capped it that low.
  #
  # `&& [ "$remaining_after" -gt "$MIN_ROUND" ]` — a real dry run (OQ-009,
  # see ROUND2-REFERENCE.md §9.3) found this breaker can also false-trip on
  # a session correctly, deliberately declining to start work it might not
  # finish this late: two consecutive genuine (not capped) tiny replies each
  # explicitly explained why starting another round was too risky with so
  # little budget left. That is good judgment, not stuckness, and it only
  # showed up once `remaining` had already dropped below `MIN_ROUND` (the
  # same threshold used elsewhere for "enough turns left to safely complete
  # one more round"). Below that point, stopping early costs almost nothing
  # anyway (there's barely any budget left regardless), so the breaker no
  # longer needs to protect it; above it, a genuinely stuck session can still
  # burn a meaningful chunk of the reserve, so the breaker stays fully armed.
  if [ "$turns" -le 2 ] && [ "$turns" -lt "$cap" ] && [ "$remaining_after" -gt "$MIN_ROUND" ]; then
    tiny=$(( tiny + 1 ))
    if [ "$tiny" -ge 2 ]; then
      echo "loop.sh: two consecutive tiny (<=2 turn) loops — the session has likely stopped making real progress — stopping" >&2
      exit 1
    fi
  else
    tiny=0
  fi
done
