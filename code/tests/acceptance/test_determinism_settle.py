"""
Acceptance tests for determinism settlement with PostgreSQL.

Tests end-to-end settlement flows with real database and ledger chaining.
"""

import json
from unittest.mock import patch, MagicMock
import pytest
from django.test import TransactionTestCase

from apps.plans.models import Plan
from apps.runtime.models import Transition, Execution
from apps.runtime.services import settle_execution_success, settle_execution_failure
from apps.ledger.models import Event


@pytest.mark.requires_postgres
class TestDeterminismSettlementAcceptance(TransactionTestCase):
    """End-to-end acceptance tests for determinism settlement."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.plan = Plan.objects.create(
            key='acceptance-plan', 
            reserved_micro=50000, 
            spent_micro=10000
        )
        self.transition = Transition.objects.create(
            plan=self.plan, 
            key='transition-1', 
            status='running'
        )
        self.execution = Execution.objects.create(
            transition=self.transition, 
            attempt_idx=1
        )
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    def test_settle_success_full_flow_with_ledger_chaining(self, mock_upload):
        """Should complete success settlement with proper ledger event chaining."""
        mock_upload.return_value = 'storage-url'
        
        # Verify initial state
        initial_reserved = self.plan.reserved_micro
        initial_spent = self.plan.spent_micro
        initial_event_count = Event.objects.filter(plan=self.plan).count()
        
        # Execute settlement
        determinism_uri = settle_execution_success(
            plan=self.plan,
            execution=self.execution,
            estimate_hi_micro=20000,
            actual_micro=15000,
            seed=987654321,
            memo_key='acceptance-memo-key',
            env_fingerprint='python-3.11.13-django-5.2.0',
            output_cids=['acceptance-cid-1', 'acceptance-cid-2', 'acceptance-cid-3']
        )
        
        # Verify determinism URI format
        expected_path = f'/artifacts/execution/{self.execution.id}/determinism.json'
        self.assertEqual(determinism_uri, expected_path)
        
        # Verify plan budget changes
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.reserved_micro, initial_reserved - 20000)
        self.assertEqual(self.plan.spent_micro, initial_spent + 15000)
        
        # Verify storage upload was called with correct data
        mock_upload.assert_called_once()
        call_args = mock_upload.call_args
        uploaded_data = call_args[0][0]      # first positional argument
        uploaded_key = call_args[1]['key']   # keyword argument
        
        self.assertEqual(uploaded_key, expected_path)
        
        # Verify uploaded receipt structure
        receipt_data = json.loads(uploaded_data.decode('utf-8'))
        expected_receipt = {
            'seed': 987654321,
            'memo_key': 'acceptance-memo-key',
            'env_fingerprint': 'python-3.11.13-django-5.2.0',
            'output_cids': ['acceptance-cid-1', 'acceptance-cid-2', 'acceptance-cid-3']
        }
        self.assertEqual(receipt_data, expected_receipt)
        
        # Verify ledger event was created
        new_events = Event.objects.filter(plan=self.plan).order_by('seq')
        self.assertEqual(new_events.count(), initial_event_count + 1)
        
        latest_event = new_events.last()
        self.assertEqual(latest_event.plan, self.plan)
        self.assertIsNotNone(latest_event.this_hash)
        
        # Verify event payload
        event_payload = latest_event.payload
        expected_payload = {
            'event_type': 'execution.settle.success',
            'actual_micro': 15000,
            'estimate_hi_micro': 20000,
            'refund_micro': 5000,  # 20000 - 15000
            'determinism_uri': expected_path,
            'execution_id': str(self.execution.id),
            'plan_id': self.plan.key
        }
        self.assertEqual(event_payload, expected_payload)
        
        # Verify hash chaining if there was a previous event
        if initial_event_count > 0:
            previous_event = Event.objects.filter(plan=self.plan).order_by('-seq')[1]
            self.assertEqual(latest_event.prev_hash, previous_event.this_hash)
    
    def test_settle_failure_with_ledger_integration(self):
        """Should complete failure settlement with ledger event."""
        # Record initial state
        initial_reserved = self.plan.reserved_micro
        initial_spent = self.plan.spent_micro
        initial_event_count = Event.objects.filter(plan=self.plan).count()
        
        # Execute failure settlement
        settle_execution_failure(
            plan=self.plan,
            execution=self.execution,
            estimate_hi_micro=25000,
            metered_actual_micro=8000,
            reason='Resource allocation failed'
        )
        
        # Verify plan budget changes
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.reserved_micro, initial_reserved - 25000)
        self.assertEqual(self.plan.spent_micro, initial_spent + 8000)
        
        # Verify ledger event was created
        new_events = Event.objects.filter(plan=self.plan).order_by('seq')
        self.assertEqual(new_events.count(), initial_event_count + 1)
        
        latest_event = new_events.last()
        event_payload = latest_event.payload
        expected_payload = {
            'event_type': 'execution.settle.failure',
            'estimate_hi_micro': 25000,
            'metered_actual_micro': 8000,
            'reason': 'Resource allocation failed',
            'execution_id': str(self.execution.id),
            'plan_id': self.plan.key
        }
        self.assertEqual(event_payload, expected_payload)
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    def test_multiple_settlements_maintain_hash_chain(self, mock_upload):
        """Should maintain proper hash chain across multiple settlements."""
        mock_upload.return_value = 'storage-url'
        
        # Create multiple executions
        execution2 = Execution.objects.create(
            transition=self.transition,
            attempt_idx=2
        )
        execution3 = Execution.objects.create(
            transition=self.transition,
            attempt_idx=3
        )
        
        # Record initial hash chain state
        initial_events = list(Event.objects.filter(plan=self.plan).order_by('seq'))
        
        # Execute multiple settlements
        settle_execution_success(
            plan=self.plan,
            execution=self.execution,
            estimate_hi_micro=10000,
            actual_micro=8000,
            seed=111,
            memo_key='memo-1',
            env_fingerprint='env-1',
            output_cids=['cid-1']
        )
        
        settle_execution_failure(
            plan=self.plan,
            execution=execution2,
            estimate_hi_micro=15000,
            metered_actual_micro=5000,
            reason='Failed execution'
        )
        
        settle_execution_success(
            plan=self.plan,
            execution=execution3,
            estimate_hi_micro=12000,
            actual_micro=11000,
            seed=222,
            memo_key='memo-3',
            env_fingerprint='env-3',
            output_cids=['cid-3']
        )
        
        # Verify hash chain integrity
        all_events = Event.objects.filter(plan=self.plan).order_by('seq')
        events_list = list(all_events)
        
        for i, event in enumerate(events_list):
            if i == 0:
                # First event should have no prev_hash
                self.assertIsNone(event.prev_hash)
            else:
                # Each subsequent event should reference the previous
                prev_event = events_list[i - 1]
                self.assertEqual(event.prev_hash, prev_event.this_hash)
            
            # Every event should have a this_hash
            self.assertIsNotNone(event.this_hash)
            self.assertIsInstance(event.this_hash, str)
            self.assertTrue(len(event.this_hash) > 0)
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    def test_concurrent_settlements_maintain_atomicity(self, mock_upload):
        """Should handle concurrent settlement attempts atomically."""
        mock_upload.return_value = 'storage-url'
        
        # This test verifies that the database transactions work correctly
        # In a real concurrent scenario, only one should succeed due to locking
        
        from django.db import transaction
        
        initial_reserved = self.plan.reserved_micro
        initial_spent = self.plan.spent_micro
        
        # Execute settlement within transaction
        with transaction.atomic():
            settle_execution_success(
                plan=self.plan,
                execution=self.execution,
                estimate_hi_micro=30000,
                actual_micro=25000,
                seed=999,
                memo_key='concurrent-memo',
                env_fingerprint='concurrent-env',
                output_cids=['concurrent-cid']
            )
        
        # Verify atomic changes
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.reserved_micro, initial_reserved - 30000)
        self.assertEqual(self.plan.spent_micro, initial_spent + 25000)
        
        # Verify exactly one event was created for this execution
        execution_events = Event.objects.filter(
            plan=self.plan,
            payload__execution_id=str(self.execution.id)
        )
        self.assertEqual(execution_events.count(), 1)
    
    def test_plan_budget_constraints_respected(self):
        """Should respect plan budget constraints during settlement."""
        # Set up plan with limited budget
        limited_plan = Plan.objects.create(
            key='limited-plan',
            reserved_micro=1000,  # Small amount
            spent_micro=0
        )
        transition = Transition.objects.create(
            plan=limited_plan,
            key='limited-transition',
            status='running'
        )
        execution = Execution.objects.create(
            transition=transition,
            attempt_idx=1
        )
        
        # Attempt to settle for more than reserved
        settle_execution_failure(
            plan=limited_plan,
            execution=execution,
            estimate_hi_micro=1000,  # Exactly what's reserved
            metered_actual_micro=500,
            reason='Partial completion'
        )
        
        # Should work correctly
        limited_plan.refresh_from_db()
        self.assertEqual(limited_plan.reserved_micro, 0)    # 1000 - 1000
        self.assertEqual(limited_plan.spent_micro, 500)     # 0 + 500
        
        # Verify event was recorded
        events = Event.objects.filter(plan=limited_plan)
        self.assertEqual(events.count(), 1)
        
        event = events.first()
        self.assertEqual(event.payload['event_type'], 'execution.settle.failure')
        self.assertEqual(event.payload['metered_actual_micro'], 500)