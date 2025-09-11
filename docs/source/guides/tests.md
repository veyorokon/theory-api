# Test Matrix & Conventions

Testing strategy and conventions for Theory API with multiple test types and database configurations.

## Test Markers & Configuration

### Pytest Configuration

```ini
[pytest]
DJANGO_SETTINGS_MODULE = backend.settings.unittest
pythonpath = .
testpaths = code
markers =
    unit: Fast tests with minimal dependencies
    integration: Slower tests with external services
    requires_postgres: Tests requiring PostgreSQL database
    ledger_acceptance: End-to-end ledger acceptance tests
```

### Test Categories

**Unit Tests** (`unit`):
- Fast execution (< 1 second per test)
- SQLite database or mocked dependencies
- No external service dependencies
- Focused on single functions or classes

**Integration Tests** (`integration`):
- Moderate execution time (1-10 seconds per test)
- May use external services or complex setups
- Test interaction between components
- Optional in CI (opt-in with environment variable)

**PostgreSQL Tests** (`requires_postgres`):
- Require PostgreSQL database
- Test database-specific features
- Used in acceptance lane of CI
- Include ledger acceptance tests

**Ledger Acceptance** (`ledger_acceptance`):
- End-to-end ledger behavior validation
- Require PostgreSQL for transaction testing
- Test event ordering and consistency
- Critical for production readiness

## Test Guard Implementation

### Environment-Based Test Skipping

```python
# conftest.py
import os
import pytest

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Skip tests based on environment and markers."""
    if "requires_postgres" in item.keywords:
        if os.getenv("DJANGO_SETTINGS_MODULE") != "backend.settings.test":
            pytest.skip("requires Postgres settings", allow_module_level=False)
    
    if "integration" in item.keywords:
        if not os.getenv("ENABLE_INTEGRATION_TESTS"):
            pytest.skip("integration tests disabled", allow_module_level=False)
```

### Django Settings Matrix

| Settings Module | Database | Purpose | CI Usage |
|-----------------|----------|---------|-----------|
| `backend.settings.unittest` | SQLite | Unit tests | Default PR checks |
| `backend.settings.test` | PostgreSQL | Acceptance tests | Full test suite |
| `backend.settings.development` | PostgreSQL | Local development | Manual testing |

## Test Execution Commands

### Local Development

**Unit tests only** (fast):
```bash
make test-unit
# Equivalent to: pytest -q -m "unit and not integration and not requires_postgres"
```

**All tests with PostgreSQL**:
```bash
DJANGO_SETTINGS_MODULE=backend.settings.test pytest -q
```

**Specific test categories**:
```bash
# Integration tests only
ENABLE_INTEGRATION_TESTS=1 pytest -m integration

# Ledger acceptance tests
DJANGO_SETTINGS_MODULE=backend.settings.test pytest -m ledger_acceptance

# PostgreSQL-specific tests
DJANGO_SETTINGS_MODULE=backend.settings.test pytest -m requires_postgres
```

### CI/CD Pipeline

**PR Checks** (fast feedback):
```bash
pytest -q -m "unit and not integration and not requires_postgres"
```

**Full Acceptance** (complete validation):
```bash
DJANGO_SETTINGS_MODULE=backend.settings.test pytest -q
```

**Property-Based Testing**:
```bash
make test-property
# Hypothesis-based property tests
```

## Contract Tests

### Envelope Parity

Test that all adapters return consistent envelope formats:

```python
@pytest.mark.unit
def test_adapter_envelope_parity():
    """All adapters return same envelope structure."""
    adapters = [LocalAdapter(), MockAdapter(), ModalAdapter()]
    
    for adapter in adapters:
        result = adapter.invoke(
            processor_ref="llm/litellm@1",
            inputs_json={"messages": [{"role": "user", "content": "test"}]},
            write_prefix="/artifacts/outputs/",
            execution_id="test-123",
            registry_snapshot=get_test_registry(),
            adapter_opts={},
            secrets_present=["OPENAI_API_KEY"]
        )
        
        # Validate envelope structure
        assert "status" in result
        assert "execution_id" in result
        assert result["execution_id"] == "test-123"
        
        if result["status"] == "success":
            assert "outputs" in result
            assert "index_path" in result
            assert "meta" in result
```

### Index Wrapper Validation

Test output index structure consistency:

```python
@pytest.mark.unit
def test_index_wrapper_format():
    """Index artifacts use consistent wrapper format."""
    # Test that index is always {"outputs": [...]}
    # Test that paths are sorted
    # Test compact JSON formatting
```

### WorldPath Canonicalization

Test path handling across all components:

```python
@pytest.mark.unit
def test_worldpath_duplicate_rejection():
    """Duplicate paths after canonicalization are rejected."""
    paths = [
        "/artifacts/outputs//text/file.txt",    # Double slash
        "/artifacts/outputs/text/file.txt",     # Clean path
    ]
    
    with pytest.raises(ValueError, match="ERR_OUTPUT_DUPLICATE"):
        validate_output_paths(paths)
```

### Modal Preflight Validation

Test Modal secrets and deployment:

```python
@pytest.mark.integration
def test_modal_secrets_preflight():
    """Modal adapter validates required secrets exist."""
    adapter = ModalAdapter()
    
    # Should fail if REGISTRY_AUTH missing
    with pytest.raises(Exception, match="REGISTRY_AUTH"):
        adapter.invoke(
            processor_ref="llm/litellm@1",
            inputs_json={},
            write_prefix="/artifacts/outputs/",
            execution_id="test",
            registry_snapshot=get_test_registry(),
            adapter_opts={},
            secrets_present=[]  # Missing secrets
        )
    
    # Should pass with required secrets
    result = adapter.invoke(
        processor_ref="llm/litellm@1",
        inputs_json={},
        write_prefix="/artifacts/outputs/",
        execution_id="test",
        registry_snapshot=get_test_registry(),
        adapter_opts={},
        secrets_present=["REGISTRY_AUTH", "OPENAI_API_KEY"]
    )
    assert result["status"] in ["success", "error"]
```

## Test Data Management

### Fixtures

**Registry snapshots**:
```python
@pytest.fixture
def test_registry_snapshot():
    """Minimal registry snapshot for testing."""
    return {
        "processors": {
            "llm/litellm@1": {
                "image": {"oci": "ghcr.io/test/llm_litellm@sha256:test"},
                "secrets": {"required": ["OPENAI_API_KEY"]},
                "runtime": {"cpu": "1", "memory_gb": 2, "timeout_s": 60}
            }
        }
    }
```

**Test plans and executions**:
```python
@pytest.fixture
def test_plan():
    """Test plan with budget."""
    return Plan.objects.create(
        key="test-plan",
        reserved_micro=100000,
        spent_micro=0
    )
```

### Database State

**Transaction isolation**:
```python
@pytest.mark.django_db
def test_with_database():
    """Test requiring database access."""
    # Automatic transaction rollback after test
```

**Persistent state** (use sparingly):
```python
@pytest.mark.django_db(transaction=True)
def test_with_transactions():
    """Test requiring transaction control."""
    # Manual state cleanup required
```

## Performance Testing

### Test Execution Benchmarks

Monitor test suite performance:

```python
@pytest.mark.unit
def test_adapter_performance():
    """Adapter calls complete within reasonable time."""
    start = time.time()
    
    result = mock_adapter.invoke(...)
    
    duration = time.time() - start
    assert duration < 1.0  # Unit tests should be fast
```

### Memory Usage

```python
@pytest.mark.integration
def test_memory_usage():
    """Large processor outputs don't cause memory issues."""
    # Test with large files, streaming, etc.
```

## Error Testing

### Error Code Consistency

Test that error codes are consistent across adapters:

```python
@pytest.mark.unit
@pytest.mark.parametrize("adapter_class", [LocalAdapter, MockAdapter, ModalAdapter])
def test_error_codes(adapter_class):
    """Error codes are consistent across adapters."""
    adapter = adapter_class()
    
    # Test missing secret error
    result = adapter.invoke(
        processor_ref="llm/litellm@1",
        inputs_json={},
        write_prefix="/artifacts/outputs/",
        execution_id="test",
        registry_snapshot=get_test_registry(),
        adapter_opts={},
        secrets_present=[]  # Missing required secrets
    )
    
    assert result["status"] == "error"
    assert result["error"]["code"] == "ERR_MISSING_SECRET"
```

### WorldPath Error Handling

```python
@pytest.mark.unit
def test_worldpath_error_codes():
    """WorldPath canonicalization returns proper error codes."""
    test_cases = [
        ("/artifacts/../other", "ERR_DOT_SEGMENTS"),
        ("/invalid/path", "ERR_BAD_FACET"),
        ("/artifacts/test%2Fpath", "ERR_DECODED_SLASH"),
    ]
    
    for path, expected_error in test_cases:
        canonical, error = canonicalize_worldpath(path)
        assert error == expected_error
```

## Integration with CI

### Test Selection Strategy

**Pull Requests**: Fast feedback with unit tests
```yaml
# .github/workflows/ci-cd.yml
- name: Run unit tests
  run: pytest -q -m "unit and not integration and not requires_postgres"
```

**Main Branch**: Complete validation
```yaml
- name: Run all tests
  run: |
    DJANGO_SETTINGS_MODULE=backend.settings.test pytest -q
  env:
    ENABLE_INTEGRATION_TESTS: "1"
```

### Test Coverage

Monitor coverage for critical paths:
```bash
pytest --cov=apps.core.adapters --cov-report=html
```

## Test Organization

### Directory Structure

```
code/
├── apps/
│   ├── core/
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_adapters.py
│   │       ├── test_worldpath.py
│   │       └── integration/
│   │           └── test_modal_adapter.py
│   ├── ledger/
│   │   └── tests.py
│   └── runtime/
│       └── tests/
│           └── test_determinism_receipts.py
└── tests/
    ├── acceptance/
    │   ├── test_ledger_acceptance.py
    │   └── test_determinism_settle.py
    └── property/
        └── test_budget_never_negative.py
```

### Naming Conventions

- **Unit tests**: `test_<component>.py`
- **Integration tests**: `test_<component>_integration.py` or `integration/test_<component>.py`
- **Acceptance tests**: `tests/acceptance/test_<feature>.py`
- **Property tests**: `tests/property/test_<property>.py`

## Cross-References

- {doc}`../concepts/adapters` - Adapter interface testing requirements
- {doc}`../concepts/worldpath` - Path canonicalization test cases
- {doc}`../runbooks/ci-cd` - CI/CD pipeline test execution
- [ADR-0015: Local Adapter Docker Execution](../adr/ADR-0015-local-adapter-docker-execution.md) - Testing considerations for Docker execution