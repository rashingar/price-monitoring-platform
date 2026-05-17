import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "ecommerce"
sys.path.insert(0, str(PROJECT_ROOT / "src"))


ALLOWED_DB_BARREL_IMPORTS = {
    "ecommerce/db/__init__.py",
}

ALLOWED_NON_API_IMPORTS_FROM_API = {
    # Contract tooling needs the assembled FastAPI app to export OpenAPI.
    ("ecommerce/jobs/export_openapi_snapshot.py", "ecommerce.api.app"),
}

DEPRECATED_DB_WRAPPER_MODULES = {
    "ecommerce.db.alerts",
    "ecommerce.db.capture_persistence",
    "ecommerce.db.observation_persistence",
    "ecommerce.db.product_source_repository",
    "ecommerce.db.source_convergence",
    "ecommerce.db.source_health",
    "ecommerce.db.source_url_repository",
}

REMOVED_COMPAT_MODULE_FILES = {
    "src/ecommerce/source_url_agent/agent.py",
    "src/ecommerce/db/alerts.py",
    "src/ecommerce/db/capture_persistence.py",
    "src/ecommerce/db/observation_persistence.py",
    "src/ecommerce/db/product_source_repository.py",
    "src/ecommerce/db/source_convergence.py",
    "src/ecommerce/db/source_health.py",
    "src/ecommerce/db/source_url_repository.py",
    "src/ecommerce/vendor_sources/run_repository.py",
}

REMOVED_COMPAT_IMPORTS = DEPRECATED_DB_WRAPPER_MODULES | {
    "ecommerce.source_url_agent.agent",
    "ecommerce.vendor_sources.run_repository",
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


def _repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _src_relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT / "src").as_posix()


def _project_relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _is_allowed_import(relative: str, imported: str, allowed_imports: set[tuple[str, str]]) -> bool:
    return any(
        relative == allowed_relative and (imported == allowed_import or imported.startswith(f"{allowed_import}."))
        for allowed_relative, allowed_import in allowed_imports
    )


def test_platform_health_does_not_import_api_modules() -> None:
    violations = []
    for path in _python_files(SRC_ROOT / "platform_health"):
        for imported in _module_imports(path):
            if imported == "ecommerce.api" or imported.startswith("ecommerce.api."):
                violations.append(f"{_repo_relative(path)} imports {imported}")

    assert violations == []


def test_application_code_does_not_import_deprecated_db_barrels() -> None:
    violations = []
    for path in _python_files(SRC_ROOT):
        relative = _src_relative(path)
        for imported in _module_imports(path):
            if imported in {"ecommerce.db.models", "ecommerce.db.repositories"} and relative not in ALLOWED_DB_BARREL_IMPORTS:
                violations.append(f"{relative} imports {imported}")

    assert violations == []


def test_non_api_imports_from_api_are_known_debt_only() -> None:
    violations = []
    for path in _python_files(SRC_ROOT):
        relative = _src_relative(path)
        if relative.startswith("ecommerce/api/"):
            continue
        for imported in _module_imports(path):
            if imported == "ecommerce.api" or imported.startswith("ecommerce.api."):
                allowed = _is_allowed_import(relative, imported, ALLOWED_NON_API_IMPORTS_FROM_API)
                if not allowed:
                    violations.append(f"{relative} imports {imported}")

    assert violations == []


def test_source_url_agent_candidate_history_service_does_not_import_api_modules() -> None:
    imports = _module_imports(SRC_ROOT / "source_url_agent" / "candidate_history_service.py")
    api_imports = sorted(
        imported for imported in imports if imported == "ecommerce.api" or imported.startswith("ecommerce.api.")
    )

    assert api_imports == []


def test_domain_and_service_code_do_not_import_api_route_modules() -> None:
    violations = []
    route_prefixes = ("ecommerce.api.routes_", "ecommerce.api.source_url_agent.")
    for path in _python_files(SRC_ROOT):
        relative = _src_relative(path)
        if relative.startswith("ecommerce/api/"):
            continue
        for imported in _module_imports(path):
            if imported.startswith(route_prefixes) and not _is_allowed_import(
                relative, imported, ALLOWED_NON_API_IMPORTS_FROM_API
            ):
                violations.append(f"{relative} imports {imported}")

    assert violations == []


def test_removed_compatibility_module_files_are_not_recreated() -> None:
    existing = [relative for relative in sorted(REMOVED_COMPAT_MODULE_FILES) if (PROJECT_ROOT / relative).exists()]

    assert existing == []


def test_source_and_tests_do_not_import_removed_compatibility_paths() -> None:
    violations = []
    for root in (SRC_ROOT, PROJECT_ROOT / "tests"):
        for path in _python_files(root):
            relative = _project_relative(path)
            imports = _module_imports(path)
            for imported in sorted(imports & REMOVED_COMPAT_IMPORTS):
                violations.append(f"{relative} imports {imported}")

    assert violations == []


def test_application_code_does_not_import_old_db_wrapper_modules() -> None:
    violations = []
    for path in _python_files(SRC_ROOT):
        relative = _src_relative(path)
        imports = _module_imports(path)
        for imported in sorted(imports & DEPRECATED_DB_WRAPPER_MODULES):
            violations.append(f"{relative} imports {imported}")

    assert violations == []


def test_critical_python_packages_have_no_obviously_unreachable_blocks() -> None:
    critical_roots = [
        SRC_ROOT / "platform_health",
        SRC_ROOT / "source_url_agent",
        SRC_ROOT / "db" / "repositories",
    ]
    violations = []
    for root in critical_roots:
        for path in _python_files(root):
            violations.extend(_obvious_unreachable_locations(path))

    assert violations == []
