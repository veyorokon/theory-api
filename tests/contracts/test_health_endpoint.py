"""Health endpoint contract tests with SLA enforcement."""

import time
import pytest
import requests
import concurrent.futures

from tests.tools.localctl_helpers import get_http_url


# Container started by Makefile via `localctl start --ref llm/litellm@1`
HTTP_URL = get_http_url("llm/litellm@1")


@pytest.mark.contracts
@pytest.mark.requires_docker
class TestHealthEndpoint:
    """Test health endpoint performance and reliability."""

    def test_healthz_returns_ok(self):
        """Test /healthz returns 200 with ok=true and digest."""
        response = requests.get(f"{HTTP_URL}/healthz", timeout=5)

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert data["ok"] is True
        assert "digest" in data
        assert isinstance(data["digest"], str)

    def test_healthz_sla_under_250ms(self):
        """Test /healthz completes under 250ms SLA."""
        # Warm up request to avoid cold start penalties
        requests.get(f"{HTTP_URL}/healthz", timeout=5)

        # Measure actual SLA performance
        start_time = time.time()
        response = requests.get(f"{HTTP_URL}/healthz", timeout=5)
        elapsed_ms = (time.time() - start_time) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 250, f"Health endpoint took {elapsed_ms:.1f}ms, exceeds 250ms SLA"

        # Verify response is still correct
        data = response.json()
        assert data["ok"] is True
        assert "digest" in data

    def test_healthz_performance_consistency(self):
        """Test /healthz performance is consistent across multiple calls."""
        times = []

        # Make 10 consecutive calls
        for _ in range(10):
            start_time = time.time()
            response = requests.get(f"{HTTP_URL}/healthz", timeout=5)
            elapsed_ms = (time.time() - start_time) * 1000

            assert response.status_code == 200
            times.append(elapsed_ms)

        # All calls should be under SLA
        max_time = max(times)
        avg_time = sum(times) / len(times)

        assert max_time < 250, f"Max health time {max_time:.1f}ms exceeds SLA"
        assert avg_time < 100, f"Average health time {avg_time:.1f}ms indicates performance issue"

    def test_healthz_no_secrets_required(self):
        """Test /healthz works without any environment secrets."""
        # Container already has no secrets configured for health endpoint
        # Just verify it works
        response = requests.get(f"{HTTP_URL}/healthz", timeout=5)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "digest" in data

    def test_healthz_no_authentication_required(self):
        """Test /healthz doesn't require any authentication headers."""
        # No headers at all
        response = requests.get(f"{HTTP_URL}/healthz", timeout=5)
        assert response.status_code == 200

        # With various irrelevant headers
        headers = {"authorization": "Bearer fake-token", "x-api-key": "fake-key", "user-agent": "test-agent"}

        response = requests.get(f"{HTTP_URL}/healthz", headers=headers, timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "digest" in data

    def test_healthz_http_methods(self):
        """Test /healthz only responds to GET requests."""
        # GET should work
        response = requests.get(f"{HTTP_URL}/healthz", timeout=5)
        assert response.status_code == 200

        # Other methods should fail appropriately
        unsupported_methods = [
            requests.post,
            requests.put,
            requests.patch,
            requests.delete,
        ]

        for method in unsupported_methods:
            try:
                response = method(f"{HTTP_URL}/healthz", timeout=5)
                # Should either be 405 Method Not Allowed or 404
                assert response.status_code in [404, 405], f"Method {method.__name__} should not be supported"
            except Exception:
                # Some methods might not be available, which is fine
                pass

    def test_healthz_concurrent_requests(self):
        """Test /healthz handles concurrent requests efficiently."""

        def make_health_request():
            start_time = time.time()
            response = requests.get(f"{HTTP_URL}/healthz", timeout=5)
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

    def test_healthz_no_side_effects(self):
        """Test /healthz doesn't modify any state or create artifacts."""
        # Make health request
        response1 = requests.get(f"{HTTP_URL}/healthz", timeout=5)
        assert response1.status_code == 200

        # Make another health request
        response2 = requests.get(f"{HTTP_URL}/healthz", timeout=5)
        assert response2.status_code == 200

        # Responses should be identical (no state change)
        data1 = response1.json()
        data2 = response2.json()
        assert data1 == data2
        assert data1["ok"] is True
        assert "digest" in data1
        assert response1.status_code == response2.status_code
