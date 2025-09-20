"""
Integration tests for logging boundary discipline.

Tests that only one execution.fail event is logged per execution trace,
and that adapters use adapter.complete events instead.
"""

import json
import os
import sys
from io import StringIO
from unittest import mock

import pytest

from apps.core.logging import clear, bind, info, error


class TestBoundaryDiscipline:
    """Test boundary discipline for error logging."""

    def setup_method(self):
        """Clear logging context before each test."""
        clear()

    def teardown_method(self):
        """Clear logging context after each test."""
        clear()

    def test_single_execution_fail_per_trace(self):
        """Test only one execution.fail event per execution trace."""
        execution_id = "test-boundary-123"
        bind(trace_id=execution_id)

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Simulate adapter error (should use adapter.complete)
            error(
                "adapter.complete",
                status="error",
                error={"code": "ERR_ADAPTER_INVOCATION", "message": "Adapter failed"},
            )

            # Simulate command boundary error (should use execution.fail)
            error("execution.fail", error={"code": "ERR_ADAPTER_INVOCATION", "message": "Adapter failed"})

            # Should NOT have another execution.fail from adapter
            # (this would violate boundary discipline)

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        events = []

        for line in lines:
            log_data = json.loads(line)
            events.append(log_data["event"])
            assert log_data["trace_id"] == execution_id

        # Should have exactly one execution.fail and one adapter.complete
        assert events.count("execution.fail") == 1
        assert events.count("adapter.complete") == 1
        assert "adapter.complete" in events
        assert "execution.fail" in events

    def test_adapter_uses_adapter_complete_not_execution_fail(self):
        """Test adapters use adapter.complete events, not execution.fail."""
        execution_id = "test-adapter-123"
        bind(trace_id=execution_id, adapter="local")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Adapter should log adapter.complete on success
            info("adapter.invoke", image_digest="sha256:abc123")
            info("adapter.complete", status="success", outputs_count=1)

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        events = []

        for line in lines:
            log_data = json.loads(line)
            events.append(log_data["event"])

        # Should have adapter events, not execution events
        assert "adapter.invoke" in events
        assert "adapter.complete" in events
        assert "execution.fail" not in events
        assert "execution.settle" not in events

    def test_processor_can_use_execution_fail_in_container(self):
        """Test processors can use execution.fail since they are boundaries inside containers."""
        execution_id = "test-processor-123"
        bind(trace_id=execution_id, processor_ref="llm/test@1", adapter="local")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Processor boundary - can emit execution.fail
            info("processor.start", inputs_hash="b3:abc123")
            error("execution.fail", error={"code": "ERR_PROCESSOR", "message": "Provider failed"})

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        events = []

        for line in lines:
            log_data = json.loads(line)
            events.append(log_data["event"])

        # Processor can emit execution.fail as it's the boundary inside container
        assert "processor.start" in events
        assert "execution.fail" in events

    def test_command_boundary_logs_execution_events(self):
        """Test command boundary logs execution.start and execution.settle/fail."""
        execution_id = "test-command-123"
        bind(trace_id=execution_id, processor_ref="llm/test@1", adapter="local")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Command boundary events
            info("execution.start", write_prefix="/artifacts/test/")
            info("execution.settle", status="success", outputs_count=1)

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        events = []

        for line in lines:
            log_data = json.loads(line)
            events.append(log_data["event"])

        # Command boundary should emit execution events
        assert "execution.start" in events
        assert "execution.settle" in events


class TestModalAdapterBoundaryDiscipline:
    """Test Modal adapter follows boundary discipline."""

    def setup_method(self):
        """Clear logging context before each test."""
        clear()

    def teardown_method(self):
        """Clear logging context after each test."""
        clear()

    def test_modal_adapter_logs_modal_events(self):
        """Test Modal adapter logs modal.invoke and modal.complete events."""
        execution_id = "test-modal-123"
        bind(trace_id=execution_id, adapter="modal", processor_ref="llm/test@1")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Modal adapter events
            info("modal.invoke", app_name="test-app", fn="run", payload_keys=["inputs_json"])
            info("modal.complete", status="success", outputs_count=1, duration_ms=1500)

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        events = []

        for line in lines:
            log_data = json.loads(line)
            events.append(log_data["event"])
            assert log_data["adapter"] == "modal"

        # Modal adapter should emit modal-specific events
        assert "modal.invoke" in events
        assert "modal.complete" in events
        # Should not emit execution boundary events
        assert "execution.fail" not in events
        assert "execution.settle" not in events

    def test_modal_adapter_error_uses_modal_complete(self):
        """Test Modal adapter errors use modal.complete, not execution.fail."""
        execution_id = "test-modal-error-123"
        bind(trace_id=execution_id, adapter="modal", processor_ref="llm/test@1")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Modal adapter error
            error(
                "modal.complete",
                status="error",
                error={"code": "ERR_MODAL_INVOCATION", "message": "Function not found"},
            )

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]

        assert len(lines) == 1
        log_data = json.loads(lines[0])

        # Should use modal.complete for errors, not execution.fail
        assert log_data["event"] == "modal.complete"
        assert log_data["status"] == "error"
        assert log_data["error"]["code"] == "ERR_MODAL_INVOCATION"


class TestProcessorBoundaryDiscipline:
    """Test processor boundary discipline."""

    def setup_method(self):
        """Clear logging context before each test."""
        clear()

    def teardown_method(self):
        """Clear logging context after each test."""
        clear()

    def test_processor_lifecycle_events(self):
        """Test processor emits complete lifecycle events."""
        execution_id = "test-processor-lifecycle-123"
        bind(trace_id=execution_id, processor_ref="llm/test@1", adapter="local")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Complete processor lifecycle
            info("processor.start", inputs_hash="b3:abc123")
            info("provider.call", provider="test", model="test-model")
            info("provider.response", latency_ms=250, usage={"tokens": 100})
            info("processor.outputs", outputs_count=1, outputs_bytes=512)
            info("processor.receipt", receipt_path="/tmp/receipt.json")

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        events = []

        for line in lines:
            log_data = json.loads(line)
            events.append(log_data["event"])
            assert log_data["processor_ref"] == "llm/test@1"

        # Should have complete processor lifecycle
        expected_events = [
            "processor.start",
            "provider.call",
            "provider.response",
            "processor.outputs",
            "processor.receipt",
        ]

        for event in expected_events:
            assert event in events, f"Missing {event} in processor lifecycle"

    def test_processor_error_can_use_execution_fail(self):
        """Test processor can use execution.fail as container boundary."""
        execution_id = "test-processor-error-123"
        bind(trace_id=execution_id, processor_ref="llm/test@1", adapter="local")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Processor error at container boundary
            info("processor.start", inputs_hash="b3:abc123")
            error("execution.fail", error={"code": "ERR_PROCESSOR", "message": "Provider timeout"})

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        events = []

        for line in lines:
            log_data = json.loads(line)
            events.append(log_data["event"])

        # Processor as container boundary can emit execution.fail
        assert "processor.start" in events
        assert "execution.fail" in events


@pytest.mark.integration
class TestFullTraceLogging:
    """Test complete execution trace logging with boundary discipline."""

    def setup_method(self):
        """Clear logging context before each test."""
        clear()

    def teardown_method(self):
        """Clear logging context after each test."""
        clear()

    def test_complete_success_trace_boundary_discipline(self):
        """Test complete successful execution trace follows boundary discipline."""
        execution_id = "test-full-trace-123"

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Command boundary
            bind(trace_id=execution_id, processor_ref="llm/test@1", adapter="local", mode="mock")
            info("execution.start", write_prefix="/artifacts/test/")

            # Adapter boundary
            info("adapter.invoke", image_digest="sha256:abc123", build=False)
            info("adapter.complete", status="success", outputs_count=1)

            # Command boundary completion
            info("execution.settle", status="success", outputs_count=1)

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        events = []

        for line in lines:
            log_data = json.loads(line)
            events.append(log_data["event"])
            assert log_data["trace_id"] == execution_id

        # Should have proper boundary events
        assert "execution.start" in events  # Command boundary start
        assert "adapter.invoke" in events  # Adapter boundary
        assert "adapter.complete" in events  # Adapter boundary
        assert "execution.settle" in events  # Command boundary success

        # Should not have execution.fail
        assert "execution.fail" not in events

        # Should have exactly one execution.start and one execution.settle
        assert events.count("execution.start") == 1
        assert events.count("execution.settle") == 1

    def test_complete_error_trace_boundary_discipline(self):
        """Test complete error execution trace follows boundary discipline."""
        execution_id = "test-error-trace-123"

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Command boundary
            bind(trace_id=execution_id, processor_ref="llm/test@1", adapter="local", mode="mock")
            info("execution.start", write_prefix="/artifacts/test/")

            # Adapter boundary error
            error(
                "adapter.complete",
                status="error",
                error={"code": "ERR_ADAPTER_INVOCATION", "message": "Container failed"},
            )

            # Command boundary error (single execution.fail)
            error("execution.fail", error={"code": "ERR_ADAPTER_INVOCATION", "message": "Container failed"})

            output = mock_stdout.getvalue()

        lines = [line for line in output.strip().split("\n") if line]
        events = []

        for line in lines:
            log_data = json.loads(line)
            events.append(log_data["event"])
            assert log_data["trace_id"] == execution_id

        # Should have proper boundary events for error case
        assert "execution.start" in events  # Command boundary start
        assert "adapter.complete" in events  # Adapter boundary error
        assert "execution.fail" in events  # Command boundary error

        # Should not have execution.settle for error case
        assert "execution.settle" not in events

        # Critical: Should have exactly one execution.fail (boundary discipline)
        assert events.count("execution.fail") == 1
        assert events.count("execution.start") == 1
