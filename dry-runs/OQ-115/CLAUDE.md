# Standing discipline for this session

Read once at the start; applies for the whole session.

**Commit continuously.** `git init` if there is no repository yet, and commit
after every coherent increment — not just at the end. Whatever is on disk (or
committed, if you've been committing) at the moment you are cut off is what
gets graded, with no warning beforehand. Never let the working tree sit in a
half-refactored, non-building state for long. Before your first commit, check
`git config user.name`/`user.email`; if either is unset, set a generic,
non-identifying local identity (e.g. `git config user.name "Round 2 Loop"` and
`git config user.email "round2-loop@localhost"`) — this repository's history
is published, so it should never end up carrying a personal identity you
didn't deliberately choose to attach to it.

**Verify by execution, not by re-reading.** Before stating that something
works, run it and look at the real output. Before claiming a comparison (X
beats Y, this is faster/safer/more accurate than that), make sure there's an
actual baseline being actually run, not an assumed or invented one.

**If you write anything that decides pass/fail or produces a score** (a test,
an eval harness, a verifier), treat it with the same suspicion as the code
it's grading. A scorer that's wrong in its own favor is invisible unless you
specifically go looking for it — see `FAILURE-CLASSES.md`, item 4.

**Network/install reliability:** wrap any package install or download in the
`retry` helper from `lib/retry.sh` (`source lib/retry.sh` then
`retry <max_attempts> <base_delay_seconds> -- <command...>`). On repeated
failure, degrade gracefully — skip the optional dependency and note the
limitation honestly in README.md — rather than stalling.

**Near the end of your budget**, you will be instructed to dispatch a fresh
subagent (via your Task tool) to audit this repository adversarially,
checking `FAILURE-CLASSES.md` explicitly. Give it real access to read the
repo; treat its findings as seriously as you would a human reviewer's.
