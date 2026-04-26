#!/usr/bin/env bash
# Run unit tests using the main repo's .venv.
# Works from any git worktree: git rev-parse --git-common-dir always returns
# the main .git directory, so ../  is the main repo root where .venv lives.
set -e
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
exec "$REPO_ROOT/.venv/bin/pytest" tests/unit/ -x -q
