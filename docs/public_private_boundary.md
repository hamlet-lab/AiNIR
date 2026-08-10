# Public/private boundary

This repository is the **public demo slice** of AiNIR.

## Public

This repo includes:

- manifesto and architecture docs;
- five small examples;
- strict draft AST parser;
- safety registry;
- evidence ledger binding;
- operation spec registry;
- trusted execution context checks;
- lowering eligibility gate;
- negative conformance corpus and golden traces;
- a TypeScript skeleton lowerer with host enforcement hooks.
- bounded, non-executing MCP tool-call profile artifacts and conformance fixtures.

## Private by default

Keep these private unless a separate release decision is made:

- full RC archive;
- historical phase packages;
- full workflow suite;
- full negative mutation corpus;
- raw provider-output hardening corpus;
- enterprise policy packs;
- extended evidence ledger and trust promotion suite;
- production-grade provider/runtime adapters.
- production MCP transports, credentials, authorization services, tool implementations, and enterprise server profiles.

## Why split the project this way

The public repo should be easy to understand and safe to inspect. The private archive preserves the larger research corpus and implementation history without overwhelming the public demo or exposing unfinished enterprise assets.

The public goal is clarity, not completeness.
