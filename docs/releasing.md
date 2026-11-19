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

TestPyPI and PyPI never accept the same version twice, even after a failed attempt. So rehearse with a pre-release
version and publish the final version only once.

1. Make sure `main` is green in CI and `CHANGELOG.md` is up to date.
2. **Rehearsal version.** Set `__version__` in `src/rt_imaging_mcp/__init__.py` to a pre-release such as `0.1.0rc1`
   and merge it through a pull request.
3. **Rehearse on TestPyPI:** *Actions → Release to TestPyPI → Run workflow* (branch `main`), and approve the
   `testpypi` environment if asked. Then check the result in a clean environment:
   ```bash
   uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ rt-imaging-mcp==0.1.0rc1 --help
   ```
   If something is wrong, fix it and rehearse again with `0.1.0rc2`.
4. **Final version.** Set `__version__` to `0.1.0`, rename `## [Unreleased]` in `CHANGELOG.md` to
   `## [0.1.0] - YYYY-MM-DD` with a fresh empty `[Unreleased]` above it, and merge through a pull request.
5. **Tag and publish:**
   ```bash
   git switch main && git pull
   git tag v0.1.0
   git push origin v0.1.0
   ```
   The `Release` workflow checks that the tag matches the package version, runs the tests, builds the
   distributions, waits for your approval, publishes to PyPI and creates a GitHub Release with the files attached.
6. Check it works from PyPI: `uvx rt-imaging-mcp --help`. Then update the install section of `README.md`.

A published version cannot be replaced. If something is wrong, fix it and release the next version.
