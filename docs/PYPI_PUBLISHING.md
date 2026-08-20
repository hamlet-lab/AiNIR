# PyPI publishing for AiNIR

AiNIR's public Python distribution is currently named **`ainir-public-demo`**. The installed command remains **`ainir`**.

This document describes the bounded RC publishing path. It does not change AiNIR's pre-v1 / non-production claim boundary.

## Expected install experience after publication

```bash
python -m pip install --pre ainir-public-demo
ainir demo
```

The `--pre` flag makes the RC intent explicit. The current package version is sourced from `src/ainir/_version.py`.

## Release workflow

`.github/workflows/publish-pypi.yml` is intentionally **manual-only**.

When started from GitHub Actions it offers three targets:

1. `build-only` — build and verify distributions; publish nothing.
2. `testpypi` — publish the already-verified distributions to TestPyPI.
3. `pypi` — publish the already-verified distributions to PyPI.

The workflow does not trigger on `push`, tags, or GitHub Releases. A normal repository update therefore cannot publish a package by itself.

Before any publishing job can run, the build job:

- runs the existing distribution contract suite;
- builds exactly one wheel and one sdist;
- checks that wheel metadata says `ainir-public-demo` and matches the source release version;
- installs the wheel into a fresh virtual environment;
- changes outside the source checkout;
- runs both `python -m ainir demo` and the installed `ainir demo` console command;
- uploads the verified wheel/sdist as an immutable GitHub Actions artifact for the publishing job.

## Authentication: PyPI Trusted Publishing

The workflow uses GitHub OIDC Trusted Publishing. It does **not** require a long-lived PyPI API token in GitHub Secrets.

For the production PyPI project, configure a Trusted Publisher with:

- PyPI project: `ainir-public-demo`
- GitHub owner: `hamlet-lab`
- Repository: `ainir`
- Workflow filename: `publish-pypi.yml`
- Environment: `pypi`

For TestPyPI, configure the equivalent publisher there with environment `testpypi`.

If the PyPI project does not exist yet, PyPI supports a pending Trusted Publisher. The pending publisher does not reserve the project name until the first successful upload, so confirm availability again immediately before the first publish.

## GitHub environments

Create these repository environments before publishing:

### `pypi`

Recommended:

- require manual approval from the repository owner/maintainer;
- prevent unreviewed branches from deploying where practical;
- keep no PyPI API token secret because OIDC is used instead.

### `testpypi`

Use the same pattern for TestPyPI. Manual approval is still useful even though this is a test index.

## First publication sequence

1. Run `publish-pypi` with target `build-only`.
2. Download/inspect the `python-package-distributions` artifact if desired.
3. Configure the TestPyPI Trusted Publisher and `testpypi` environment.
4. Run the workflow with target `testpypi`.
5. Verify installation from TestPyPI in a clean environment.
6. Configure the production PyPI Trusted Publisher and `pypi` environment.
7. Run the workflow with target `pypi` and approve the `pypi` environment deployment.
8. Verify the public install path:

```bash
python -m venv /tmp/ainir-pypi-check
/tmp/ainir-pypi-check/bin/python -m pip install --upgrade pip
/tmp/ainir-pypi-check/bin/python -m pip install --pre ainir-public-demo
cd /tmp
/tmp/ainir-pypi-check/bin/ainir demo
```

On Windows, use the corresponding virtual-environment executables under `Scripts\\`.

## Release identity rules

Do not publish a new artifact by overwriting an existing PyPI version. PyPI releases are immutable in normal operation.

For a new RC or final release:

1. change the version/release identity in `src/ainir/_version.py` deliberately;
2. run the normal AiNIR CI and distribution checks;
3. review README/scope wording for the new release state;
4. use `build-only` before selecting a publishing target.

## Package-name note

The distribution name and import/CLI names do not need to match:

- distribution: `ainir-public-demo`
- Python package: `ainir`
- console command: `ainir`

A future rename to a shorter PyPI distribution name should be treated as a separate branding/migration decision, not mixed into the first publication workflow.
