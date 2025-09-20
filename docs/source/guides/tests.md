# Test Matrix & Conventions

Testing strategy and conventions for Theory API across unit, integration, Docker-required, and acceptance suites.

## Pytest Configuration

Located in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "unit: fast tests with minimal dependencies",
    "integration: integration tests",
    "requires_postgres: needs PostgreSQL",
    "requires_docker: needs Docker",
    "property: Hypothesis property-based tests",
    "slow: long-running tests"
]
testpaths = ["tests", "code/tests"]
```

## Mode Guidelines

Processors now accept explicit `mode` values (`mock` or `real`). Tests must set the mode rather than relying on environment variables.

- **Unit tests** use `mode="mock"` to avoid Docker/MinIO.
- **Integration tests** targeting Docker flows set `mode="real"`.
- Modal smoke tests call `modal_app.smoke`, which forces `mode="mock"`.

Example helper for unit tests:

```python
from libs.runtime_common.mode import resolve_mode
from apps.core.adapters.local_adapter import LocalAdapter

adapter = LocalAdapter()
inputs = {"schema": "v1", "params": {"messages": []}, "mode": "mock"}
mode = resolve_mode(inputs)
result = adapter.invoke(...)
```

## Contract Tests

### Envelope Parity

```python
@pytest.mark.unit
def test_adapter_envelope_parity():
    adapters = [
        (LocalAdapter(), {"schema": "v1", "params": {}, "mode": "mock"}),
        (LocalAdapter(), {"schema": "v1", "params": {}, "mode": "real"}),
    ]
    for adapter, payload in adapters:
        result = adapter.invoke(...)
        assert result["status"] in {"success", "error"}
        assert result["execution_id"]
```

### Error Codes

```python
@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        {"schema": "v1", "params": {}, "mode": "mock"},
        {"schema": "v1", "params": {}, "mode": "real"},
    ],
)
def test_missing_secret_error(payload):
    adapter = LocalAdapter()
    result = adapter.invoke(
        processor_ref="llm/litellm@1",
        inputs_json=payload,
        write_prefix="/artifacts/outputs/test/{execution_id}/",
        execution_id="test",
        registry_snapshot=get_test_registry(),
        adapter_opts={},
        secrets_present=[],
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "ERR_MISSING_SECRET"
```

## CI / Local Commands

```bash
# Fast unit lane (mock mode, SQLite)
make test-unit

# Acceptance lane (Docker + mock mode)
make test-acceptance

# Property tests
make test-property
```
