from __future__ import annotations

from pathlib import Path
import sys
from typing import Sequence

from .cli import main as cli_main
from .demo_resources import materialized_public_demo


def _has_examples_override(argv: Sequence[str]) -> bool:
    return any(
        item == "--examples-dir" or item.startswith("--examples-dir=")
        for item in argv[1:]
    )


def _repository_examples_available() -> bool:
    return (Path("examples") / "demo_manifest.json").is_file()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args or args[0] != "demo":
        return cli_main(args)

    if _has_examples_override(args) or _repository_examples_available():
        return cli_main(args)

    with materialized_public_demo() as examples_dir:
        return cli_main([*args, "--examples-dir", str(examples_dir)])


__all__ = ["main"]
