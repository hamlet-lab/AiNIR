# Current GitHub Repository Settings

This document records the public settings that should match the live `hamlet-lab/AiNIR` repository. It is a maintenance reference, not a launch-time suggestion list.

## Repository identity

```text
owner: hamlet-lab
repository: AiNIR
visibility: public
default_branch: main
license: Apache-2.0
```

## Description

Current public description:

> Semantic trust layer that checks AI-agent actions and MCP tool calls before execution.

Keep this synchronized with the live repository unless a deliberate positioning change is made.

## Website

No project website is currently required. A future project page can be added deliberately without changing the technical claim boundary.

## Topics

Current repository topics:

- `agent-governance`
- `ai-agents`
- `ai-safety`
- `ai-security`
- `conformance-testing`
- `mcp`
- `policy-as-code`
- `pre-execution-validation`
- `python`
- `semantic-verification`
- `tool-calling`
- `tool-contracts`
- `trust-layer`

These are the maintained discovery labels. Do not silently replace them with older launch-draft topics such as `llm`, `runtime-safety`, `semantic-ir`, or `intermediate-representation` unless the repository metadata is intentionally changed too.

## Merge and branch settings

Current repository behavior includes:

```text
allow_auto_merge: false
delete_branch_on_merge: false
```

Branch cleanup therefore remains an explicit maintainer action rather than an automatic merge side effect.

## Social preview

The repository contains [`../assets/ainir-social-preview.png`](../assets/ainir-social-preview.png) as the intended social-preview artwork.

The asset communicates:

> **Model output is a claim, not a fact.**
>
> AI proposes. AiNIR checks whether the proposal has earned the right to proceed.

The presence of the asset in Git does not prove that GitHub's repository-level social-preview setting is currently rendering it. Verify the actual preview in the GitHub UI whenever that setting matters.

Avoid presenting the project as a universal arbitrary-code verifier or a replacement for authentication, authorization, sandboxing, or runtime security.

## Public release maintenance

For a release-affecting change:

1. keep the repository contents bounded to the intended public surface;
2. run the normal CI and release-contract checks;
3. keep the description/topics above synchronized with the live repository;
4. keep private archives, private corpora, and enterprise-only material out of the public repository;
5. follow [`PYPI_PUBLISHING.md`](PYPI_PUBLISHING.md) for any Python publication;
6. preserve the explicit non-production / pre-v1 claim boundary until a deliberate later release changes it.

Use [`public_launch_kit.md`](public_launch_kit.md) for maintained public-facing copy and [`github_launch_checklist.md`](github_launch_checklist.md) for the current repository/release maintenance checklist.
