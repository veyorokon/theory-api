"""
Ledger services for atomic event writing and budget operations.
"""

from django.db import transaction

from .models import Event
from apps.plans.models import Plan
from .utils import event_hash


class LedgerWriter:
    """Service for atomically writing events and managing budget operations."""

    def append_event(self, plan: Plan, payload: dict) -> Event:
        """Append an event to the ledger with proper sequencing and hash chaining."""
        with transaction.atomic():
            # Get last event for this plan with row-level lock
            last_event = Event.objects.select_for_update().filter(plan=plan).order_by("-seq").first()

            # Calculate next sequence and hash chain
            next_seq = (last_event.seq if last_event else 0) + 1
            prev_hash = last_event.this_hash if last_event else None
            this_hash = event_hash(payload, prev_hash=prev_hash, include_ts=True)

            # Atomically create event
            return Event.objects.create(
                plan=plan, seq=next_seq, prev_hash=prev_hash, this_hash=this_hash, payload=payload
            )

    def reserve_execution(self, plan: Plan, amount_micro: int) -> Event:
        """Reserve budget for execution atomically."""
        with transaction.atomic():
            # Lock plan for atomic budget update
            plan = Plan.objects.select_for_update().get(id=plan.id)
            plan.reserved_micro += amount_micro
            plan.save(update_fields=["reserved_micro"])

            # Record reservation event
            return self.append_event(
                plan,
                {
                    "event_type": "budget.reserved",
                    "amount_micro": amount_micro,
                    "plan_id": plan.key,
                },
            )

    def settle_execution(self, plan: Plan, reserved_amount_micro: int, actual_cost_micro: int, success: bool) -> Event:
        """Settle execution budget atomically (success or failure)."""
        with transaction.atomic():
            # Lock plan for atomic budget update
            plan = Plan.objects.select_for_update().get(id=plan.id)

            # Release reservation
            plan.reserved_micro -= reserved_amount_micro

            # On success, record actual spending
            if success and actual_cost_micro > 0:
                plan.spent_micro += actual_cost_micro

            plan.save(update_fields=["reserved_micro", "spent_micro"])

            # Record settlement event
            return self.append_event(
                plan,
                {
                    "event_type": "budget.settled",
                    "success": success,
                    "reserved_micro": reserved_amount_micro,
                    "actual_cost_micro": actual_cost_micro,
                    "plan_id": plan.key,
                },
            )
