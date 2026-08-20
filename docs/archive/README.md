# AiNIR documentation archive

This directory contains historical development and release records that are useful for provenance and regression context but are **not current user guidance**.

For the maintained documentation surface, start with [`../README.md`](../README.md) or the repository-level [`START_HERE.md`](../../START_HERE.md).

## Why this archive exists

AiNIR was developed through many explicit verification phases and RC hardening passes. Keeping those records is useful, but leaving every phase note in the main `docs/` directory made the repository look much larger and made historical instructions easier to confuse with current guidance.

The archive keeps that lineage while giving the maintained docs a smaller front-stage surface.

## Development history

[`development/`](development/) contains dated baseline and P1–P7 development notes. These records describe how current contracts were reached; they are not required for installation or integration.

## Phase history

[`phases/`](phases/) contains the Phase 13–26 design/review notes that preceded the current RC surface. Executable phase-named regression code and tests remain in `src/`, `scripts/`, and `tests/` because they are still part of the RC verification suite; only the historical prose was archived here.

## Release history

[`release-history/`](release-history/) contains superseded RC patch notes and the historical public-launch candidate record.

Current release guidance remains in:

- [`../pre_v1_status.md`](../pre_v1_status.md)
- [`../v1_rc_candidate.md`](../v1_rc_candidate.md)
- [`../v1_rc_scope.md`](../v1_rc_scope.md)
- [`../v1_known_limitations.md`](../v1_known_limitations.md)
- [`../PYPI_PUBLISHING.md`](../PYPI_PUBLISHING.md)
- [`../github_launch_checklist.md`](../github_launch_checklist.md)

## Archive rule

Do not copy historical release state back into current onboarding or release instructions without a deliberate new review. Git history remains the authoritative record of when these documents moved and how they changed.
