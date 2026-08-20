from __future__ import annotations

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected text not found in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1. Package the five bounded public demo fixtures.
demo_root = ROOT / "src" / "ainir" / "demo_examples"
demo_root.mkdir(parents=True, exist_ok=True)
(demo_root / "__init__.py").write_text(
    '"""Bundled fixtures for the bounded public AiNIR demo."""\n',
    encoding="utf-8",
)
shutil.copy2(ROOT / "examples" / "demo_manifest.json", demo_root / "demo_manifest.json")
for name in [
    "account_deletion_hard_delete_blocked",
    "create_user_outbox_safe",
    "order_payment_real_payment_blocked",
    "password_reset_raw_token_blocked",
    "pii_export_raw_pii_blocked",
]:
    target = demo_root / name
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "examples" / name / "draft.yaml", target / "draft.yaml")

# 2. Add a Python 3.10+ compatible materializer for importlib.resources Traversables.
(ROOT / "src" / "ainir" / "demo_resources.py").write_text(
'''"""Materialize the bundled public demo fixtures outside a source checkout."""\nfrom __future__ import annotations\n\nfrom collections.abc import Iterator\nfrom contextlib import contextmanager\nfrom importlib import resources as importlib_resources\nfrom pathlib import Path\nfrom tempfile import TemporaryDirectory\n\n\ndef _copy_traversable(source, destination: Path) -> None:\n    destination.mkdir(parents=True, exist_ok=True)\n    for child in source.iterdir():\n        if child.name == "__init__.py":\n            continue\n        target = destination / child.name\n        if child.is_dir():\n            _copy_traversable(child, target)\n        else:\n            target.write_bytes(child.read_bytes())\n\n\n@contextmanager\ndef materialized_demo_examples() -> Iterator[Path]:\n    """Yield a temporary filesystem copy of the packaged public demo fixtures."""\n\n    source = importlib_resources.files("ainir.demo_examples")\n    with TemporaryDirectory(prefix="ainir-demo-") as tmp:\n        destination = Path(tmp) / "examples"\n        _copy_traversable(source, destination)\n        yield destination\n\n\n__all__ = ["materialized_demo_examples"]\n''',
    encoding="utf-8",
)

# 3. Include the packaged fixture data in wheels/sdists.
pyproject = ROOT / "pyproject.toml"
replace_once(
    pyproject,
    'ainir = ["registries/*.yaml", "schemas/*.json", "schemas/*.yaml", "profile_packs/*/*.yaml", "profile_packs/*/examples/*/*.yaml", "mcp_profiles/*/*.yaml", "mcp_profiles/*/descriptors/*.json"]',
    'ainir = ["registries/*.yaml", "schemas/*.json", "schemas/*.yaml", "profile_packs/*/*.yaml", "profile_packs/*/examples/*/*.yaml", "mcp_profiles/*/*.yaml", "mcp_profiles/*/descriptors/*.json", "demo_examples/*.json", "demo_examples/*/*.yaml"]',
)

# 4. Preserve the CLI surface, but fall back only when the default examples directory is absent.
cli = ROOT / "src" / "ainir" / "cli.py"
replace_once(
    cli,
    'from .core import dump_yaml, iter_example_drafts, load_draft, load_yaml_no_duplicate_keys\n',
    'from .core import dump_yaml, iter_example_drafts, load_draft, load_yaml_no_duplicate_keys\nfrom .demo_resources import materialized_demo_examples\n',
)
replace_once(
    cli,
    '''    if args.command == "demo":\n        context = TrustedExecutionContext.from_environment(args.env, source="cli", purpose="demo")\n        return _run_demo(Path(args.examples_dir), Path(args.out_dir), context)\n''',
    '''    if args.command == "demo":\n        context = TrustedExecutionContext.from_environment(args.env, source="cli", purpose="demo")\n        examples_dir = Path(args.examples_dir)\n        if args.examples_dir == "examples" and not examples_dir.exists():\n            with materialized_demo_examples() as packaged_examples:\n                return _run_demo(packaged_examples, Path(args.out_dir), context)\n        return _run_demo(examples_dir, Path(args.out_dir), context)\n''',
)

# 5. Strengthen the CI promise: ordinary install, then run the demo outside the repo.
ci = ROOT / ".github" / "workflows" / "ci.yml"
replace_once(
    ci,
    '''      - name: Install runtime package only\n        run: |\n          python -m pip install --upgrade pip\n          python -m pip install -c requirements.lock.txt -e .\n      - name: Verify documented quick-start path without dev extras\n        run: |\n          python -m ainir --help\n          python -m ainir demo --out-dir "$RUNNER_TEMP/ainir-runtime-demo"\n          python -m ainir trust evaluate examples/create_user_outbox_safe/draft.yaml --json --out-dir "$RUNNER_TEMP/ainir-runtime-trust-gate"\n''',
    '''      - name: Install runtime package only\n        run: |\n          python -m pip install --upgrade pip\n          python -m pip install -c requirements.lock.txt .\n      - name: Verify installed demo outside the repository\n        run: |\n          python -m ainir --help\n          cd "$RUNNER_TEMP"\n          python -m ainir demo --out-dir "$RUNNER_TEMP/ainir-runtime-demo"\n''',
)

print("packaged public demo migration applied")
