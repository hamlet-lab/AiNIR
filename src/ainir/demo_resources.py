from __future__ import annotations

from contextlib import contextmanager
from importlib import resources as importlib_resources
from pathlib import Path
import tempfile
from typing import Iterator


_DEMO_PACKAGE = "ainir.demo_examples"


def _copy_tree(source: object, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name == "__pycache__":
            continue
        destination = target / child.name
        if child.is_dir():
            _copy_tree(child, destination)
        elif child.name != "__init__.py":
            destination.write_bytes(child.read_bytes())


@contextmanager
def materialized_public_demo() -> Iterator[Path]:
    """Materialize the bundled public demo into a temporary examples directory.

    This keeps the existing file-based demo runner unchanged while allowing
    installed distributions to run ``ainir demo`` outside a source checkout.
    """

    package_root = importlib_resources.files(_DEMO_PACKAGE)
    with tempfile.TemporaryDirectory(prefix="ainir-public-demo-") as tmp:
        target = Path(tmp) / "examples"
        _copy_tree(package_root, target)
        yield target


__all__ = ["materialized_public_demo"]
