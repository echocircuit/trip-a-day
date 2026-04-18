# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`trip-a-day` determines the cheapest trip that can be booked each day. The PyPI distribution name is `trip-a-day`; the importable package is `trip_a_day` (PEP 8 — no hyphens in module names).

## Commands

```bash
pytest tests/unit/                           # fast unit tests (no I/O allowed)
pytest tests/integration/ -m integration     # slower, can hit files/DBs/APIs
pytest tests/unit/test_foo.py::test_bar      # single test
pytest --cov=src/trip_a_day                  # full suite with coverage (fail_under=70)
ruff check .                                 # lint
ruff format .                                # format (88 char, replaces black+isort)
mypy src/                                    # type check (permissive; check_untyped_defs on)
python scripts/demo_<name>.py                # runnable end-to-end demos
```

Install/reinstall after dependency or package-name changes: `uv pip install -e ".[dev]"`.

## Architecture

- **src layout** under [src/trip_a_day/](src/trip_a_day/) — tests import the installed package, not a relative path, so editable install is required for tests to find the code.
- **Single config file**: [pyproject.toml](pyproject.toml) holds build config, dependencies, ruff, pytest, coverage, and mypy settings. Do not add `setup.py`, `setup.cfg`, `.flake8`, `mypy.ini`, or `pytest.ini` — everything goes in `pyproject.toml`.
- **Test split is enforced by location, not just marker**:
  - [tests/unit/](tests/unit/) — must stay fast, no I/O, no network. Run on every commit via pre-commit pre-push hook and on every push via CI.
  - [tests/integration/](tests/integration/) — marked `@pytest.mark.integration`, can touch filesystem/DB/APIs. Run only on PRs to `main`.
  - `pytest tests/integration/` without `-m integration` will still collect them, but the CI workflow uses the marker to be explicit.

## CI and branch protection

- [.github/workflows/ci.yml](.github/workflows/ci.yml) runs `lint` (ruff check + ruff format --check + mypy) and `unit-tests` (Python 3.11 and 3.12 matrix with coverage) on pushes to `main`/`develop` and PRs to `main`. These are the required status checks for branch protection.
- [.github/workflows/integration.yml](.github/workflows/integration.yml) runs integration tests and every `scripts/demo_*.py` on PRs to `main` only.
- `main` is branch-protected — all changes go through a feature branch + PR + squash-merge. See [CONTRIBUTING.md](CONTRIBUTING.md) for the loop.

## Pre-commit hooks

[.pre-commit-config.yaml](.pre-commit-config.yaml) installs two stages. Run `pre-commit install && pre-commit install --hook-type pre-push` once after cloning.

- **pre-commit**: ruff (with `--fix`), ruff-format, trailing whitespace, EOF fixer, YAML check, large-file guard (500KB), merge-conflict check.
- **pre-push**: `pytest tests/unit/ -x -q` — pushes are blocked if any unit test fails.

If a hook fails, fix the cause and re-stage; do not bypass with `--no-verify` unless explicitly asked.

## Conventions

- Type hints required on new code; mypy is permissive (`disallow_untyped_defs = false`) but tightening is expected over time.
- Commit prefixes: `feat`, `fix`, `test`, `refactor`, `docs`, `ci`, `chore`.
- First-party import group is `trip_a_day` (see `[tool.ruff.lint.isort]`).
