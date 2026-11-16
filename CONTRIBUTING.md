# Contributing

Thanks for your interest. This project handles medical image files, so a few rules matter more than usual.

## The rules that matter

1. **Never use or attach real patient data.** Not in code, tests, issues, pull requests or screenshots. Tests
   generate synthetic data at run time (`tests/synthetic.py`). A pre-commit hook and a CI check block medical image
   files from the repository.
2. **Output is the security boundary.** Whatever a tool returns goes into a language model's context. Read
   [docs/threat-model.md](docs/threat-model.md) before changing or adding a tool. New output fields must be numbers,
   allowlisted codes or standardised names, never free text from a file.
3. **A rule without a test is not a rule.** Every change to what a tool returns needs a test that fails if the
   rule is broken. Try it: temporarily break the rule and check that a test goes red.
4. **Say what is approximate.** Results that are not validated against a reference must say so in the tool output
   and the docs.

## Development setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/MLwithDyy/rt-imaging-mcp
cd rt-imaging-mcp
uv sync
uv tool install pre-commit   # or: pip install pre-commit
pre-commit install
```

Checks that CI also runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

## Making a change

1. Open an issue first for anything larger than a small fix.
2. Create a branch (`feat/...`, `fix/...`, `docs/...`) and keep the change focused.
3. Add or update tests, and update `README.md`, `CHANGELOG.md` and the threat model when behaviour changes.
4. Open a pull request. CI must be green on Linux and Windows for Python 3.11, 3.12 and 3.13.

Commit messages follow the conventional style (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`).

## Adding a tool

- Put the implementation in `src/rt_imaging_mcp/tools/`, take a `Config`, return JSON-safe data.
- Resolve every path with `security.paths.resolve_in_root` and return paths only through `to_relative`.
- Return DICOM attributes only through the allowlist, names only through `security/roi_names.py`, and code strings
  only through an allowlist (`tools/rt_common.code`).
- Raise the static errors from `security/errors.py`. Never build an error message from file content.
- Register it in `server.py` with the read-only annotations and add it to the expected tool lists in
  `tests/test_server.py` and `tests/test_stdio_integration.py`.
- Add security tests (identifiers absent, paths, limits, static errors) next to the functional tests, and a row in
  the threat model's test mapping.

## Licence

By contributing you agree that your contribution is licensed under the Apache License 2.0.
