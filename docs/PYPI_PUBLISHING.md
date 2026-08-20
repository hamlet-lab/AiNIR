# PyPI publishing for AiNIR

AiNIR's public Python distribution is named **`ainir`**. The Python package and installed console command are also **`ainir`**.

This document describes the bounded RC publishing path. It does not change AiNIR's pre-v1 / non-production claim boundary.

## Public install experience

The first-run path is now:

```bash
python -m pip install ainir
ainir demo
```

The current release is an RC. If an older or custom resolver refuses the prerelease, use:

```bash
python -m pip install --pre ainir
```

The package version is sourced from `src/ainir/_version.py`.

## Release workflow

`.github/workflows/publish-pypi.yml` is intentionally **manual-only**.

When started from GitHub Actions it offers three targets:

1. `build-only` — build and verify distributions; publish nothing.
2. `testpypi` — publish the already-verified distributions to TestPyPI.
3. `pypi` — publish the already-verified distributions to PyPI.

The workflow does not trigger on `push`, tags, or GitHub Releases. A normal repository update therefore cannot publish a package by itself.

Before any publishing job can run, the build job:

- installs the locked runtime dependency needed by the release checks;
- runs the existing distribution contract suite;
- builds exactly one wheel and one sdist;
- checks that wheel metadata says `ainir` and matches the source release version;
- installs the wheel into a fresh virtual environment;
- changes outside the source checkout;
- runs both `python -m ainir demo` and the installed `ainir demo` console command;
- uploads the verified wheel/sdist as a GitHub Actions artifact for the publishing job.

## Authentication: PyPI Trusted Publishing

The workflow uses GitHub OIDC Trusted Publishing. It does **not** require a long-lived PyPI API token in GitHub Secrets.

The production publisher identity is:

- PyPI project: `ainir`
- GitHub owner: `hamlet-lab`
- Repository: `AiNIR`
- Workflow filename: `publish-pypi.yml`
- Environment: `pypi`

The initial production publication used this trusted-publishing path. Future releases should preserve the same identity unless the release process is deliberately migrated.

TestPyPI is a separate service. If the optional `testpypi` path is used, configure the equivalent publisher on TestPyPI with environment `testpypi`; production PyPI configuration does not automatically configure TestPyPI.

## GitHub environments

The production job declares the GitHub environment `pypi`.

Recommended for `pypi`:

- require manual approval from the repository owner/maintainer where the account plan/settings permit it;
- prevent unreviewed branches from deploying where practical;
- keep no PyPI API token secret because OIDC is used instead.

If TestPyPI is used, apply the same pattern to a `testpypi` environment.

## Release sequence for the next version

1. Change the release identity in `src/ainir/_version.py` deliberately. Never reuse an already-published version.
2. Run normal repository CI and review the public scope/release wording.
3. Run `publish-pypi` with target `build-only` and require a green build/verification job.
4. Optionally publish the verified artifact to TestPyPI.
5. Re-check the production Trusted Publisher identity and GitHub `pypi` environment.
6. Run `publish-pypi` with target `pypi`.
7. Confirm the PyPI project/version and run a clean-environment install smoke.
8. Only then update release-specific public copy that depends on the new published artifact.

A clean-environment smoke can use:

```bash
python -m venv /tmp/ainir-pypi-check
/tmp/ainir-pypi-check/bin/python -m pip install --upgrade pip
/tmp/ainir-pypi-check/bin/python -m pip install ainir
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

## Package identity

The public names are intentionally aligned:

- PyPI distribution: `ainir`
- Python package: `ainir`
- console command: `ainir`

That keeps the default user experience simple: `python -m pip install ainir`, followed by `ainir demo`.
