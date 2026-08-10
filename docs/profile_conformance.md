# Standalone Profile Conformance Runner

Run any valid workflow profile with:

```bash
ainir conformance run <profile.yaml-or-bundled-id> --out-dir <directory>
```

The bundled public profile unifies the existing golden traces and negative corpus:

```bash
ainir conformance run ainir.public-demo.v1 --out-dir /tmp/ainir-public-profile
```

## Output formats

The runner always writes the complete report bundle:

- `conformance_report.json`;
- `conformance_report.jsonl`;
- `conformance_report.junit.xml`;
- `conformance_report.yaml`;
- per-case Trust Gate decisions and requested replay reports.

Select standard output rendering with:

```bash
ainir conformance run profile.yaml --format console
ainir conformance run profile.yaml --format json
ainir conformance run profile.yaml --format jsonl
ainir conformance run profile.yaml --format junit
```

The report contract is `ainir.conformance-report.v1`. Its stable hash excludes only the local output path. Every case records the expected and actual trust status, lowering eligibility, finding rules, replay status, and receipt projection hash when applicable.

## Case categories

Every authored profile must cover:

- `positive` — a complete bounded workflow passes;
- `negative` — a required role, policy, evidence, effect, capability, or transaction binding is absent or wrong;
- `mutation` — an adversarial semantic variation remains refused;
- `replay` — a profile-bound receipt exact-replays against the same profile registry bundle.

A passing conformance report means the declared cases reproduced their expected decisions. It does not establish production readiness or prove all possible inputs safe.
## Fail-closed case contract

The validator refuses vacuous conformance declarations:

- a `positive` case must expect `passed` and `lowering_allowed: true`;
- a `negative` or `mutation` case must expect `refused`/`invalid`, forbid lowering, and name at least one required finding;
- a `replay` case must expect a passing decision, lowering eligibility, and successful exact replay;
- legacy golden-trace and negative-corpus source adapters are reserved for the bundled `ainir.public-demo.v1` profile. Additive profiles must provide explicit self-contained cases.

All case paths are confined to the profile directory. A passing report proves only that the declared bounded cases reproduced their expected decisions under the profile-bound registry snapshot.
