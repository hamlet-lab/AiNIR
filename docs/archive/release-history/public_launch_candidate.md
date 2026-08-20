# Public Launch Candidate Notes — Historical Record

> **Status:** the public-launch candidate gate has been completed. `hamlet-lab/AiNIR` is public and the Python distribution is `ainir`. This document is retained to preserve the reasoning and public/private boundary that preceded launch; it is not a current "before publishing" checklist.

## Original goal

Make the core idea legible in 5–10 minutes:

> Model output is a claim, not a fact.

The repository should show a concrete, bounded pipeline where unsupported or unsafe model-generated workflow and tool-call proposals are refused before host-owned execution.

## Current public state

Use these maintained entry points instead of the former pre-publication checklist:

- [`../../../README.md`](../../../README.md) — public first impression and Quick Start
- [`../../../START_HERE.md`](../../../START_HERE.md) — guided install/demo path
- [`../../integration_quickstart.md`](../../integration_quickstart.md) — bounded five-minute host integration
- [`../../pre_v1_status.md`](../../pre_v1_status.md) — current RC status and claim boundary
- [`../../github_launch_checklist.md`](../../github_launch_checklist.md) — current public-RC maintenance checklist
- [`../../PYPI_PUBLISHING.md`](../../PYPI_PUBLISHING.md) — manual PyPI release process

Current GitHub description:

```text
Semantic trust layer that checks AI-agent actions and MCP tool calls before execution.
```

The exact current topics are recorded in [`../../github_repo_settings.md`](../../github_repo_settings.md) rather than duplicated here as launch suggestions.

## Historical pre-publication checks

Before the repository became public, the launch candidate was expected to satisfy all of the following:

- run `python scripts/run_prelaunch_check.py --out-dir /tmp/ainir_prelaunch_results`;
- confirm the public checks passed;
- exclude private archive ZIPs and generated check folders;
- keep README wording explicitly pre-v1 / RC / non-production;
- preserve [`../../public_private_boundary.md`](../../public_private_boundary.md);
- verify repository metadata and the intended public surface.

Those checks remain useful release regressions, but the instruction to upload to a private GitHub repository first is historical.

## What remains private

Do not publish the full private RC archive, extended workflow suite, enterprise policy packs, private hardening corpora, or private evaluation packs unless a separate release decision is made.

The public repository being live does not widen that boundary.
