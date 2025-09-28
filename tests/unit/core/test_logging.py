"""
Unit tests for apps.core.logging module.

Tests redaction patterns, context binding, and JSON formatting.
"""

import json
import os
import sys
from io import StringIO
from unittest import mock

import pytest

from apps.core.logging import _redact, bind, clear, log, info, error, debug, _sample


class TestRedactionPatterns:
    """Test secret redaction patterns."""

    def test_api_key_redaction(self):
        """Test API key patterns are redacted."""
        text = "API_KEY=sk-1234567890abcdef"
        result = _redact(text)
        assert "[REDACTED]" in result
        assert "sk-1234567890abcdef" not in result

    def test_bearer_token_redaction(self):
        """Test Bearer token patterns are redacted."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"
        result = _redact(text)
        assert "[REDACTED]" in result
        assert "eyJhbGciOiJIUzI1NiJ9" not in result

    def test_url_credentials_redaction(self):
        """Test URL credentials are redacted."""
        text = "https://user:pass@example.com/api"
        result = _redact(text)
        assert "[REDACTED]" in result
        assert "user:pass" not in result

    def test_hex_token_redaction(self):
        """Test long hex tokens are redacted."""
        text = "secret=1234567890abcdef1234567890abcdef"
        result = _redact(text)
        assert "[REDACTED]" in result
        assert "1234567890abcdef1234567890abcdef" not in result

    def test_safe_text_not_redacted(self):
        """Test normal text is not redacted."""
        text = "This is normal log message"
        result = _redact(text)
        assert result == text
        assert "[REDACTED]" not in result


class TestContextBinding:
    """Test context variable binding and clearing."""

    def setup_method(self):
        """Clear context before each test."""
        clear()

    def teardown_method(self):
        """Clear context after each test."""
        clear()

    def test_bind_updates_context(self, logs_to_stdout):
        """Test bind adds fields to context."""
        bind(trace_id="test-123", processor_ref="llm/test@1")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            info("test.event", custom_field="value")
            output = mock_stdout.getvalue()

        log_data = json.loads(output)
        assert log_data["trace_id"] == "test-123"
        assert log_data["processor_ref"] == "llm/test@1"
        assert log_data["custom_field"] == "value"

    def test_clear_removes_context(self, logs_to_stdout):
        """Test clear removes all context."""
        bind(trace_id="test-123")
        clear()

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            info("test.event")
            output = mock_stdout.getvalue()

        log_data = json.loads(output)
        assert "trace_id" not in log_data

    def test_bind_none_values_ignored(self, logs_to_stdout):
        """Test None values are ignored in bind."""
        bind(trace_id="test-123", empty_field=None)

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            info("test.event")
            output = mock_stdout.getvalue()

        log_data = json.loads(output)
        assert log_data["trace_id"] == "test-123"
        assert "empty_field" not in log_data


class TestLogFormatting:
    """Test log output formatting."""

    def setup_method(self):
        """Clear context before each test."""
        clear()

    def teardown_method(self):
        """Clear context after each test."""
        clear()

    @mock.patch.dict(os.environ, {"JSON_LOGS": "1"})
    def test_json_output_format(self, logs_to_stdout):
        """Test JSON log output format."""
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            info("test.event", field="value")
            output = mock_stdout.getvalue().strip()

        # Should be valid JSON
        log_data = json.loads(output)
        assert log_data["level"] == "info"
        assert log_data["event"] == "test.event"
        assert log_data["field"] == "value"
        assert "ts" in log_data
        assert "service" in log_data

    @mock.patch.dict(os.environ, {"JSON_LOGS": "0"})
    def test_pretty_output_format(self, logs_to_stdout):
        """Test pretty log output format for development."""
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            info("test.event", field="value")
            output = mock_stdout.getvalue().strip()

        assert output.startswith("[INFO] test.event")
        assert "field=value" in output

    def test_field_truncation(self, logs_to_stdout):
        """Test long fields are truncated."""
        long_text = "x" * 3000  # Over 2000 char limit

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            info("test.event", long_field=long_text)
            output = mock_stdout.getvalue()

        log_data = json.loads(output)
        assert len(log_data["long_field"]) == 2000

    def test_redaction_applied_to_fields(self, logs_to_stdout):
        """Test redaction is applied to string fields."""
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            info("test.event", secret="API_KEY=sk-1234567890abcdef")
            output = mock_stdout.getvalue()

        log_data = json.loads(output)
        assert "[REDACTED]" in log_data["secret"]
        assert "sk-1234567890abcdef" not in log_data["secret"]


class TestSampling:
    """Test log sampling functionality."""

    def test_sample_with_zero_rate(self):
        """Test sampling with 0.0 rate never samples."""
        for _ in range(100):
            assert not _sample("NONEXISTENT_VAR", 0.0)

    def test_sample_with_full_rate(self):
        """Test sampling with 1.0 rate always samples."""
        for _ in range(100):
            assert _sample("NONEXISTENT_VAR", 1.0)

    @mock.patch.dict(os.environ, {"TEST_SAMPLE_RATE": "0.5"})
    def test_sample_from_environment(self):
        """Test sampling rate from environment variable."""
        # With 50% rate, should get some True and some False over many trials
        results = [_sample("TEST_SAMPLE_RATE") for _ in range(1000)]
        true_count = sum(results)
        # Should be roughly 50% (allow for randomness)
        assert 400 < true_count < 600

    def test_debug_sampling(self):
        """Test debug logs respect LOG_SAMPLE_DEBUG."""
        with mock.patch.dict(os.environ, {"LOG_SAMPLE_DEBUG": "0.0"}):
            with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                debug("test.debug", field="value")
                output = mock_stdout.getvalue()

        # Should be empty due to 0% sampling
        assert output == ""


class TestErrorHandling:
    """Test error handling in logging."""

    def setup_method(self):
        """Clear context before each test."""
        clear()

    def teardown_method(self):
        """Clear context after each test."""
        clear()

    def test_json_encoding_with_valid_types(self, logs_to_stdout):
        """Test logging handles all valid JSON types correctly."""
        valid_data = {
            "string": "test",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null_value": None,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
        }

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            info("test.event", **valid_data)
            output = mock_stdout.getvalue()

        log_data = json.loads(output)
        for key, value in valid_data.items():
            assert log_data[key] == value


@pytest.mark.integration
class TestLoggingIntegration:
    """Integration tests for logging with other components."""

    def setup_method(self):
        """Clear context before each test."""
        clear()

    def teardown_method(self):
        """Clear context after each test."""
        clear()

    def test_execution_trace_logging(self, logs_to_stdout):
        """Test logging throughout an execution trace."""
        execution_id = "test-exec-123"

        # Simulate full execution trace
        bind(trace_id=execution_id, processor_ref="llm/test@1", adapter="local", mode="mock")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            info("execution.start", write_prefix="/artifacts/test/")
            info("adapter.invoke", image_digest="sha256:abc123")
            info("processor.start", inputs_hash="b3:def456")
            info("provider.call", provider="test", model="test-model")
            info("provider.response", latency_ms=100, usage={"tokens": 50})
            info("processor.outputs", outputs_count=1, outputs_bytes=256)
            info("processor.receipt", receipt_path="/artifacts/test/receipt.json")
            info("adapter.complete", status="success", outputs_count=1)
            info("execution.settle", status="success", outputs_count=1)

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        assert len(lines) == 9

        # All lines should have same trace_id
        for line in lines:
            log_data = json.loads(line)
            assert log_data["trace_id"] == execution_id
            assert log_data["processor_ref"] == "llm/test@1"
            assert log_data["adapter"] == "local"
            assert log_data["mode"] == "mock"
