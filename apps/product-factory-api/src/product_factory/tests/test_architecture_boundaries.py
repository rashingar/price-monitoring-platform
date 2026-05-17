import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "product_factory"
REPO_ROOT = PROJECT_ROOT.parents[2]

API_JOB_COMPAT_MODULES = {
    "product_factory.api.job_models",
    "product_factory.api.job_runner",
    "product_factory.api.job_store",
}


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*")
    return imports


def _src_relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _obvious_unreachable_locations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    locations: list[str] = []

    def check_block(statements: list[ast.stmt]) -> None:
        terminator_line: int | None = None
        for statement in statements:
            if terminator_line is not None:
                locations.append(
                    f"{_repo_relative(path)}:{statement.lineno} follows terminator on line {terminator_line}"
                )
                return

            if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                terminator_line = statement.lineno

            for field_name in ("body", "orelse", "finalbody"):
                nested = getattr(statement, field_name, None)
                if isinstance(nested, list):
                    check_block(nested)
            for handler in getattr(statement, "handlers", []):
                check_block(handler.body)

    check_block(tree.body)
    return locations


def test_non_api_runtime_code_does_not_import_api_job_compat_shims() -> None:
    violations = []
    for path in _python_files(PACKAGE_ROOT):
        relative = _src_relative(path)
        if relative.startswith(("product_factory/api/", "product_factory/tests/")):
            continue
        for imported in _module_imports(path):
            if imported in API_JOB_COMPAT_MODULES:
                violations.append(f"{relative} imports {imported}")

    assert violations == []


def test_jobs_runtime_has_no_obviously_unreachable_blocks() -> None:
    violations = []
    for path in _python_files(PACKAGE_ROOT / "jobs"):
        violations.extend(_obvious_unreachable_locations(path))

    assert violations == []
