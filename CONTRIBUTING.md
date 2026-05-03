# Contributing / Development Workflow

This is a solo project, but I follow a branch-based workflow with CI enforcement
to build good habits and keep main stable.

---

## Dev environment setup

```bash
# 1. Clone and enter the repo
git clone git@github.com:YOUR_USERNAME/trip-a-day.git
cd trip-a-day

# 2. Create a virtual environment and install all dependencies
uv venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
pip install -r requirements.txt

# 3. Install pre-commit hooks (ruff on commit, unit tests on push)
pre-commit install
pre-commit install --hook-type pre-push

# 4. Copy the env template — no keys are required to run in mock mode
cp .env.example .env
```

Running `python main.py` immediately after setup works out of the box: `FLIGHT_DATA_MODE=mock` (the default) reads `tests/fixtures/mock_flights.json` and makes no network calls.

---

## Running the test suite

```bash
# Fast unit tests — no API calls, runs in ~1 s
pytest tests/unit/

# All fast tests (unit + smoke + links + charts + …)
pytest

# Integration tests — makes real Google Flights calls (no key required, ~1–2 min)
pytest tests/integration/ -m integration -v

# Single test
pytest tests/unit/test_costs.py::test_foo

# With coverage
pytest --cov=src/trip_a_day
```

The default `pytest` invocation excludes `tests/integration/` automatically (see `addopts` in `pyproject.toml`).

---

## Workflow

1. Create a feature branch: `git checkout -b feature/short-description`
2. Make changes, commit often with clear messages
3. Push the branch: `git push -u origin feature/short-description`
4. Open a PR against `main` on GitHub
5. Wait for CI checks to pass (lint, unit tests, integration tests)
6. Squash-merge the PR on GitHub
7. Pull main locally: `git checkout main && git pull`
8. Delete the old branch: `git branch -d feature/short-description`

### Branch naming convention

| Prefix | When to use |
|---|---|
| `feature/<name>` | New capability or phase |
| `fix/<name>` | Bug fix |
| `docs/<name>` | Documentation-only change |
| `chore/<name>` | Dependency bump, tooling |

---

## PR checklist

Before opening a PR, verify:

- [ ] `ruff check .` — no lint errors
- [ ] `ruff format --check .` — no formatting changes needed
- [ ] `pytest` — all fast tests pass
- [ ] If you added a new module: added to **Key file map** in `CLAUDE.md` and **Project structure** in `README.md`
- [ ] If you added or renamed a preference or env var: updated `CLAUDE.md` Architecture decisions table and `README.md` Default preferences table
- [ ] If you changed a public type (`CostBreakdown`, `TripCandidate`, etc.): updated **Key types** in `CLAUDE.md`
- [ ] `PROGRESS.md` "Next Action" line updated to reflect the current state
- [ ] Docs updated in the same commit as the code they describe (per `CLAUDE.md`)

---

## Commit message style

Use conventional-ish prefixes for scanability:

- `feat: add new capability`
- `fix: correct off-by-one in processing`
- `test: add unit tests for parser`
- `refactor: extract helper function`
- `docs: update README with usage example`
- `ci: update workflow to cache pip`
- `chore: bump dependencies`
- `perf: reduce run time`

---

## Testing philosophy

- **Unit tests** (`tests/unit/`): fast, isolated, no I/O. Run on every commit via pre-commit push hook.
- **Integration tests** (`tests/integration/`): hit real Google Flights (no key required). Run explicitly with `-m integration`.

---

## Tools

- **ruff**: linting and formatting (replaces black + isort + flake8)
- **mypy**: type checking (permissive to start, tighten over time)
- **pytest**: testing with coverage
- **pre-commit**: runs ruff on every commit, unit tests on push
- **uv**: fast virtual environment and package management (replaces venv + pip)
