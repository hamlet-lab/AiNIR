# PyPI publishing for AiNIR

AiNIR's public Python distribution is named **`ainir`**. The Python package and installed console command are also **`ainir`**.

This document describes the bounded RC publishing path. It does not change AiNIR's pre-v1 / non-production claim boundary.

## Expected install experience after publication

```bash
python -m pip install --pre ainir
ainir demo
```

The `--pre` flag makes the RC intent explicit. The current package version is sourced from `src/ainir/_version.py`.

Until the first PyPI publication succeeds, the public README intentionally keeps the verified GitHub-source install path instead of advertising a package that is not yet available.

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
- checks that wheel metadata says `ainir` and matches the source release version;
- installs the wheel into a fresh virtual environment;
- changes outside the source checkout;
- runs both `python -m ainir demo` and the installed `ainir demo` console command;
- uploads the verified wheel/sdist as a GitHub Actions artifact for the publishing job.

## Authentication: PyPI Trusted Publishing

The workflow uses GitHub OIDC Trusted Publishing. It does **not** require a long-lived PyPI API token in GitHub Secrets.

The production PyPI pending Trusted Publisher is configured for:

- PyPI project: `ainir`
- GitHub owner: `hamlet-lab`
- Repository: `AiNIR`
- Workflow filename: `publish-pypi.yml`
- Environment: `pypi`

A pending Trusted Publisher allows the first successful trusted upload to create the project. It does not reserve the project name before that upload.

TestPyPI is a separate service. If the optional `testpypi` path is used, configure the equivalent publisher on TestPyPI with environment `testpypi`; production PyPI configuration does not automatically configure TestPyPI.

## GitHub environments

The production job declares the GitHub environment `pypi`. If the repository does not already have that environment, GitHub can create an unprotected environment when the job first references it; for a deliberate release process, configure the environment explicitly before production publishing.

Recommended for `pypi`:

- require manual approval from the repository owner/maintainer where the account plan/settings permit it;
- prevent unreviewed branches from deploying where practical;
- keep no PyPI API token secret because OIDC is used instead.

If TestPyPI is used, apply the same pattern to a `testpypi` environment.

## First publication sequence

1. Merge the distribution-name change only after normal repository CI is green.
2. Run `publish-pypi` with target `build-only` and confirm the build/verification job succeeds.
3. Optionally configure TestPyPI Trusted Publishing and run the `testpypi` target.
4. Confirm the production PyPI pending publisher still matches `hamlet-lab/AiNIR`, `publish-pypi.yml`, and environment `pypi`.
5. Run `publish-pypi` with target `pypi`.
6. Verify that the new PyPI project is `ainir` and that version `1.0.0rc2` is present.
7. Verify the public install path in a clean environment:

```bash
python -m venv /tmp/ainir-pypi-check
/tmp/ainir-pypi-check/bin/python -m pip install --upgrade pip
/tmp/ainir-pypi-check/bin/python -m pip install --pre ainir
cd /tmp
/tmp/ainir-pypi-check/bin/ainir demo
```

On Windows, use the corresponding virtual-environment executables under `Scripts\\`.

Only after that verification should README/START_HERE switch their fastest-install path from the GitHub source URL to PyPI.

## Release identity rules

Do not publish a new artifact by overwriting an existing PyPI version. PyPI releases are immutable in normal operation.

For a new RC or final release:

1. change the version/release identity in `src/ainir/_version.py` deliberately;
2. run the normal AiNIR CI and distribution checks;
3. review README/scope wording for the new release state;
4. use `build-only` before selecting a publishing target.

## Package identity

The public names are intentionally aligned for the first PyPI publication:

- PyPI distribution: `ainir`
- Python package: `ainir`
- console command: `ainir`

This keeps the eventual install experience simple: `python -m pip install --pre ainir`, followed by `ainir demo`.
