"""Core processor execution logic."""

from __future__ import annotations
import datetime
import json
import logging
import sys
import uuid
from typing import Any, Dict, List

from django.db import transaction

from apps.plans.models import Plan
from apps.runtime.models import Transition, Execution
from apps.storage.artifact_store import artifact_store
from apps.runtime.determinism import write_determinism_receipt
from apps.runtime.services import settle_execution_success, settle_execution_failure
from apps.core.adapters.mock_adapter import MockAdapter
from apps.core.adapters.local_adapter import LocalAdapter
from apps.core.adapters.modal_adapter import ModalAdapter
from apps.core.registry.loader import snapshot_for_ref, get_secrets_present_for_spec
from apps.core.adapters.envelope import error_envelope
from apps.core.errors import ERR_PREFIX_TEMPLATE, ERR_ADAPTER_INVOCATION
from .paths import validate_write_prefix, PrefixError
from .receipts import build_receipt

logger = logging.getLogger(__name__)


def _get_adapter(adapter_name: str):
    """Get adapter instance by name."""
    adapters = {
        "local": LocalAdapter,
        "mock": MockAdapter,
        "modal": ModalAdapter,
    }
    if adapter_name not in adapters:
        raise ValueError(f"Unknown adapter: {adapter_name}")
    return adapters[adapter_name]()


def run_processor_core(
    *,
    ref: str,
    adapter: str,
    inputs_json: Dict[str, Any],
    write_prefix: str,
    plan: str | None = None,
    adapter_opts: Dict[str, Any] | None = None,
    build: bool = False,
    timeout: int | None = None,
    started_at: datetime.datetime | None = None,
) -> Dict[str, Any]:
    """
    Pure function: orchestrates one processor run and returns the envelope dict.
    No printing, no Django IO. Easy to unit-test.
    """
    if started_at is None:
        started_at = datetime.datetime.now(datetime.UTC)

    adapter_opts = adapter_opts or {}

    # Get or create plan if specified
    plan_obj = None
    execution = None
    if plan:
        plan_obj, created = Plan.objects.get_or_create(key=plan, defaults={"reserved_micro": 100000, "spent_micro": 0})

        # Create transition and execution
        with transaction.atomic():
            transition = Transition.objects.create(plan=plan_obj, key=f"run-{ref}", status="running")
            execution = Execution.objects.create(transition=transition, attempt_idx=1)

    try:
        # Load registry snapshot
        try:
            registry_snapshot = snapshot_for_ref(ref)
            spec = registry_snapshot["processors"][ref]
        except Exception as e:
            execution_id = str(execution.id) if execution else str(uuid.uuid4())
            logger.error("Registry loading failed", extra={"execution_id": execution_id, "ref": ref}, exc_info=True)
            return error_envelope(
                execution_id=execution_id,
                code=ERR_ADAPTER_INVOCATION,
                message=f"Failed to load registry for {ref}: {e}",
                env_fingerprint="registry_error",
            )

        # Get secrets present in environment
        secrets_present = get_secrets_present_for_spec(spec)

        # Get adapter
        try:
            adapter_instance = _get_adapter(adapter)
        except ValueError as e:
            execution_id = str(execution.id) if execution else str(uuid.uuid4())
            logger.error(
                "Adapter initialization failed", extra={"execution_id": execution_id, "adapter": adapter}, exc_info=True
            )
            return error_envelope(
                execution_id=execution_id,
                code=ERR_ADAPTER_INVOCATION,
                message=str(e),
                env_fingerprint="adapter_error",
            )

        # Generate execution_id
        execution_id = str(execution.id) if execution else str(uuid.uuid4())
        if execution:
            adapter_opts["execution_id"] = execution_id

        # Validate and expand write_prefix using secure validator
        try:
            write_prefix = validate_write_prefix(write_prefix, execution_id)
        except PrefixError as e:
            return error_envelope(
                execution_id=execution_id,
                code=ERR_PREFIX_TEMPLATE,
                message=str(e),
                env_fingerprint="prefix_validation_error",
                meta_extra={"write_prefix_template": write_prefix},
            )

        # Invoke processor with new keyword-only signature
        try:
            result = adapter_instance.invoke(
                processor_ref=ref,
                inputs_json=inputs_json,
                write_prefix=write_prefix,
                execution_id=execution_id,
                registry_snapshot=registry_snapshot,
                adapter_opts=adapter_opts,
                secrets_present=secrets_present,
            )
        except TypeError as te:
            # Adapter doesn't implement new signature
            result = error_envelope(
                execution_id=execution_id,
                code=ERR_ADAPTER_INVOCATION,
                message=f"Adapter {adapter} does not implement the new keyword-only signature: {te}",
                env_fingerprint=f"adapter={adapter}",
            )
        except Exception as e:
            logger.error(
                "Adapter invocation failed", extra={"execution_id": execution_id, "adapter": adapter}, exc_info=True
            )
            result = error_envelope(
                execution_id=execution_id,
                code=ERR_ADAPTER_INVOCATION,
                message=f"{e.__class__.__name__}: {e}",
                env_fingerprint=f"adapter={adapter}",
            )

        # Generate receipt for every run (success and error)
        finished_at = datetime.datetime.now(datetime.UTC)

        # Generate inputs fingerprint
        inputs_fingerprint = str(hash(json.dumps(inputs_json, sort_keys=True)))

        # Extract model from inputs if available
        model = None
        if "model" in inputs_json:
            model = inputs_json["model"]
        elif "messages" in inputs_json and inputs_json["messages"]:
            # Try to extract from LLM-style inputs
            model = inputs_json.get("model", "gpt-4o-mini")  # Default fallback

        # Determine status and extract metadata
        status = "completed" if result.get("status") == "success" else "failed"
        result_meta = result.get("meta", {})

        # Extract image reference for digest fallback
        image_ref = None
        try:
            image_ref = registry_snapshot["processors"][ref]["image"]["oci"]
        except (KeyError, TypeError):
            pass

        # Plan information for extras (optional)
        plan_extras = {}
        if plan_obj:
            plan_extras["plan_id"] = plan_obj.id
        if execution:
            plan_extras["execution_pk"] = execution.id

        # Build complete receipt with new signature
        receipt_data = build_receipt(
            processor=ref,
            model=model,
            status=status,
            execution_id=execution_id,
            inputs_fingerprint=inputs_fingerprint,
            env_fingerprint=result_meta.get("env_fingerprint", ""),
            image_ref=image_ref,
            image_digest=result_meta.get("image_digest"),
            started_at=started_at,
            finished_at=finished_at,
            extra=plan_extras,
        )

        # Write receipt to write_prefix location alongside outputs
        receipt_path = f"{write_prefix}receipt.json"
        receipt_bytes = json.dumps(receipt_data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        artifact_store.put_bytes(receipt_path, receipt_bytes, "application/json")

        # Write determinism receipt and settle execution if plan/execution exists
        if execution and result.get("status") == "success":
            # Derive output_cids from canonical outputs
            outputs = result.get("outputs") or []
            output_cids = [o["cid"] for o in outputs if isinstance(o, dict) and "cid" in o]

            env_fp = result.get("env_fingerprint") or (result.get("meta") or {}).get("env_fingerprint", "")
            determinism_uri = write_determinism_receipt(
                plan=plan_obj,
                execution=execution,
                seed=result.get("seed", 0),
                memo_key=result.get("memo_key", ""),
                env_fingerprint=env_fp,
                output_cids=output_cids,
            )

            # Settle execution with canonical output metadata
            # Include outputs_index/outputs_count only when outputs non-empty
            outputs_index = result.get("index_path") if outputs else None
            outputs_count = len(outputs) if outputs else None
            settle_execution_success(
                plan=plan_obj,
                execution=execution,
                estimate_hi_micro=result.get("estimate_micro", 1000),
                actual_micro=result.get("actual_micro", 500),
                seed=result.get("seed", 0),
                memo_key=result.get("memo_key", ""),
                env_fingerprint=env_fp,
                output_cids=output_cids,
                outputs_index=outputs_index,
                outputs_count=outputs_count,
            )

            result["determinism_uri"] = determinism_uri

        # Ensure execution_id is in result envelope (contract guarantee)
        result["execution_id"] = execution_id

        return result

    except Exception as e:
        execution_id = str(execution.id) if execution else str(uuid.uuid4())

        if execution:
            # Settle as failure
            settle_execution_failure(
                plan=plan_obj, execution=execution, estimate_hi_micro=1000, metered_actual_micro=100, reason=str(e)
            )

        # Create error result for programmatic access
        return {
            "status": "error",
            "execution_id": execution_id,
            "error": {"code": "ERR_COMMAND_EXCEPTION", "message": str(e)},
            "meta": {"env_fingerprint": "command_error"},
        }
