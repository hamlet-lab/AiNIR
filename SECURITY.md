# Security policy

AiNIR is a security-sensitive research and public-demo project, not a production runtime.

## Reporting a vulnerability

Use GitHub private vulnerability reporting or a private security advisory for this repository when available. Do not open a public issue containing exploit details, credentials, private data, or a working bypass.

If no private channel is available, open a minimal public issue asking the maintainer to establish a private contact channel. Include no exploit details in that issue.

A useful private report includes:

- affected commit or release;
- the violated invariant from `PROTECTED_INVARIANTS.md`;
- minimal reproduction input;
- expected and actual Trust Gate result;
- impact on lowering, handoff, receipt, replay, registry, or evidence handling;
- whether the issue is deterministic;
- a proposed regression test, when possible.

## Supported security scope

Security fixes target the current `main` branch and the latest published release candidate. Older snapshots may receive documentation-only guidance rather than patches.

## Explicit non-goals

This repository does not provide production deployment support, credential storage, a network service, or a host execution sandbox. A passing AiNIR decision does not replace operating-system, application, authorization, or runtime security controls.
