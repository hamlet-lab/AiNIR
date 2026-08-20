# Distribution and public-resource contracts

AiNIR's public Python release identity is defined once in `src/ainir/_version.py`.
The build metadata in `pyproject.toml` reads that value dynamically, so an installed
wheel and `ainir.__version__` must report the same PEP 440 version.

Current candidate identity:

- Python distribution: `ainir`
- Python version: `1.0.0rc2`
- Release tag: `v1.0.0-rc.2`
- Status: release candidate, not v1.0 final and not a production runtime

`package.json` is private metadata used only to pin the TypeScript compiler for
skeleton compilation checks. Its `0.0.0-private` value is intentionally not an
AiNIR release version.

## Supported resource API

Public schemas and registries are packaged under `ainir.schemas` and
`ainir.registries`. Consumers should not derive filesystem paths from
`ainir.__file__`; use `ainir.resources` instead:

```python
from ainir.resources import (
    PUBLIC_SCHEMA_NAMES,
    public_resource_manifest,
    read_schema_text,
)

schema = read_schema_text("trust_receipt.schema.json")
manifest = public_resource_manifest()
```

The API allowlists known filenames and rejects path traversal or undeclared
resources. The deterministic manifest records byte size and SHA-256 for every
public schema and registry.

## Distribution verification

Run the complete wheel/sdist contract check from the repository root:

```bash
python scripts/check_distribution_contracts.py
```

The check builds in an isolated scratch copy without network access, inspects the
wheel and source distribution, installs the wheel into a separate target, runs
the module CLI outside the checkout, compares source and installed resource
hashes, passes the safe Trust Gate example, issues a TrustReceipt with its
RegistrySnapshot sidecar, validates identity RegistryDiff and migration artifacts,
confirms current-registry replay, verifies unsigned migrated replay is refused by
default, confirms the explicit bounded local opt-in path leaves the historical
receipt unchanged, and runs the installed-wheel offline EvidenceProvider readiness
flow plus `evidence bundle`, `evidence policy`, and `evidence resolve` CLI checks.
