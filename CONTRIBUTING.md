# Contributing / Development Workflow

This is a solo project, but I follow a branch-based workflow with CI enforcement
to build good habits and keep main stable.

## Workflow

1. Create a feature branch: `git checkout -b feature/short-description`
2. Make changes, commit often with clear messages
3. Push the branch: `git push -u origin feature/short-description`
4. Open a PR against `main` on GitHub
5. Wait for CI checks to pass (lint, unit tests, integration tests)
6. Squash-merge the PR on GitHub
7. Pull main locally: `git checkout main && git pull`
8. Delete the old branch: `git branch -d feature/short-description`

## Commit message style

Use conventional-ish prefixes for scanability:

- `feat: add new capability`
- `fix: correct off-by-one in processing`
- `test: add unit tests for parser`
- `refactor: extract helper function`
- `docs: update README with usage example`
- `ci: update workflow to cache pip`
- `chore: bump dependencies`

## Testing philosophy

- **Unit tests** (`tests/unit/`): fast, isolated, no I/O. Run on every commit via CI.
- **Integration tests** (`tests/integration/`): can hit files, databases, APIs. Run on PRs to main.
- **Demo scripts** (`scripts/demo_*.py`): runnable examples showing the project works end-to-end. Run on PRs.

## Tools

- **ruff**: linting and formatting (replaces black + isort + flake8)
- **mypy**: type checking (permissive to start, tighten over time)
- **pytest**: testing with coverage
- **pre-commit**: runs ruff on every commit, unit tests on push
- **uv**: fast virtual environment and package management (replaces venv + pip)
