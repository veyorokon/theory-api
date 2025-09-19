"""
Replicate provider runners.

Provides both real and mock implementations for Replicate API.
"""

import os
from typing import Dict, Any
from apps.core.integrations.secret_resolver import resolve_secret


class ReplicateRunner:
    """Real Replicate API runner."""

    def __init__(self, api_token: str, timeout_s: int = 120):
        """
        Initialize Replicate runner.

        Args:
            api_token: Replicate API token
            timeout_s: Request timeout in seconds
        """
        self._timeout_s = timeout_s

        # Lazy import to avoid dependency issues
        try:
            import replicate as _rep
        except ImportError as e:
            raise RuntimeError(
                "ERR_DEP_MISSING: 'replicate' package not installed. "
                "Install replicate>=0.25.0 or run with CI=true/SMOKE=true to use the mock."
            ) from e

        self._rep = _rep
        self.client = _rep.Client(api_token=api_token, timeout=timeout_s)

    def run(self, *, model: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run prediction on Replicate.

        Args:
            model: Model identifier (may include version)
            inputs: Input parameters

        Returns:
            Prediction output
        """
        # Strip version if present for API compatibility
        api_model = model.split(":")[0] if ":" in model else model

        # Run prediction
        prediction = self.client.predictions.create(model=api_model, input=inputs)

        # Wait for completion
        prediction.wait(interval=1)

        # Return output
        if prediction.status == "succeeded":
            return {"output": prediction.output, "status": "success"}
        else:
            return {"error": prediction.error, "status": "failed"}


class MockReplicateRunner:
    """Mock Replicate runner for CI/testing."""

    def __init__(self):
        """Initialize mock runner."""
        pass

    def run(self, *, model: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mock prediction run.

        Args:
            model: Model identifier
            inputs: Input parameters

        Returns:
            Mock output
        """
        # Return deterministic mock response
        return {"output": "Mock response for CI/testing", "status": "success", "model": model, "mock": True}


def select_replicate_runner(ci: bool = None, token_or_key: str = None):
    """
    Select Replicate runner based on environment.

    Args:
        ci: If True, use mock. If None, check CI/SMOKE env vars
        token_or_key: API token. If None, resolve from environment

    Returns:
        Callable runner matching ProviderRunner Protocol
    """
    from apps.core.integrations.types import ProcessorResult, OutputItem
    import json

    # Determine CI environment if not explicitly provided
    if ci is None:
        ci = os.getenv("CI") == "true" or os.getenv("SMOKE") == "true"

    if ci:
        # Return mock callable
        def mock_runner(inputs: dict) -> ProcessorResult:
            model = inputs.get("model", "unknown")
            # Create mock response
            text_output = f"Mock Replicate response for model: {model}"
            outputs = [
                OutputItem(relpath="outputs/result.txt", bytes_=text_output.encode("utf-8")),
                OutputItem(
                    relpath="outputs/response.json",
                    bytes_=json.dumps(
                        {"output": text_output, "status": "success", "model": model, "mock": True},
                        separators=(",", ":"),
                    ).encode("utf-8"),
                ),
            ]
            return ProcessorResult(
                outputs=outputs,
                processor_info=f"replicate-mock/{model}",
                usage={"predict_time": 0.1, "total_time": 0.1},
                extra={"mock": "true"},
            )

        return mock_runner

    # Resolve token if not provided
    if token_or_key is None:
        token_or_key = resolve_secret("REPLICATE_API_TOKEN")

    if not token_or_key:
        from apps.core.errors import ERR_SECRET_MISSING

        raise RuntimeError(f"{ERR_SECRET_MISSING}: REPLICATE_API_TOKEN required for Replicate")

    timeout = int(resolve_secret("REPLICATE_TIMEOUT_S") or "120")
    runner_instance = ReplicateRunner(api_token=token_or_key, timeout_s=timeout)

    # Return real callable that wraps the instance
    def real_runner(inputs: dict) -> ProcessorResult:
        model = inputs.get("model", "unknown")
        result = runner_instance.run(model=model, inputs=inputs)

        # Convert to ProcessorResult format
        outputs = []
        if isinstance(result, dict) and "output" in result:
            # Handle text output
            output_data = result["output"]
            if isinstance(output_data, str):
                outputs.append(OutputItem(relpath="outputs/result.txt", bytes_=output_data.encode("utf-8")))

        # Always include full response
        outputs.append(
            OutputItem(
                relpath="outputs/response.json", bytes_=json.dumps(result, separators=(",", ":")).encode("utf-8")
            )
        )

        # Extract usage
        usage = {}
        if isinstance(result, dict) and "metrics" in result:
            metrics = result["metrics"]
            usage = {
                "predict_time": float(metrics.get("predict_time", 0)),
                "total_time": float(metrics.get("total_time", 0)),
            }

        return ProcessorResult(
            outputs=outputs, processor_info=f"replicate/{model}", usage=usage, extra={"provider": "replicate"}
        )

    return real_runner
