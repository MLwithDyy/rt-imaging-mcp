# Releasing

How to publish a version to PyPI. Releases are built and published by GitHub Actions with
[trusted publishing](https://docs.pypi.org/trusted-publishers/): no PyPI token is stored in the repository.
PyPI's screens change from time to time, so follow the linked PyPI documentation if a menu looks different.

## One-time setup

1. **Check the name.** Open `https://pypi.org/project/rt-imaging-mcp/`. A 404 means the name is free.
2. **Create PyPI and TestPyPI accounts** with two-factor authentication.
3. **Add a pending trusted publisher** on each service (PyPI: *Your account → Publishing*; TestPyPI the same on
   `test.pypi.org`). Use:
   - PyPI project name: `rt-imaging-mcp`
   - Owner: `MLwithDyy`, repository: `rt-imaging-mcp`
   - Workflow name: `release.yml` for PyPI and `release-testpypi.yml` for TestPyPI
   - Environment name: `pypi` for PyPI and `testpypi` for TestPyPI
4. **Create the two environments** in GitHub: *Settings → Environments → New environment*, named `pypi` and
   `testpypi`. For `pypi`, add yourself as a required reviewer so that nothing is published without your approval.

## Every release

1. Make sure `main` is green in CI and `CHANGELOG.md` is up to date.
2. Set the version in `src/rt_imaging_mcp/__init__.py` (for example `0.1.0`), and rename `## [Unreleased]` in
   `CHANGELOG.md` to `## [0.1.0] - YYYY-MM-DD` with a fresh empty `[Unreleased]` above it. Commit through a pull request.
3. **Rehearse on TestPyPI:** *Actions → Release to TestPyPI → Run workflow*. Then check the result in a clean
   environment:
   ```bash
   uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ rt-imaging-mcp --help
   ```
4. **Tag and publish:**
   ```bash
   git switch main && git pull
   git tag v0.1.0
   git push origin v0.1.0
   ```
   The `Release` workflow checks that the tag matches the package version, runs the tests, builds the
   distributions, waits for your approval, publishes to PyPI and creates a GitHub Release with the files attached.
5. Check it works from PyPI: `uvx rt-imaging-mcp --help`. Then update the install section of `README.md`.

A published version cannot be replaced. If something is wrong, fix it and release the next version.
