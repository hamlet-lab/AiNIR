# Workflow Profile Authoring SDK

AiNIR workflow profiles are additive, non-executing semantic extensions. They let contributors register a bounded workflow contract and its conformance evidence without editing the core verifier or weakening the Trust Gate.

## Create a profile

```bash
ainir profile init profiles/example-audit \
  --profile-id example.audit.v1 \
  --workflow-id AuditRequest
```

The command creates:

- `profile.yaml` — `ainir.profile-manifest.v1`;
- `conformance.yaml` — `ainir.conformance-pack.v1`;
- `README.md` — the local validation commands.

Validate and inspect it:

```bash
ainir profile validate profiles/example-audit/profile.yaml
ainir profile inspect profiles/example-audit/profile.yaml --json
ainir profile list --kind workflow --root profiles
```

The bundled closed-world profile is available by stable ID:

```bash
ainir profile validate ainir.public-demo.v1
ainir profile inspect ainir.public-demo.v1
```

## Required coverage

A profile must explicitly identify:

- workflow IDs and aliases;
- semantic roles and operation specs;
- declared effects and exact capabilities;
- evidence records and claim bindings;
- transaction requirements where applicable;
- positive, negative, mutation, and receipt-replay conformance coverage.

Unknown workflows, operations, and effects remain refused. Model output cannot become evidence, a consumer cannot override the Trust Gate, and AiNIR core does not execute actions.

## Reviewed vocabulary boundary

P3 authoring profiles may **compose only the exact effect and capability identifiers already reviewed in the packaged registries**. They cannot create effect aliases, role-marker classifiers, effect-to-capability contracts, external-effect allowlists, effect families, or capability-prefix rules. Safety-critical operation names and aliases are also rejected rather than reclassified as benign profile operations.

Those changes alter the global semantic taxonomy and therefore require a separate core-registry governance review. A profile proposal that needs a new effect or capability should document the requested identifier and threat model, but it must not smuggle that vocabulary into an additive profile.

`profile_fixture` evidence is scoped to the isolated conformance bundle. It demonstrates claim/evidence binding and is not a production credential, signature, or live provider assertion.

## Isolation boundary

An additive profile is compiled into a context-local registry bundle. It cannot replace an existing workflow, operation, evidence record, effect contract, alias, or protected role marker. The bundle exists only while its conformance run is active; leaving that context restores the packaged registries and their original snapshot hash.

A profile-bound TrustReceipt records the compiled profile registry snapshot, manifest hash, and conformance-pack hash. This is an audit binding, not a production signature or runtime authorization.

## Status

Profile Manifest v1 and the authoring/conformance SDK are implemented for bounded public review. They are not a production registry service, plugin marketplace, live evidence backend, or arbitrary-workflow verification system.
