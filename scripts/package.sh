#!/usr/bin/env bash
# Build the final submission zip from submission/, preserving Unix file
# modes (in particular, loop.sh's executable bit) via scripts/make-zip.js.
# `zip` is not installed on this Windows machine, and PowerShell's
# Compress-Archive cannot represent POSIX permissions at all — it would
# silently ship loop.sh non-executable. `unzip` (present) is used only by
# tests/test_package.sh to verify the result.
set -e
set -u
set -o pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$DIR/round2-submission.zip}"

rm -f "$OUT"
chmod +x "$DIR/submission/loop.sh"

# Wrap every entry in one top-level folder named after the zip itself,
# matching the real starter-kit (1).zip's actual internal structure
# (confirmed via `unzip -l`: everything lives under a single "starter-kit/"
# folder, including an explicit directory entry for it — not flat).
WRAPPER="$(basename "$OUT" .zip)"

# Pass "loop.sh" explicitly as a known-executable relative path: on this
# Windows machine, Node's fs.statSync().mode never reflects the Unix
# permission bits that the chmod +x above just set (Node's Windows stat
# only looks at the read-only attribute, not the MSYS/Git-Bash ACL-based
# permission emulation), so make-zip.js cannot discover the executable bit
# on its own here. bash can see it, so we tell make-zip.js directly.
node "$DIR/scripts/make-zip.js" "$DIR/submission" "$OUT" "$WRAPPER" "loop.sh"
