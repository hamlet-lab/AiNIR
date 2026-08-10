# AiNIR v1 Roadmap

AiNIR v1.0 RC Candidate is a bounded public demo and private review package. The next steps are about hardening scope, governance, and reproducibility rather than expanding the public demo indiscriminately.

## Near-term

- GitHub private-trial validation;
- README and GitHub Actions rendering check;
- final public/private boundary check;
- one external-style review pass;
- v1.0 RC1 decision.

## v1.x hardening targets

- harden the implemented workflow profile extension process through external review;
- external review and governance for the implemented offline EvidenceProvider contracts;
- public-key issuer identity and an explicitly reviewed ledger-promotion contract;
- canonical effect taxonomy;
- harden the implemented registry snapshot, semantic diff, and explicit migration replay through external review;
- add cryptographic migration authorization without weakening the current fail-closed local-review path;
- developer-facing registry authoring guide and community profile governance;
- clearer executable-claim semantics;
- optional consumer profile conformance packs.
- external review and governance for non-workspace MCP tool-call profiles without adding an MCP execution runtime;

## Not planned for v1.0 final

- production host runtime;
- enterprise evidence backend;
- full arbitrary workflow verification;
- downstream compiler/runtime integration;
- universal effect-name classification.

The core v1 claim should remain conservative: AiNIR provides a semantic trust layer and reproducible Trust Gate decisions for bounded, registry-backed workflows.

## Post-RC hardening notes from Patch 4

The RC candidate keeps the public demo bounded and conservative. Future production work should continue with:

- registry governance beyond the implemented local additive profile SDK;
- networked and enterprise evidence provider adapters beyond the implemented offline fixture/file/signed-bundle set;
- canonical effect taxonomy publication and migration;
- production governance and cryptographic authorization for the implemented snapshot/current/migrated TrustReceipt replay modes;
- server-safe TrustReceipt manifest locking;
- optional external consumer conformance packs.
- separately governed MCP profile extension, public-key server identity, and host integration examples that preserve the non-executing core boundary.


## Infrastructure direction

The long-term direction is a profile-based semantic trust framework, not a single monolithic registry. AiNIR should grow through domain profiles with explicit workflow contracts, canonical effects, evidence providers, and conformance packs.

The main test for future versions is not whether more rules can be added. It is whether new semantic domains can be registered, reviewed, versioned, replayed, and audited without weakening the Trust Gate.
