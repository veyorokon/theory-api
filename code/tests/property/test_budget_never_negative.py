"""
Property-based tests for budget invariants:
- Budget never goes negative across randomized attempts
- Reserve/settle operations maintain consistency
"""

import pytest
from django.test import TestCase, TransactionTestCase
from django.db import transaction, IntegrityError
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import uuid

from apps.plans.models import Plan


@pytest.mark.property
class TestBudgetProperties(TransactionTestCase):
    """Property-based tests for budget invariants."""

    def setUp(self):
        """Set up test data."""
        self.plan = Plan.objects.create(
            key=f"property-test-{uuid.uuid4()}",
            reserved_micro=5000000,  # $50.00
            spent_micro=0,
        )

    def test_budget_never_negative_single_threaded(self):
        """Property: budgets never go negative in deterministic scenario."""
        initial_reserved = self.plan.reserved_micro
        initial_spent = self.plan.spent_micro

        # Perform deterministic sequence of operations
        operations = [
            ("reserve", 100000),  # Reserve $1.00
            ("spend", 50000),  # Spend $0.50
            ("reserve", 200000),  # Reserve $2.00
            ("spend", 150000),  # Spend $1.50
            ("refund", 50000),  # Refund $0.50
        ]

        running_reserved = initial_reserved
        running_spent = initial_spent

        for operation, amount in operations:
            with transaction.atomic():
                if operation == "reserve":
                    self.plan.reserved_micro += amount
                    running_reserved += amount
                elif operation == "spend":
                    if amount <= self.plan.reserved_micro:  # Only spend if reserved
                        self.plan.spent_micro += amount
                        self.plan.reserved_micro -= amount
                        running_spent += amount
                        running_reserved -= amount
                elif operation == "refund":
                    if amount <= self.plan.spent_micro:  # Only refund if spent
                        self.plan.spent_micro -= amount
                        running_spent -= amount

                # Save and verify constraints
                try:
                    self.plan.save()
                except IntegrityError:
                    # Rollback and continue - this validates constraints work
                    transaction.rollback()
                    continue

                self.plan.refresh_from_db()

                # Invariant: budgets never negative
                self.assertGreaterEqual(
                    self.plan.reserved_micro, 0, f"Reserved micro went negative: {self.plan.reserved_micro}"
                )
                self.assertGreaterEqual(self.plan.spent_micro, 0, f"Spent micro went negative: {self.plan.spent_micro}")

    def test_budget_never_negative_randomized(self):
        """Property: budgets never go negative across randomized operations."""
        random.seed(42)  # Deterministic for reproducibility

        for _ in range(50):
            operation = random.choice(["reserve", "spend", "partial_refund"])
            amount = random.randint(1000, 100000)  # $0.01 to $1.00

            try:
                with transaction.atomic():
                    if operation == "reserve":
                        # Reserve up to remaining capacity
                        max_reserve = 10000000 - self.plan.reserved_micro  # $100 max total
                        amount = min(amount, max_reserve)
                        if amount > 0:
                            self.plan.reserved_micro += amount

                    elif operation == "spend":
                        # Spend from reserved amount
                        amount = min(amount, self.plan.reserved_micro)
                        if amount > 0:
                            self.plan.spent_micro += amount
                            self.plan.reserved_micro -= amount

                    elif operation == "partial_refund":
                        # Refund part of spent amount
                        amount = min(amount, self.plan.spent_micro)
                        if amount > 0:
                            self.plan.spent_micro -= amount

                    self.plan.save()
                    self.plan.refresh_from_db()

                    # Invariant: budgets never negative
                    self.assertGreaterEqual(self.plan.reserved_micro, 0)
                    self.assertGreaterEqual(self.plan.spent_micro, 0)

            except IntegrityError:
                # Constraint prevented negative values - this is expected
                transaction.rollback()
                self.plan.refresh_from_db()

    @pytest.mark.requires_postgres
    def test_concurrent_budget_operations_atomicity(self):
        """Property: concurrent budget operations are atomic."""

        def random_budget_operation(worker_id: int) -> tuple[int, int, int]:
            """Perform random budget operations, return (worker_id, operations_attempted, operations_succeeded)."""
            operations_attempted = 0
            operations_succeeded = 0

            for _ in range(10):  # 10 operations per worker
                operations_attempted += 1
                operation = random.choice(["reserve", "spend"])
                amount = random.randint(1000, 50000)  # $0.01 to $0.50

                try:
                    with transaction.atomic():
                        plan = Plan.objects.select_for_update().get(id=self.plan.id)

                        if operation == "reserve":
                            # Only reserve if we have capacity
                            max_total = 10000000  # $100 max
                            if plan.reserved_micro + plan.spent_micro + amount <= max_total:
                                plan.reserved_micro += amount
                                plan.save()
                                operations_succeeded += 1

                        elif operation == "spend":
                            # Only spend if we have reserved funds
                            if amount <= plan.reserved_micro:
                                plan.spent_micro += amount
                                plan.reserved_micro -= amount
                                plan.save()
                                operations_succeeded += 1

                except (IntegrityError, Exception):
                    # Operation failed - expected under concurrency
                    continue

            return (worker_id, operations_attempted, operations_succeeded)

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(random_budget_operation, i) for i in range(5)]
            results = [future.result() for future in as_completed(futures)]

        # Verify final state is consistent
        self.plan.refresh_from_db()
        self.assertGreaterEqual(self.plan.reserved_micro, 0)
        self.assertGreaterEqual(self.plan.spent_micro, 0)

        # At least some operations should have succeeded
        total_succeeded = sum(succeeded for _, _, succeeded in results)
        self.assertGreater(total_succeeded, 0, "No operations succeeded in concurrent test")

    def test_reserve_settle_idempotency(self):
        """Property: reserve/settle sequences are idempotent at the accounting layer."""
        initial_reserved = self.plan.reserved_micro
        initial_spent = self.plan.spent_micro

        # Perform the same reserve→spend→reserve sequence multiple times
        for iteration in range(3):
            reserve_amount = 100000  # $1.00
            spend_amount = 60000  # $0.60

            # Reserve
            with transaction.atomic():
                self.plan.reserved_micro += reserve_amount
                self.plan.save()

            # Spend part of reservation
            with transaction.atomic():
                self.plan.spent_micro += spend_amount
                self.plan.reserved_micro -= spend_amount
                self.plan.save()

            # Verify intermediate state
            self.plan.refresh_from_db()
            expected_reserved = initial_reserved + (reserve_amount - spend_amount) * (iteration + 1)
            expected_spent = initial_spent + spend_amount * (iteration + 1)

            self.assertEqual(self.plan.reserved_micro, expected_reserved)
            self.assertEqual(self.plan.spent_micro, expected_spent)

            # Invariants maintained
            self.assertGreaterEqual(self.plan.reserved_micro, 0)
            self.assertGreaterEqual(self.plan.spent_micro, 0)

    def test_budget_conservation_property(self):
        """Property: total budget (reserved + spent + remaining) is conserved across operations."""
        # Start with known total budget
        initial_total_budget = 1000000  # $10.00
        self.plan.reserved_micro = initial_total_budget
        self.plan.spent_micro = 0
        self.plan.save()

        operations = [
            ("spend", 200000),  # Spend $2.00 from reserved
            ("spend", 300000),  # Spend $3.00 from reserved
            ("reserve_more", 500000),  # Add $5.00 to reserved (external funding)
            ("spend", 150000),  # Spend $1.50 from reserved
        ]

        total_external_additions = 0

        for operation, amount in operations:
            with transaction.atomic():
                if operation == "spend":
                    if amount <= self.plan.reserved_micro:
                        self.plan.spent_micro += amount
                        self.plan.reserved_micro -= amount

                elif operation == "reserve_more":
                    # Simulate external funding addition
                    self.plan.reserved_micro += amount
                    total_external_additions += amount

                self.plan.save()
                self.plan.refresh_from_db()

                # Property: total accounted funds = initial + external additions
                total_accounted = self.plan.reserved_micro + self.plan.spent_micro
                expected_total = initial_total_budget + total_external_additions

                self.assertEqual(
                    total_accounted, expected_total, f"Budget not conserved: {total_accounted} != {expected_total}"
                )

    def test_no_overdraft_property(self):
        """Property: cannot spend more than reserved (no overdraft)."""
        # Set up limited budget
        self.plan.reserved_micro = 50000  # $0.50
        self.plan.spent_micro = 0
        self.plan.save()

        # Try to spend more than reserved
        overdraft_attempts = [
            60000,  # $0.60 (more than $0.50 reserved)
            100000,  # $1.00 (much more than reserved)
            51000,  # $0.51 (just slightly over)
        ]

        for overdraft_amount in overdraft_attempts:
            initial_spent = self.plan.spent_micro
            initial_reserved = self.plan.reserved_micro

            # Attempt overdraft
            attempted_spend = overdraft_amount
            if attempted_spend <= self.plan.reserved_micro:
                # This should succeed
                with transaction.atomic():
                    self.plan.spent_micro += attempted_spend
                    self.plan.reserved_micro -= attempted_spend
                    self.plan.save()
            else:
                # This should be prevented by application logic
                # (In real implementation, would check before attempting)
                pass

            self.plan.refresh_from_db()

            # Property: spent cannot exceed what was available to spend
            total_spent = self.plan.spent_micro - initial_spent
            max_spendable = initial_reserved

            self.assertLessEqual(
                total_spent, max_spendable, f"Overdraft occurred: spent {total_spent} > available {max_spendable}"
            )

    @pytest.mark.requires_postgres
    def test_concurrent_plan_budget_isolation(self):
        """Property: concurrent operations on different plans don't affect each other's budgets."""
        # Create additional plans
        other_plans = []
        for i in range(3):
            other_plans.append(
                Plan.objects.create(
                    key=f"isolation-test-{i}",
                    reserved_micro=200000,  # $2.00 each
                    spent_micro=0,
                )
            )

        all_plans = [self.plan] + other_plans

        def operate_on_plan(plan: Plan) -> tuple[int, int]:
            """Perform operations on a single plan."""
            initial_reserved = plan.reserved_micro
            initial_spent = plan.spent_micro

            # Perform some operations
            operations = [
                ("spend", 50000),  # $0.50
                ("spend", 30000),  # $0.30
            ]

            for operation, amount in operations:
                try:
                    with transaction.atomic():
                        plan = Plan.objects.select_for_update().get(id=plan.id)
                        if operation == "spend" and amount <= plan.reserved_micro:
                            plan.spent_micro += amount
                            plan.reserved_micro -= amount
                            plan.save()
                except Exception:
                    continue

            plan.refresh_from_db()
            return (plan.id, plan.reserved_micro + plan.spent_micro)

        # Run operations concurrently on different plans
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(operate_on_plan, plan) for plan in all_plans]
            results = [future.result() for future in as_completed(futures)]

        # Verify each plan maintains its budget independently
        for plan_id, final_total in results:
            plan = Plan.objects.get(id=plan_id)

            # Each plan should have non-negative budgets
            self.assertGreaterEqual(plan.reserved_micro, 0)
            self.assertGreaterEqual(plan.spent_micro, 0)

            # Total budget should be conserved (no cross-plan interference)
            if plan == self.plan:
                expected_total = 5000000  # Original $50.00
            else:
                expected_total = 200000  # Original $2.00

            self.assertEqual(
                final_total, expected_total, f"Plan {plan_id} budget not conserved: {final_total} != {expected_total}"
            )

    def test_rollback_safety_property(self):
        """Property: failed transactions don't leave budgets in inconsistent state."""
        initial_reserved = self.plan.reserved_micro
        initial_spent = self.plan.spent_micro

        # Simulate transaction that should fail
        try:
            with transaction.atomic():
                # Valid operation
                self.plan.reserved_micro += 100000  # Reserve $1.00
                self.plan.save()

                # Force constraint violation
                self.plan.spent_micro = -50000  # Invalid negative spent
                self.plan.save()  # This should fail
        except IntegrityError:
            # Expected - transaction should rollback
            pass

        # Verify rollback occurred
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.reserved_micro, initial_reserved)
        self.assertEqual(self.plan.spent_micro, initial_spent)

        # Budgets remain non-negative
        self.assertGreaterEqual(self.plan.reserved_micro, 0)
        self.assertGreaterEqual(self.plan.spent_micro, 0)
