# PyPI publishing for AiNIR

AiNIR's public Python distribution is named **`ainir`**. The Python package and installed console command are also **`ainir`**.

This document describes the bounded RC publishing path. It does not change AiNIR's pre-v1 / non-production claim boundary.

## Public install experience

The first-run path is:

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
3. `pypi` — publish the already-verified distributions to PyPI and, after a successful upload, verify that exact version from the public PyPI index.

The workflow does not trigger on `push`, tags, GitHub Releases, or a schedule. A normal repository update therefore cannot publish a package by itself.

Before any publishing job can run, the build job:

- resolves the source release version and exposes it as a job output;
- installs the locked runtime dependency needed by the release checks;
- runs the existing distribution contract suite;
- builds exactly one wheel and one sdist;
- checks that wheel metadata says `ainir` and matches the source release version;
- installs the wheel into a fresh virtual environment;
- changes outside the source checkout;
- runs both `python -m ainir demo` and the installed `ainir demo` console command;
- uploads the verified wheel/sdist as a GitHub Actions artifact for the publishing job.

## Post-publication public-index smoke

When target `pypi` succeeds, the workflow starts a separate `verify-public-pypi-install` job.

That job deliberately does **not** check out the repository and does **not** download the build artifact. Instead it:

1. creates a fresh virtual environment on a new runner;
2. installs the exact source release version with `--no-cache-dir --index-url https://pypi.org/simple`;
3. retries briefly to tolerate normal PyPI index propagation delay;
4. verifies `importlib.metadata.version("ainir")` exactly matches the release version;
5. changes to the runner temp directory, outside any source checkout;
6. runs both `python -m ainir demo` and the installed `ainir demo` console command.

This closes the gap between “the artifact uploaded successfully” and “a new user can actually obtain and run that exact artifact from public PyPI.”

A failed post-publication smoke does **not** roll back or delete a PyPI upload. PyPI releases are immutable in normal operation. If the upload job is green but the smoke job is red, first determine whether the failure is only index propagation/networking or an actual artifact defect. Do not attempt to overwrite the same version.

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
7. Require both `publish-to-pypi` and `verify-public-pypi-install` to be green before treating the release path as fully verified.
8. Only then update release-specific public copy that depends on the new published artifact.

For an independent manual re-check, use the exact published version rather than an unconstrained latest install:

```bash
VERSION=1.0.0rc2
python -m venv /tmp/ainir-pypi-check
/tmp/ainir-pypi-check/bin/python -m pip install --upgrade pip
/tmp/ainir-pypi-check/bin/python -m pip install --no-cache-dir --index-url https://pypi.org/simple "ainir==$VERSION"
cd /tmp
/tmp/ainir-pypi-check/bin/python -m ainir demo
/tmp/ainir-pypi-check/bin/ainir demo
```

On Windows, use the corresponding virtual-environment executables under `Scripts\\`.

## Release identity rules

Do not publish a new artifact by overwriting an existing PyPI version. PyPI releases are immutable in normal operation.

For a new RC or final release:

1. change the version/release identity in `src/ainir/_version.py` deliberately;
2. run the normal AiNIR CI and distribution checks;
3. review README/scope wording for the new release state;
4. use `build-only` before selecting a publishing target;
5. after production publishing, require the public-index smoke for the exact version.

## Package identity

The public names are intentionally aligned:

- PyPI distribution: `ainir`
- Python package: `ainir`
- console command: `ainir`

That keeps the default user experience simple: `python -m pip install ainir`, followed by `ainir demo`.
