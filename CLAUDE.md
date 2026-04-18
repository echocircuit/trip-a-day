# CLAUDE.md — Project context for Claude Code

## Project overview
TODO: One-paragraph description of what this project does and why.

## Architecture
- Source code lives in `src/myproject/`
- Uses `pyproject.toml` for all configuration (no setup.py, no separate tool configs)
- Installed in editable mode: `pip install -e ".[dev]"`

## Commands
- Run unit tests: `pytest tests/unit/`
- Run integration tests: `pytest tests/integration/ -m integration`
- Run all tests with coverage: `pytest --cov=src/myproject`
- Lint: `ruff check .`
- Format: `ruff format .`
- Type check: `mypy src/`
- Run demo scripts: `python scripts/demo_*.py`

## Conventions
- All new code should have type hints
- Every public function needs a unit test
- Use ruff for formatting (88 char line length, matches black)
- Imports sorted by ruff (isort rules)
- Commit messages use conventional prefixes: feat, fix, test, refactor, docs, ci, chore
- Work on feature branches, merge to main via PR
- Unit tests must stay fast (no I/O, no network)
- Integration tests are marked with `@pytest.mark.integration`

## Key dependencies
TODO: List important libraries and what they're used for.

## Known issues / tech debt
TODO: Track things that need attention.
