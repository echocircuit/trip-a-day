# Starting a New Project from `python-template`

A linear checklist from "I have an idea" to "first PR merged into main."

---

## Phase 1: Create the repo on GitHub

1. Go to your `python-template` repo on GitHub
2. Click **Use this template** → **Create a new repository**
3. Name it (e.g., `radar-sonification`), set visibility, click **Create repository**
4. Leave the GitHub tab open — you'll come back to it

---

## Phase 2: Clone and set up locally

In your terminal:

```bash
# Clone (use SSH since you set up your key)
git clone git@github.com:YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO

# Create and activate virtual environment (requires uv: brew install uv)
uv venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install in editable mode with dev dependencies
uv pip install -e ".[dev]"

# Install pre-commit hooks (both commit-time and push-time)
pre-commit install
pre-commit install --hook-type pre-push

# Sanity check — these should all pass
pytest tests/unit/
ruff check .
mypy src/
```

---

## Phase 3: Open in VS Code and let Claude Code initialize the project

```bash
code .
```

In the VS Code terminal, start Claude Code and give it this prompt (fill in the bracketed parts):

> Read CLAUDE.md and CONTRIBUTING.md to understand the project conventions. This project is **[one sentence description of what it does]**. The package should be named **[your_package_name]**. Please:
> 1. Rename `myproject` to `[your_package_name]` in all files, directories, and configs
> 2. Update the TODO placeholders in CLAUDE.md, README.md, and pyproject.toml
> 3. Add the core dependencies I'll need to pyproject.toml: **[numpy, scipy, etc.]**
> 4. Create the initial module structure under `src/[your_package_name]/` with skeleton files for: **[list your planned modules]**
> 5. Update the unit test to import from the new package name
> 6. Run `pytest`, `ruff check .`, and `mypy src/` to confirm everything passes

After Claude Code finishes, verify the rename worked:

```bash
grep -r "myproject" . --exclude-dir=.venv --exclude-dir=.git
```

Should return nothing.

Then reinstall so the renamed package is picked up:

```bash
uv pip install -e ".[dev]"
pytest tests/unit/
```

---

## Phase 4: First commit and push to `main`

> **Note:** This first push goes directly to `main` because branch protection isn't on yet. We need CI to run once before we can configure protection — chicken-and-egg.

```bash
git add .
git commit -m "feat: initial project scaffolding"
git push -u origin main
```

If you get the **GH007 email privacy error**, your global git config still has a real email somewhere. Fix it:

```bash
# Get your noreply address from https://github.com/settings/emails
git config --global user.email "ID+USERNAME@users.noreply.github.com"
git commit --amend --reset-author --no-edit
git push -u origin main
```

---

## Phase 5: Trigger CI so GitHub learns the check names

Branch protection requires picking which checks must pass — but the dropdown is empty until GitHub has seen them run. Force a quick PR:

```bash
git checkout -b chore/trigger-ci
echo "" >> README.md  # trivial change
git add README.md
git commit -m "chore: trigger initial CI run"
git push -u origin chore/trigger-ci
```

On GitHub:
1. Click the **Compare & pull request** banner that appears
2. Open the PR against `main`
3. Wait for the `lint` and `unit-tests` checks to run (1-2 minutes)
4. Once green, **squash and merge** the PR
5. Delete the branch when prompted

Back in your terminal:

```bash
git checkout main
git pull
git branch -d chore/trigger-ci
```

---

## Phase 6: Configure branch protection

On GitHub:

1. Go to **Settings → Branches** (or **Rules → Rulesets**)
2. Click **Add branch ruleset** (or **Add classic branch protection rule**)
3. Target branch: `main`
4. Enable:
   - **Require a pull request before merging**
   - **Require status checks to pass before merging**
     - Search the dropdown and add: `lint`, `unit-tests` (they'll appear now that CI has run)
   - **Require branches to be up to date before merging**
5. Save

From this point on, you cannot push directly to `main` — every change must go through a PR.

---

## Phase 7: Confirm the workflow works end-to-end

Make a real first feature branch to confirm the full loop:

```bash
git checkout -b feature/first-real-feature
# ... work with Claude Code, write code and tests ...
git add .
git commit -m "feat: add first real capability"
git push -u origin feature/first-real-feature
```

On GitHub: open PR → wait for green checks → squash and merge.

```bash
git checkout main
git pull
git branch -d feature/first-real-feature
```

Done. From here on, every change follows Phase 7.

---

## Quick reference: the steady-state loop

```bash
git checkout main && git pull
git checkout -b feature/short-description
# ... work, commit, push ...
git push -u origin feature/short-description
# ... open PR on GitHub, wait for CI, squash-merge ...
git checkout main && git pull
git branch -d feature/short-description
```
