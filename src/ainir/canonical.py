"""Supported canonical JSON and defensive JSON artifact helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

MAX_JSON_BYTES = 1_000_000
MAX_JSON_DEPTH = 160


class DuplicateKeyJSONError(ValueError):
    """Raised when a JSON object contains duplicate keys."""


class NonFiniteJSONNumberError(ValueError):
    """Raised when JSON uses NaN or Infinity values."""


def reject_duplicate_json_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise DuplicateKeyJSONError(f"duplicate JSON key {key!r}")
        seen.add(key)
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise NonFiniteJSONNumberError(f"non-finite JSON number {value!r} is forbidden")


def json_depth(value: Any, *, limit: int = MAX_JSON_DEPTH, current: int = 0) -> int:
    if current > limit:
        raise ValueError(f"JSON nesting depth exceeds {limit}")
    if isinstance(value, dict):
        if not value:
            return current
        return max(json_depth(item, limit=limit, current=current + 1) for item in value.values())
    if isinstance(value, list):
        if not value:
            return current
        return max(json_depth(item, limit=limit, current=current + 1) for item in value)
    return current


def canonical_json(value: Any) -> str:
    """Return AiNIR canonical JSON used for local integrity hashes."""

    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


@dataclass(frozen=True)
class JSONArtifactResult:
    ok: bool
    path: str
    artifact_name: str
    value: dict[str, Any] | None = None
    reason: str | None = None
    detail: str | None = None
    raw_file_sha256: str | None = None
    canonical_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def read_json_object_artifact(
    path: str | Path,
    *,
    artifact_name: str = "artifact",
    max_bytes: int = MAX_JSON_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
) -> JSONArtifactResult:
    """Read a bounded UTF-8, duplicate-key-free JSON object from disk."""

    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        return JSONArtifactResult(False, str(source), artifact_name, reason="json_file_read_error", detail=str(exc))
    raw_hash = sha256_bytes(raw)
    if len(raw) > max_bytes:
        return JSONArtifactResult(
            False,
            str(source),
            artifact_name,
            reason="json_file_too_large",
            detail=f"JSON artifact exceeds {max_bytes} byte limit",
            raw_file_sha256=raw_hash,
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return JSONArtifactResult(False, str(source), artifact_name, reason="json_utf8_decode_error", detail=str(exc), raw_file_sha256=raw_hash)
    try:
        value = json.loads(
            text,
            object_pairs_hook=reject_duplicate_json_keys,
            parse_constant=_reject_non_finite,
        )
    except DuplicateKeyJSONError as exc:
        return JSONArtifactResult(False, str(source), artifact_name, reason="json_duplicate_key", detail=str(exc), raw_file_sha256=raw_hash)
    except NonFiniteJSONNumberError as exc:
        return JSONArtifactResult(False, str(source), artifact_name, reason="json_non_finite_number", detail=str(exc), raw_file_sha256=raw_hash)
    except json.JSONDecodeError as exc:
        return JSONArtifactResult(False, str(source), artifact_name, reason="json_decode_error", detail=str(exc), raw_file_sha256=raw_hash)
    except (RecursionError, MemoryError, ValueError) as exc:
        return JSONArtifactResult(False, str(source), artifact_name, reason="json_resource_error", detail=str(exc), raw_file_sha256=raw_hash)
    if not isinstance(value, dict):
        return JSONArtifactResult(False, str(source), artifact_name, reason="json_root_not_object", detail=type(value).__name__, raw_file_sha256=raw_hash)
    try:
        json_depth(value, limit=max_depth)
    except (ValueError, RecursionError, MemoryError) as exc:
        return JSONArtifactResult(False, str(source), artifact_name, reason="json_depth_limit_exceeded", detail=str(exc), raw_file_sha256=raw_hash)
    return JSONArtifactResult(
        True,
        str(source),
        artifact_name,
        value=value,
        raw_file_sha256=raw_hash,
        canonical_sha256=sha256_json(value),
    )


__all__ = [
    "DuplicateKeyJSONError",
    "JSONArtifactResult",
    "MAX_JSON_BYTES",
    "MAX_JSON_DEPTH",
    "NonFiniteJSONNumberError",
    "canonical_json",
    "json_depth",
    "read_json_object_artifact",
    "reject_duplicate_json_keys",
    "sha256_bytes",
    "sha256_json",
    "sha256_text",
]
