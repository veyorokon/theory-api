"""
Integration tests for Modal payload validation and logging.

Tests that Modal functions validate payloads and log appropriate events.
"""

import json
import sys
import tempfile
import tarfile
from io import StringIO, BytesIO
from pathlib import Path
from unittest import mock

import pytest

# Import Modal app functions for testing
# Note: This requires Modal SDK to be available
try:
    from modal_app import run, smoke, _log, _err

    MODAL_AVAILABLE = True
except (ImportError, RuntimeError):
    MODAL_AVAILABLE = False


@pytest.mark.skipif(not MODAL_AVAILABLE, reason="Modal SDK not available")
class TestModalPayloadValidation:
    """Test Modal function payload validation."""

    def test_run_function_invalid_payload_type(self):
        """Test run function rejects non-dict payloads."""
        with mock.patch("builtins.print") as mock_print:
            result = run("invalid payload")

        # Should return error tarball
        assert isinstance(result, bytes)

        # Should have logged invoke.payload.invalid
        mock_print.assert_called()
        log_calls = [call[0][0] for call in mock_print.call_args_list]

        payload_invalid_logged = False
        for call in log_calls:
            try:
                log_data = json.loads(call)
                if log_data.get("event") == "invoke.payload.invalid":
                    assert log_data["got_type"] == "str"
                    payload_invalid_logged = True
                    break
            except json.JSONDecodeError:
                continue

        assert payload_invalid_logged, "Should have logged invoke.payload.invalid"

        # Extract and check error from tarball
        with tarfile.open(fileobj=BytesIO(result), mode="r:gz") as tar:
            # Should contain error status
            members = tar.getnames()
            assert any("status.json" in member for member in members)

    def test_run_function_missing_required_keys(self):
        """Test run function rejects payloads missing required keys."""
        payload = {"mode": "mock"}  # Missing inputs_json and write_prefix

        with mock.patch("builtins.print") as mock_print:
            result = run(payload)

        # Should return error tarball
        assert isinstance(result, bytes)

        # Should have logged invoke.payload.missing
        mock_print.assert_called()
        log_calls = [call[0][0] for call in mock_print.call_args_list]

        payload_missing_logged = False
        for call in log_calls:
            try:
                log_data = json.loads(call)
                if log_data.get("event") == "invoke.payload.missing":
                    missing_keys = log_data["missing"]
                    assert "inputs_json" in missing_keys
                    assert "write_prefix" in missing_keys
                    payload_missing_logged = True
                    break
            except json.JSONDecodeError:
                continue

        assert payload_missing_logged, "Should have logged invoke.payload.missing"

    def test_smoke_function_invalid_payload_type(self):
        """Test smoke function rejects non-dict payloads."""
        with mock.patch("builtins.print") as mock_print:
            result = smoke(42)  # Invalid number payload

        # Should return error tarball
        assert isinstance(result, bytes)

        # Should have logged invoke.payload.invalid
        mock_print.assert_called()
        log_calls = [call[0][0] for call in mock_print.call_args_list]

        payload_invalid_logged = False
        for call in log_calls:
            try:
                log_data = json.loads(call)
                if log_data.get("event") == "invoke.payload.invalid":
                    assert log_data["got_type"] == "int"
                    payload_invalid_logged = True
                    break
            except json.JSONDecodeError:
                continue

        assert payload_invalid_logged, "Should have logged invoke.payload.invalid"

    def test_smoke_function_missing_required_keys(self):
        """Test smoke function rejects payloads missing required keys."""
        payload = {}  # Empty payload missing required keys

        with mock.patch("builtins.print") as mock_print:
            result = smoke(payload)

        # Should return error tarball
        assert isinstance(result, bytes)

        # Should have logged invoke.payload.missing
        mock_print.assert_called()
        log_calls = [call[0][0] for call in mock_print.call_args_list]

        payload_missing_logged = False
        for call in log_calls:
            try:
                log_data = json.loads(call)
                if log_data.get("event") == "invoke.payload.missing":
                    missing_keys = log_data["missing"]
                    assert "inputs_json" in missing_keys
                    assert "write_prefix" in missing_keys
                    payload_missing_logged = True
                    break
            except json.JSONDecodeError:
                continue

        assert payload_missing_logged, "Should have logged invoke.payload.missing"

    def test_smoke_function_forces_mock_mode(self):
        """Test smoke function forces mode=mock and logs it."""
        payload = {
            "inputs_json": {"schema": "v1"},
            "write_prefix": "/tmp/test/",
            "mode": "real",  # Should be overridden to mock
        }

        with mock.patch("builtins.print") as mock_print:
            with mock.patch("modal_app._invoke_processor") as mock_invoke:
                # Mock successful processor execution
                mock_invoke.return_value = b"fake_tarball"

                result = smoke(payload)

        # Should have called _invoke_processor with mode=mock
        mock_invoke.assert_called_once()
        called_payload = mock_invoke.call_args[0][0]
        assert called_payload["mode"] == "mock"

        # Should have logged mock.exec with forced=True
        mock_print.assert_called()
        log_calls = [call[0][0] for call in mock_print.call_args_list]

        mock_exec_logged = False
        for call in log_calls:
            try:
                log_data = json.loads(call)
                if log_data.get("event") == "mock.exec":
                    assert log_data["forced"] is True
                    mock_exec_logged = True
                    break
            except json.JSONDecodeError:
                continue

        assert mock_exec_logged, "Should have logged mock.exec with forced=True"


@pytest.mark.skipif(not MODAL_AVAILABLE, reason="Modal SDK not available")
class TestModalErrorHelpers:
    """Test Modal app error helper functions."""

    def test_err_function_returns_canonical_error(self):
        """Test _err function returns canonical error envelope as tarball."""
        result = _err("ERR_TEST", "Test error message")

        assert isinstance(result, bytes)

        # Extract and verify error envelope structure
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(result)
            tmp.flush()

            with tarfile.open(tmp.name, "r:gz") as tar:
                members = tar.getnames()
                assert any("status.json" in member for member in members)

                # Extract status.json and verify structure
                for member in tar.getmembers():
                    if "status.json" in member.name:
                        f = tar.extractfile(member)
                        status_data = json.loads(f.read().decode("utf-8"))

                        assert status_data["status"] == "error"
                        assert status_data["error"]["code"] == "ERR_TEST"
                        assert status_data["error"]["message"] == "Test error message"
                        assert status_data["meta"]["env_fingerprint"] == "adapter=modal"
                        break

    def test_log_function_structured_output(self):
        """Test _log function produces structured JSON output."""
        with mock.patch("builtins.print") as mock_print:
            _log("test.event", field1="value1", field2=42)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]

        log_data = json.loads(output)
        assert log_data["event"] == "test.event"
        assert log_data["field1"] == "value1"
        assert log_data["field2"] == 42
        assert log_data["level"] == "info"
        assert "ts" in log_data

    def test_log_function_handles_json_errors(self):
        """Test _log function falls back gracefully on JSON errors."""

        # Create an object that can't be JSON serialized
        class UnserializableObject:
            pass

        obj = UnserializableObject()

        with mock.patch("builtins.print") as mock_print:
            with mock.patch("json.dumps", side_effect=TypeError("not serializable")):
                _log("test.event", bad_obj=obj)

        # Should have printed fallback format
        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        assert "[test.event]" in output


@pytest.mark.integration
@pytest.mark.skipif(not MODAL_AVAILABLE, reason="Modal SDK not available")
class TestModalAppBoundaryDiscipline:
    """Test Modal app follows boundary discipline for error logging."""

    def test_modal_functions_log_execution_boundaries(self):
        """Test Modal functions log at execution boundaries only."""
        payload = {"inputs_json": {"schema": "v1"}, "write_prefix": "/tmp/test/", "mode": "mock"}

        with mock.patch("builtins.print") as mock_print:
            with mock.patch("modal_app._invoke_processor") as mock_invoke:
                # Mock successful processor execution
                mock_invoke.return_value = b"fake_tarball"

                result = run(payload)

        # Should have logged processor.exec.start and processor.exec.complete
        log_calls = [call[0][0] for call in mock_print.call_args_list]

        events_logged = []
        for call in log_calls:
            try:
                log_data = json.loads(call)
                events_logged.append(log_data.get("event"))
            except json.JSONDecodeError:
                continue

        assert "processor.exec.start" in events_logged
        assert "processor.exec.complete" in events_logged

        # Should not log multiple execution.fail events (boundary discipline)
        execution_fail_count = events_logged.count("execution.fail")
        assert execution_fail_count <= 1, "Should not log multiple execution.fail events"
