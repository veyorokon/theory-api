import pathlib
import re
import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[3]  # repository root
PROC_DIR = ROOT / "code" / "apps" / "core" / "processors"

FORBIDDEN = (
    re.compile(r"^\s*from\s+apps\.core\.", re.MULTILINE),
    re.compile(r"^\s*import\s+apps\.core(\.|$)", re.MULTILINE),
    re.compile(r"^\s*from\s+django(\.|$)", re.MULTILINE),
)


def test_processors_do_not_import_django_or_core_logging():
    offenders = []
    for py in PROC_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if any(p.search(text) for p in FORBIDDEN):
            offenders.append(str(py.relative_to(ROOT)))
    assert offenders == [], f"Processors must be Django-free. Offenders: {offenders}"
