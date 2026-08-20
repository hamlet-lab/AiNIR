# Suggested GitHub Repository Settings

## Repository name

`ainir`

## Description

Recommended public description:

> Semantic trust layer that checks AI-agent actions and MCP tool calls before execution.

This is intentionally easier to discover and understand than the internal architectural definition. The README can carry the more precise bounded-RC scope.

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
- `runtime-safety`
- `agent-governance`
- `semantic-verification`
- `policy-as-code`
- `intermediate-representation`
- `semantic-ir`
- `python`

The intent is to let people discover AiNIR using terms they already know before asking them to learn AiNIR-specific vocabulary.

## README social-preview message

For future social-preview artwork or a project page, prefer the short public message:

> **Model output is a claim, not a fact.**
>
> AI proposes. AiNIR checks whether the proposal has earned the right to proceed.

Avoid presenting the project as a universal arbitrary-code verifier or a replacement for authentication, authorization, sandboxing, or runtime security.

## Visibility

Recommended launch sequence:

1. Keep the public repository contents bounded to the intended release surface.
2. Run `python scripts/run_prelaunch_check.py --out-dir /tmp/ainir_prelaunch_results` before major release changes.
3. Confirm the full private RC archive and private corpora are not included.
4. Keep the repository public only with the deliberately released public-demo surface.

Do not publish the private RC archive, full corpus, extended hardening suite, or enterprise policy packs unless deliberately releasing them later.
