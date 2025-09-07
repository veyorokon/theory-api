"""
Acceptance tests for ledger invariants:
- Reserve→settle atomicity (success/failure/refund)
- Per-plan sequence monotonicity under concurrency (no global lock)
- Hash-chain continuity and tamper detection
"""

import pytest
from django.test import TestCase, TransactionTestCase
from django.db import transaction, IntegrityError
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Barrier
import uuid

from apps.plans.models import Plan
from apps.ledger.models import Event
from apps.ledger.services import LedgerWriter
from apps.ledger.utils import event_hash


@pytest.mark.ledger_acceptance
class TestLedgerAcceptance(TransactionTestCase):
    """Acceptance tests for ledger invariants using Django models."""
    
    def setUp(self):
        """Set up test data."""
        self.plan = Plan.objects.create(
            key=f"test-plan-{uuid.uuid4()}",
            reserved_micro=1000000,  # $10.00
            spent_micro=0
        )
        self.ledger = LedgerWriter()
    
    def test_reserve_settle_success_atomicity(self):
        """Test reserve→settle atomicity on successful execution using LedgerWriter."""
        initial_reserved = self.plan.reserved_micro
        initial_spent = self.plan.spent_micro
        
        # Reserve using LedgerWriter
        reserve_amount = 50000  # $0.50
        reserve_event = self.ledger.reserve_execution(self.plan, reserve_amount)
        
        # Verify reservation
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.reserved_micro, initial_reserved + reserve_amount)
        self.assertEqual(self.plan.spent_micro, initial_spent)
        
        # Verify reserve event
        self.assertEqual(reserve_event.seq, 1)
        self.assertEqual(reserve_event.payload['event_type'], 'budget.reserved')
        self.assertEqual(reserve_event.payload['amount_micro'], reserve_amount)
        self.assertIsNone(reserve_event.prev_hash)
        
        # Settle using LedgerWriter (success)
        actual_cost = 30000  # $0.30
        settle_event = self.ledger.settle_execution(self.plan, reserve_amount, actual_cost, success=True)
        
        # Verify settlement - spent increases, reservation cleared
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.spent_micro, initial_spent + actual_cost)
        self.assertEqual(self.plan.reserved_micro, initial_reserved)  # Back to original
        
        # Verify settle event
        self.assertEqual(settle_event.seq, 2)
        self.assertEqual(settle_event.payload['event_type'], 'budget.settled')
        self.assertTrue(settle_event.payload['success'])
        self.assertEqual(settle_event.payload['actual_cost_micro'], actual_cost)
        self.assertEqual(settle_event.prev_hash, reserve_event.this_hash)
        
        # Verify hash chain integrity
        events = Event.objects.filter(plan=self.plan).order_by('seq')
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].prev_hash, events[0].this_hash)
    
    def test_reserve_settle_failure_refund(self):
        """Test reserve→settle with failure refund using LedgerWriter."""
        initial_reserved = self.plan.reserved_micro
        initial_spent = self.plan.spent_micro
        
        # Reserve using LedgerWriter
        reserve_amount = 75000  # $0.75
        reserve_event = self.ledger.reserve_execution(self.plan, reserve_amount)
        
        # Verify reservation
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.reserved_micro, initial_reserved + reserve_amount)
        
        # Settle with failure using LedgerWriter (should refund, no spending)
        settle_event = self.ledger.settle_execution(self.plan, reserve_amount, 0, success=False)
        
        # Verify full refund
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.reserved_micro, initial_reserved)  # Back to original
        self.assertEqual(self.plan.spent_micro, initial_spent)        # No spending
        
        # Verify settle event
        self.assertEqual(settle_event.payload['event_type'], 'budget.settled')
        self.assertFalse(settle_event.payload['success'])
        self.assertEqual(settle_event.payload['actual_cost_micro'], 0)
    
    def test_budget_never_negative_constraint(self):
        """Test that budget constraints prevent negative values."""
        # Try to set negative reserved_micro
        self.plan.reserved_micro = -100
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                self.plan.save()
        
        # Try to set negative spent_micro  
        self.plan.refresh_from_db()  # Reset to clean state
        self.plan.spent_micro = -200
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                self.plan.save()
    
    @pytest.mark.requires_postgres
    def test_sequence_monotonicity_per_plan(self):
        """Test per-plan sequence monotonicity under concurrency."""
        def append_event(worker_id: int, barrier: Barrier) -> tuple[int, bool]:
            """Append event after barrier synchronization."""
            barrier.wait()  # Synchronize all workers
            
            try:
                with transaction.atomic():
                    # Get current max sequence
                    last_event = Event.objects.filter(plan=self.plan).order_by('-seq').first()
                    next_seq = (last_event.seq if last_event else 0) + 1
                    
                    Event.objects.create(
                        plan=self.plan,
                        seq=next_seq,
                        prev_hash=last_event.this_hash if last_event else None,
                        this_hash=event_hash({
                            'event_type': 'test.concurrent',
                            'worker_id': worker_id,
                            'seq': next_seq
                        }),
                        payload={
                            'event_type': 'test.concurrent',
                            'worker_id': worker_id,
                            'seq': next_seq
                        }
                    )
                    return (worker_id, True)
            except IntegrityError:
                # Unique constraint violation on (plan, seq)
                return (worker_id, False)
        
        # Run concurrent workers
        num_workers = 5
        barrier = Barrier(num_workers)
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(append_event, i, barrier) for i in range(num_workers)]
            results = [future.result() for future in as_completed(futures)]
        
        # Verify results
        successful_workers = [worker_id for worker_id, success in results if success]
        failed_workers = [worker_id for worker_id, success in results if not success]
        
        # Exactly one worker should succeed due to unique constraint
        self.assertEqual(len(successful_workers), 1, 
                        f"Expected exactly 1 successful worker, got {len(successful_workers)}")
        self.assertEqual(len(failed_workers), num_workers - 1,
                        f"Expected {num_workers - 1} failed workers, got {len(failed_workers)}")
        
        # Verify sequence is correct
        events = Event.objects.filter(plan=self.plan).order_by('seq')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].seq, 1)
    
    def test_hash_chain_continuity(self):
        """Test hash chain continuity and tamper detection."""
        # Create first event
        event1_payload = {
            'event_type': 'test.first',
            'data': 'first_event',
            'plan_id': self.plan.key
        }
        event1_hash = event_hash(event1_payload)
        
        event1 = Event.objects.create(
            plan=self.plan,
            seq=1,
            prev_hash=None,
            this_hash=event1_hash,
            payload=event1_payload
        )
        
        # Create second event with correct prev_hash
        event2_payload = {
            'event_type': 'test.second',
            'data': 'second_event',
            'plan_id': self.plan.key
        }
        event2_hash = event_hash(event2_payload)
        
        event2 = Event.objects.create(
            plan=self.plan,
            seq=2,
            prev_hash=event1.this_hash,
            this_hash=event2_hash,
            payload=event2_payload
        )
        
        # Verify chain integrity
        events = Event.objects.filter(plan=self.plan).order_by('seq')
        self.assertEqual(len(events), 2)
        self.assertIsNone(events[0].prev_hash)
        self.assertEqual(events[1].prev_hash, events[0].this_hash)
        
        # Verify hash computation is correct
        self.assertEqual(events[0].this_hash, event_hash(events[0].payload))
        self.assertEqual(events[1].this_hash, event_hash(events[1].payload))
    
    def test_tamper_detection_through_hash_verification(self):
        """Test tamper detection by hash recomputation."""
        # Create event
        original_payload = {
            'event_type': 'important.data',
            'sensitive_value': 'original_value',
            'plan_id': self.plan.key
        }
        original_hash = event_hash(original_payload)
        
        event = Event.objects.create(
            plan=self.plan,
            seq=1,
            prev_hash=None,
            this_hash=original_hash,
            payload=original_payload
        )
        
        # Simulate tampering with payload
        tampered_payload = original_payload.copy()
        tampered_payload['sensitive_value'] = 'tampered_value'
        
        # Recompute hash of tampered payload
        tampered_hash = event_hash(tampered_payload)
        
        # Hash should be different, proving tamper detection works
        self.assertNotEqual(tampered_hash, event.this_hash)
        
        # Original stored hash should still match original payload
        self.assertEqual(event.this_hash, event_hash(original_payload))
    
    @pytest.mark.requires_postgres
    def test_concurrent_different_plans_no_interference(self):
        """Test that concurrent operations on different plans don't interfere."""
        # Create additional plans
        plans = [self.plan]
        for i in range(4):
            plans.append(Plan.objects.create(
                key=f"concurrent-plan-{i}",
                reserved_micro=100000,
                spent_micro=0
            ))
        
        def append_events_for_plan(plan: Plan) -> int:
            """Append 3 events for the given plan."""
            events_created = 0
            for seq in range(1, 4):  # Create 3 events per plan
                Event.objects.create(
                    plan=plan,
                    seq=seq,
                    prev_hash=None if seq == 1 else f"hash_{seq-1}",
                    this_hash=event_hash({
                        'event_type': 'test.plan_isolation',
                        'plan_id': plan.key,
                        'seq': seq
                    }),
                    payload={
                        'event_type': 'test.plan_isolation',
                        'plan_id': plan.key,
                        'seq': seq
                    }
                )
                events_created += 1
            return events_created
        
        # Run concurrent operations on different plans
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(append_events_for_plan, plan) for plan in plans]
            results = [future.result() for future in as_completed(futures)]
        
        # Verify each plan has exactly 3 events
        self.assertEqual(all(count == 3 for count in results), True)
        
        for plan in plans:
            events = Event.objects.filter(plan=plan).order_by('seq')
            self.assertEqual(len(events), 3)
            
            # Verify sequences are 1, 2, 3 for each plan
            sequences = [event.seq for event in events]
            self.assertEqual(sequences, [1, 2, 3])
    
    def test_unique_plan_seq_constraint(self):
        """Test that the unique (plan, seq) constraint is enforced."""
        # Create first event
        Event.objects.create(
            plan=self.plan,
            seq=1,
            prev_hash=None,
            this_hash=event_hash({'event_type': 'test.unique', 'plan_id': self.plan.key}),
            payload={'event_type': 'test.unique', 'plan_id': self.plan.key}
        )
        
        # Try to create another event with same plan and seq
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Event.objects.create(
                    plan=self.plan,
                    seq=1,  # Same seq - should fail
                    prev_hash=None,
                    this_hash=event_hash({'event_type': 'test.duplicate', 'plan_id': self.plan.key}),
                    payload={'event_type': 'test.duplicate', 'plan_id': self.plan.key}
                )
        
        # Verify only one event exists
        events = Event.objects.filter(plan=self.plan)
        self.assertEqual(len(events), 1)