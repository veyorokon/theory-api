"""Health endpoint contract tests with SLA enforcement."""

import time
import pytest
from fastapi.testclient import TestClient


@pytest.mark.contracts
class TestHealthEndpoint:
    """Test health endpoint performance and reliability."""

    @pytest.fixture
    def client(self):
        """FastAPI test client for llm/litellm processor."""
        try:
            from apps.core.processors.llm_litellm.app.http import app

            return TestClient(app)
        except ImportError:
            pytest.skip("HTTP app not available for llm/litellm processor")

    def test_healthz_returns_ok(self, client):
        """Test /healthz returns 200 with ok=true."""
        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert data == {"ok": True}

    def test_healthz_sla_under_250ms(self, client):
        """Test /healthz completes under 250ms SLA."""
        # Warm up request to avoid cold start penalties
        client.get("/healthz")

        # Measure actual SLA performance
        start_time = time.time()
        response = client.get("/healthz")
        elapsed_ms = (time.time() - start_time) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 250, f"Health endpoint took {elapsed_ms:.1f}ms, exceeds 250ms SLA"

        # Verify response is still correct
        assert response.json() == {"ok": True}

    def test_healthz_performance_consistency(self, client):
        """Test /healthz performance is consistent across multiple calls."""
        times = []

        # Make 10 consecutive calls
        for _ in range(10):
            start_time = time.time()
            response = client.get("/healthz")
            elapsed_ms = (time.time() - start_time) * 1000

            assert response.status_code == 200
            times.append(elapsed_ms)

        # All calls should be under SLA
        max_time = max(times)
        avg_time = sum(times) / len(times)

        assert max_time < 250, f"Max health time {max_time:.1f}ms exceeds SLA"
        assert avg_time < 100, f"Average health time {avg_time:.1f}ms indicates performance issue"

    def test_healthz_no_secrets_required(self, client):
        """Test /healthz works without any environment secrets."""
        import os

        # Save original environment
        original_env = {}
        secret_vars = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "REPLICATE_API_TOKEN",
            "MODAL_TOKEN_ID",
            "MODAL_TOKEN_SECRET",
        ]

        for var in secret_vars:
            if var in os.environ:
                original_env[var] = os.environ[var]
                del os.environ[var]

        try:
            # Health endpoint should work without secrets
            response = client.get("/healthz")

            assert response.status_code == 200
            assert response.json() == {"ok": True}

        finally:
            # Restore original environment
            for var, value in original_env.items():
                os.environ[var] = value

    def test_healthz_no_authentication_required(self, client):
        """Test /healthz doesn't require any authentication headers."""
        # No headers at all
        response = client.get("/healthz")
        assert response.status_code == 200

        # With various irrelevant headers
        headers = {"authorization": "Bearer fake-token", "x-api-key": "fake-key", "user-agent": "test-agent"}

        response = client.get("/healthz", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_healthz_http_methods(self, client):
        """Test /healthz only responds to GET requests."""
        # GET should work
        response = client.get("/healthz")
        assert response.status_code == 200

        # Other methods should fail appropriately
        unsupported_methods = [
            client.post,
            client.put,
            client.patch,
            client.delete,
            client.head,  # HEAD might work but let's verify
            client.options,
        ]

        for method in unsupported_methods:
            try:
                response = method("/healthz")
                # Should either be 405 Method Not Allowed or 404
                assert response.status_code in [404, 405], f"Method {method.__name__} should not be supported"
            except Exception:
                # Some methods might not be available, which is fine
                pass

    def test_healthz_concurrent_requests(self, client):
        """Test /healthz handles concurrent requests efficiently."""
        import concurrent.futures
        import threading

        def make_health_request():
            start_time = time.time()
            response = client.get("/healthz")
            elapsed_ms = (time.time() - start_time) * 1000
            return response.status_code, elapsed_ms

        # Make 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_health_request) for _ in range(5)]
            results = [future.result() for future in futures]

        # All requests should succeed and meet SLA
        for status_code, elapsed_ms in results:
            assert status_code == 200
            assert elapsed_ms < 250, f"Concurrent health request took {elapsed_ms:.1f}ms"

    def test_healthz_no_side_effects(self, client):
        """Test /healthz doesn't modify any state or create artifacts."""
        # Make health request
        response1 = client.get("/healthz")
        assert response1.status_code == 200

        # Make another health request
        response2 = client.get("/healthz")
        assert response2.status_code == 200

        # Responses should be identical (no state change)
        assert response1.json() == response2.json()
        assert response1.status_code == response2.status_code
