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
    # Deferred debt: move shared candidate/run payload serialization out of API.
    ("ecommerce/source_url_agent/candidate_history_service.py", "ecommerce.api.source_url_agent.serializers"),
}

ALLOWED_SOURCE_URL_AGENT_AGENT_IMPORTS = {
    "ecommerce/api/source_url_agent/runs.py",
    "ecommerce/api/source_url_agent/serializers.py",
    "ecommerce/api/source_url_agent/state.py",
    "ecommerce/jobs/source_url_agent.py",
    "ecommerce/source_url_agent/__init__.py",
    "ecommerce/source_url_agent/job_handler.py",
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
    return imports


def _repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _src_relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT / "src").as_posix()


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
                allowed = (relative, imported) in ALLOWED_NON_API_IMPORTS_FROM_API
                if not allowed:
                    violations.append(f"{relative} imports {imported}")

    assert violations == []


def test_source_url_agent_agent_compat_imports_are_known_only() -> None:
    violations = []
    for path in _python_files(SRC_ROOT):
        relative = _src_relative(path)
        if "ecommerce.source_url_agent.agent" in _module_imports(path):
            if relative not in ALLOWED_SOURCE_URL_AGENT_AGENT_IMPORTS:
                violations.append(f"{relative} imports ecommerce.source_url_agent.agent")

    assert violations == []


def test_application_code_does_not_import_old_db_wrapper_modules() -> None:
    violations = []
    for path in _python_files(SRC_ROOT):
        relative = _src_relative(path)
        imports = _module_imports(path)
        for imported in sorted(imports & DEPRECATED_DB_WRAPPER_MODULES):
            violations.append(f"{relative} imports {imported}")

    assert violations == []
