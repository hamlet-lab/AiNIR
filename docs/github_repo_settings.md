# Suggested GitHub Repository Settings

## Repository name

`ainir`

## Description

Recommended public description:

> Semantic preflight for AI-agent actions before execution.

This is intentionally easier to discover and understand than the internal architectural definition. The README carries the more precise bounded-RC scope.

## Website

Leave blank at first, or link to a future project page.

## Topics

Recommended discovery topics, ordered from broad existing language toward AiNIR-specific language:

- `ai-agents`
- `agent-safety`
- `ai-safety`
- `llm`
- `mcp`
- `tool-calling`
- `ai-security`
- `runtime-safety`
- `agent-governance`
- `semantic-verification`
- `policy-as-code`
- `intermediate-representation`
- `semantic-ir`
- `python`

The intent is to let people discover AiNIR using terms they already know before asking them to learn AiNIR-specific vocabulary.

## Social preview

Use [`../assets/ainir-social-preview.png`](../assets/ainir-social-preview.png) as the repository social-preview artwork.

The asset uses the short public message:

> **Model output is a claim, not a fact.**
>
> AI proposes. AiNIR checks whether the proposal has earned the right to proceed.

It also shows the Trust Gate as a real branch: a passing proposal may continue to host-controlled execution, while a refused proposal stops and is explained.

Avoid presenting the project as a universal arbitrary-code verifier or a replacement for authentication, authorization, sandboxing, or runtime security.

## Public launch copy

Use [`public_launch_kit.md`](public_launch_kit.md) for the maintained one-line pitch, 30-second explanation, Show HN-style draft, developer-community draft, short-form copy, FAQ responses, and public claim-boundary rules.

## Visibility

Recommended launch sequence:

1. Keep the public repository contents bounded to the intended release surface.
2. Run `python scripts/run_prelaunch_check.py --out-dir /tmp/ainir_prelaunch_results` before major release changes.
3. Confirm the full private RC archive and private corpora are not included.
4. Apply the repository description and topics above.
5. Set `assets/ainir-social-preview.png` as the repository social preview.
6. Keep the repository public only with the deliberately released public-demo surface.

Do not publish the private RC archive, full corpus, extended hardening suite, or enterprise policy packs unless deliberately releasing them later.
