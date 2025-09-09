from __future__ import annotations
from typing import Iterable, Optional
from datetime import datetime, timezone
from django.db import transaction
from apps.plans.models import Plan
from apps.runtime.models import Execution
from apps.ledger.services import LedgerWriter
from .determinism import write_determinism_receipt

def settle_execution_success(
    *,
    plan: Plan,
    execution: Execution,
    estimate_hi_micro: int,
    actual_micro: int,
    seed: int,
    memo_key: str,
    env_fingerprint: str,
    output_cids: Iterable[str],
) -> str:
    """
    Success path: clears reserve fully, records spend, writes receipt, emits event with pointer.
    Returns determinism_uri.
    """
    with transaction.atomic():
        # Budget math (μUSD)
        refund_micro = max(int(estimate_hi_micro) - int(actual_micro), 0)
        plan.reserved_micro = int(plan.reserved_micro) - int(estimate_hi_micro)
        plan.spent_micro = int(plan.spent_micro) + int(actual_micro)
        plan.save(update_fields=["reserved_micro", "spent_micro"])

        # Write determinism receipt
        determinism_uri = write_determinism_receipt(
            plan=plan,
            execution=execution,
            seed=seed,
            memo_key=memo_key,
            env_fingerprint=env_fingerprint,
            output_cids=list(output_cids or []),
        )

        # Emit ledger event with determinism reference
        ledger_writer = LedgerWriter()
        ledger_writer.append_event(plan, {
            'kind': 'execution.settle.success',
            'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'actual_micro': int(actual_micro),
            'estimate_hi_micro': int(estimate_hi_micro),
            'refund_micro': refund_micro,
            'determinism_uri': determinism_uri,
            'execution_id': str(execution.id),
            'plan_id': plan.key
        })
        
        return determinism_uri

def settle_execution_failure(
    *,
    plan: Plan,
    execution: Execution,
    estimate_hi_micro: int,
    metered_actual_micro: int = 0,
    reason: Optional[str] = None,
) -> None:
    """
    Failure path: clears full reserve; may record any metered actual spend.
    """
    with transaction.atomic():
        plan.reserved_micro = int(plan.reserved_micro) - int(estimate_hi_micro)
        plan.spent_micro = int(plan.spent_micro) + int(metered_actual_micro)
        plan.save(update_fields=["reserved_micro", "spent_micro"])

        # Emit ledger event for failure
        ledger_writer = LedgerWriter()
        ledger_writer.append_event(plan, {
            'kind': 'execution.settle.failure',
            'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'estimate_hi_micro': int(estimate_hi_micro),
            'metered_actual_micro': int(metered_actual_micro),
            'reason': reason or '',
            'execution_id': str(execution.id),
            'plan_id': plan.key
        })

def record_memo_hit(*, plan: Plan, execution: Execution, memo_key: str) -> None:
    """
    Memo hits do not reserve budget (or if you prefer uniform accounting later:
    reserve -> immediate refund; not implemented here).
    """
    ledger_writer = LedgerWriter()
    ledger_writer.append_event(plan, {
        'kind': 'execution.memo_hit',
        'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'memo_key': memo_key,
        'execution_id': str(execution.id),
        'plan_id': plan.key
    })
