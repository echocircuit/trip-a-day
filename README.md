# trip-a-day

Determines the cheapest trip that can be booked each day.

## Installation

```bash
# Clone the repo
git clone git@github.com:YOUR_USERNAME/trip-a-day.git
cd trip-a-day

# Create virtual environment and install (requires uv: brew install uv)
uv venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

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
pytest --cov=src/trip_a_day
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
├── src/trip_a_day/      # Source code
├── tests/
│   ├── unit/            # Fast, isolated tests — run on every commit
│   └── integration/     # Slower, end-to-end tests — run on PRs
├── scripts/             # Demo and utility scripts
├── .github/workflows/   # CI/CD pipelines
└── pyproject.toml       # Project config (deps, tools, metadata)
```

## License

MIT — see [LICENSE](LICENSE).

<!-- initial CI trigger -->
