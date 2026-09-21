# Code Style Guidelines & Rules

- Use Python 3.12 as baseline for any projects, unless `.python-version` file specifies a different version.
- Use ruff for linting and formatting. Do not use black, isort, flake8, etc.
- Use uv for package management. Do not use pip, poetry, etc.
- Use pytest for testing. Do not use unittest, pytest-django, etc.
- Use .env files for environment variables. Do not use os.environ, dotenv, etc.


## General Guidelines For Python Code
- Type Checking: Use type hints and annotations in code.
- All public functions and classes should have docstrings.
- Docstrings should be written in Google style, always featuring argument and return type annotations.
- Write boring code that prioritizes readability over being concise at all costs.
- Write docstrings that explain why something exists and what it does, not how.
- Do not overcomment, do not use block comments, do not use comments as chapter titles for your code base.
- Never use print statements, always scan the repo for a custom logger and use that, default logging module otherwise.
- Keep modules and scripts single-purpose. Never have functions do multiple things at once.
- All functions and public modules should come with a docstring that also describes function arguments and what the function returns.
- Never commit real data. If a csv/xls/xlsx file is added to a repo, always prompt the user to confirm the file contains synthetic data before doing anything else.
- Do not commit commented out code, prompting user to delete the commented out section before commit.
- Choose clear, specific, consistent names for variables. Abbreviations and contractions (if commonly used) are fine if unambiguous.
- Do not name variables after data types (e.g. prefer onboarded_users over onboarded_users_dict).
- Ensure all code committed to the repo is formatted and linted beforehand; use pre-commit hooks if possible.

## Repo Structure Guidelines
- Keep app code in a dedicated directory (most of the time, a `src/` folder or a package named after the project).
- Each repo should have a tests/ directory for unit and integration tests in repo root, mirroring the structure of the code.
- Use the following folder structure for new projects, unless working on a repo that already has a different structure:

```
├── .gitignore
├── .python-version
├── .env
├── .env.example
├── src/
│   ├── __init__.py
│   ├── app.py
│   ├── config.py
│   ├── utils.py
├── tests/
│   ├── __init__.py
│   ├── test_app.py
│   ├── test_config.py
│   └── test_utils.py
├── docs/
├── CONTRIBUTING.md
├── BACKLOG.md
├── README.md
├── pyproject.toml
├── uv.lock
```

## Secrets Management Guidelines
- For local development, use secret values in a gitignored `.env` file.
- If a certain secret is required for local development, it must be added to `.env.example` file (version controlled).

## Version Control Guidelines
- Use git for version control. Do not use svn, mercurial, etc.
- Each repo should have a .gitignore file with a sensible default set of commonly ignored files:

```
.venv/
.env
__pycache__/
*.pyc
.claude/
.worktree/
.DS_Store
.vscode/
.idea/
.cursor/
.pytest_cache/
.ruff_cache/
```