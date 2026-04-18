# Project Name

Short description of what this project does.

## Installation

```bash
# Clone the repo
git clone git@github.com:echocircuit/YOUR_REPO.git
cd YOUR_REPO

# Create virtual environment and install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

## Usage

```python
# TODO: Add usage example
```

## Development

### Running tests

```bash
# Unit tests (fast, run often)
pytest tests/unit/

# Integration tests
pytest tests/integration/

# All tests with coverage
pytest --cov=src/myproject
```

### Code quality

```bash
# Linting and formatting (handled automatically by pre-commit)
ruff check .
ruff format .

# Type checking
mypy src/
```

### Project structure

```
├── src/myproject/       # Source code
├── tests/
│   ├── unit/            # Fast, isolated tests — run on every commit
│   └── integration/     # Slower, end-to-end tests — run on PRs
├── scripts/             # Demo and utility scripts
├── .github/workflows/   # CI/CD pipelines
└── pyproject.toml       # Project config (deps, tools, metadata)
```

## License

MIT — see [LICENSE](LICENSE).
