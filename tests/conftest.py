import sys
import pathlib
import os
import json
import subprocess
import typing as t
import pytest

# Ensure repo root is importable so `import tests.tools.*` works everywhere.
_TESTS_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_CODE_DIR = _REPO_ROOT / "code"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

# Optional hardening: use pytest-socket if available
try:
    from pytest_socket import disable_socket, enable_socket  # type: ignore
except Exception:  # pragma: no cover
    disable_socket = None
    enable_socket = None

# ---------- Table-driven folder → marker mapping ----------

# Any test file under these subtrees is auto-marked accordingly.
# Keep this tiny and boring: folders are the taxonomy.
FOLDER_MARKS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("tests", "unit"), ("unit",)),
    (("tests", "property"), ("property",)),
    (("tests", "integration"), ("integration",)),
    (("tests", "integration", "adapters", "modal"), ("integration", "modal")),
    (("tests", "contracts"), ("contracts",)),
    (("tests", "acceptance"), ("acceptance", "requires_postgres", "requires_docker")),
    (("tests", "acceptance", "pr"), ("acceptance", "prlane", "requires_postgres", "requires_docker")),
    (("tests", "acceptance", "pinned"), ("acceptance", "supplychain", "requires_postgres", "requires_docker")),
    (("tests", "smoke"), ("deploy_smoke",)),
]


def _under(path_posix: str, *segments: str) -> bool:
    return f"/{'/'.join(segments)}/" in path_posix


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply markers from FOLDER_MARKS (pathlib/posix-safe)."""
    for item in items:
        p = pathlib.Path(str(item.fspath)).as_posix()
        for segs, marks in FOLDER_MARKS:
            if _under(p, *segs):
                for m in marks:
                    item.add_marker(getattr(pytest.mark, m))

    # Apply lane validation from marker plugin
    try:
        import sys
        from pathlib import Path

        # Add tests/tools to path for marker access
        tests_tools = Path(__file__).parent / "tools"
        if str(tests_tools) not in sys.path:
            sys.path.insert(0, str(tests_tools))
        from markers import pytest_collection_modifyitems as validate_markers

        validate_markers(config, items)
    except Exception:
        # Continue if marker validation unavailable
        pass


# ---------- Global, boring, deterministic env ----------
# ---------- Stable global env ----------
@pytest.fixture(autouse=True)
def _stable_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("PYTHONUNBUFFERED", "1")
    # Do not force LOG_STREAM globally. Tests should opt-in via fixtures:
    # - logs_to_stderr: for CLI/--json parsing scenarios
    # - logs_to_stdout: for unit tests that capture stdout behavior
    # Default app env (tests can override)
    monkeypatch.setenv("APP_ENV", os.getenv("APP_ENV", "dev"))
    # Default Django settings for tests if not provided by CI target
    if not os.getenv("DJANGO_SETTINGS_MODULE"):
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "backend.settings.unittest")

    # Ensure "code" package importable when tests run from repo root
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    code_dir = repo_root / "code"
    if str(code_dir) not in sys.path:
        sys.path.insert(0, str(code_dir))

    yield


# ---------- Registry-driven secret discovery ----------
@pytest.fixture(scope="session")
def registry_required_secrets() -> set[str]:
    """Walk embedded processor registry.yaml files and collect `secrets.required` names."""
    import yaml

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    processors_dir = repo_root / "code" / "apps" / "core" / "processors"
    secrets: set[str] = set()

    if processors_dir.exists():
        # Look for embedded registry.yaml in each processor directory
        for processor_dir in processors_dir.iterdir():
            if processor_dir.is_dir():
                registry_file = processor_dir / "registry.yaml"
                if registry_file.exists():
                    try:
                        doc = yaml.safe_load(registry_file.read_text(encoding="utf-8")) or {}
                        req = (doc.get("secrets") or {}).get("required") or []
                        for name in req:
                            if isinstance(name, str) and name:
                                secrets.add(name)
                    except Exception:
                        # Registry parse errors should fail the suite loudly where used,
                        # not here — we keep discovery tolerant.
                        pass
    return secrets


# ---------- Network control ----------
@pytest.fixture
def no_network():
    if disable_socket and enable_socket:
        disable_socket()
        try:
            yield
        finally:
            enable_socket()
    else:
        # Plugin not installed; best-effort hermeticity.
        yield


# ---------- Test services provisioning ----------
@pytest.fixture(scope="session", autouse=True)
def test_services():
    """Start all test services once per session."""
    import time

    # Ensure Docker is available
    try:
        subprocess.run(
            ["docker", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except Exception:
        pytest.skip("Docker not available")

    # Start all services with full profile
    try:
        subprocess.run(
            ["docker", "compose", "--profile", "full", "up", "-d"],
            check=True,
            capture_output=True,
            text=True,
        )

        # Quick check that services are running
        result = subprocess.run(
            ["docker", "compose", "ps", "--services"],
            capture_output=True,
            text=True,
        )
        running_services = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
        expected_services = {"postgres", "minio"}

        if not expected_services.issubset(running_services):
            pytest.fail(f"Expected services {expected_services} not all running. Found: {running_services}")

    except subprocess.CalledProcessError as e:
        pytest.fail(f"Failed to start test services: {e}")

    yield

    # Clean up services
    try:
        subprocess.run(
            ["docker", "compose", "down"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        pass  # Best effort cleanup


# ---------- Lane fixtures ----------
@pytest.fixture
def pr_lane_env(monkeypatch: pytest.MonkeyPatch, no_network, registry_required_secrets: set[str]):
    """PR lane: build from source, mock only, no secrets, filesystem storage."""
    monkeypatch.setenv("CI", "true")  # CI guard still active; mode=real forbidden
    # PR lane uses --build flag in CLI calls instead of environment variable
    # Strip all registry-required secrets to enforce hermetic behavior
    for name in registry_required_secrets:
        monkeypatch.delenv(name, raising=False)
    # Force filesystem (no S3/MinIO) unless a test opts-in
    for name in ("S3_ENDPOINT_URL", "S3_BUCKET", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def supplychain_env(monkeypatch: pytest.MonkeyPatch, registry_required_secrets: set[str]):
    """Supply-chain lane (dev/staging/main): pinned-only by default; secrets absent unless test sets."""
    monkeypatch.setenv("CI", "true")
    # Supply-chain lane avoids --build flag to use registry images only
    # Default: still hermetic. Pinned acceptance should not need secrets.
    for name in registry_required_secrets:
        monkeypatch.delenv(name, raising=False)
    yield


# ---------- Auto-apply lane fixtures ----------
@pytest.fixture(autouse=True)
def _auto_apply_lane_fixtures(request):
    """Automatically apply lane fixtures based on test markers."""
    if request.node.get_closest_marker("prlane"):
        request.getfixturevalue("pr_lane_env")
    if request.node.get_closest_marker("supplychain"):
        request.getfixturevalue("supplychain_env")


# ---------- Tiny helpers ----------
@pytest.fixture
def tmp_write_prefix(tmp_path: pathlib.Path):
    """Return a write_prefix rooted in temp, with {execution_id} template."""
    # Application requires absolute path under /artifacts/
    base = f"/artifacts/outputs/test/{tmp_path.name}/{{execution_id}}/"
    return base


@pytest.fixture
def load_json():
    def _load(pathlike: t.StrOrBytesPath):
        with open(pathlike, "rb") as f:
            return json.loads(f.read().decode("utf-8"))

    return _load


# ---------- Log stream opt-in helpers ----------
@pytest.fixture
def logs_to_stderr(monkeypatch: pytest.MonkeyPatch):
    """Ensure structured logs are written to stderr (for CLI --json tests)."""
    monkeypatch.setenv("LOG_STREAM", "stderr")
    yield


@pytest.fixture
def logs_to_stdout(monkeypatch: pytest.MonkeyPatch):
    """Ensure logs are written to stdout (for unit tests that capture stdout)."""
    monkeypatch.setenv("LOG_STREAM", "stdout")
    yield
