#!/usr/bin/env bash
# Validate commit messages: Conventional Commits + no Co-Authored-By / AI attribution (D47).
# Usage:  check-commit-msg.sh <message-file>         (git commit-msg hook)
#         check-commit-msg.sh --range <base>..<head>  (CI)
set -euo pipefail

PATTERN='^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?!?: .{1,100}$'
fail=0

check() {  # $1 = label, $2 = full message
  local subject
  subject="$(printf '%s\n' "$2" | head -n1)"
  case "$subject" in Merge\ *) return 0 ;; esac
  if ! printf '%s' "$subject" | grep -Eq "$PATTERN"; then
    echo "✗ $1: subject is not a Conventional Commit: \"$subject\""
    fail=1
  fi
  if printf '%s\n' "$2" | grep -Eiq '^co-authored-by:|generated with \[?claude|🤖 generated'; then
    echo "✗ $1: contains Co-Authored-By / AI attribution (not allowed, see AGENTS.md)"
    fail=1
  fi
}

if [[ "${1:-}" == "--range" ]]; then
  for sha in $(git rev-list --no-merges "$2"); do
    check "${sha:0:7}" "$(git log -1 --format=%B "$sha")"
  done
else
  check "commit message" "$(grep -v '^#' "$1")"
fi

if [[ $fail -eq 0 ]]; then echo "✓ commit messages OK"; fi
exit $fail
