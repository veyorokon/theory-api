"""
Unit tests for determinism receipts functionality.

Tests receipt writing, content stability, and hashing.
"""

import json
from unittest.mock import patch, MagicMock
import pytest
from django.test import TestCase

from apps.plans.models import Plan
from apps.runtime.models import Transition, Execution
from apps.runtime.determinism import write_determinism_receipt
from apps.runtime.services import settle_execution_success, settle_execution_failure


@pytest.mark.unit
class TestDeterminismReceiptWriter(TestCase):
    """Test determinism receipt writing functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.plan = Plan.objects.create(key='test-plan', reserved_micro=10000, spent_micro=0)
        self.transition = Transition.objects.create(
            plan=self.plan, 
            key='t1', 
            status='running'
        )
        self.execution = Execution.objects.create(
            transition=self.transition, 
            attempt_idx=1
        )
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    def test_write_determinism_receipt_structure(self, mock_upload):
        """Should write determinism receipt with correct JSON structure."""
        mock_upload.return_value = 'mock-url'
        
        result_path = write_determinism_receipt(
            plan=self.plan,
            execution=self.execution,
            seed=12345,
            memo_key='test-memo-key',
            env_fingerprint='python-3.11-django-5.2',
            output_cids=['cid1', 'cid2']
        )
        
        # Verify upload was called
        mock_upload.assert_called_once()
        
        # Check call arguments
        call_args = mock_upload.call_args
        data = call_args[0][0]                      # first positional argument
        key = call_args[1]['key']                   # keyword argument
        content_type = call_args[1]['content_type'] # keyword argument
        bucket = call_args[1]['bucket']             # keyword argument
        
        # Verify path format
        self.assertEqual(key, f'/artifacts/execution/{self.execution.id}/determinism.json')
        self.assertEqual(content_type, 'application/json')
        self.assertEqual(bucket, 'default')
        self.assertEqual(result_path, key)
        
        # Verify JSON structure
        receipt_data = json.loads(data.decode('utf-8'))
        expected_structure = {
            'seed': 12345,
            'memo_key': 'test-memo-key',
            'env_fingerprint': 'python-3.11-django-5.2',
            'output_cids': ['cid1', 'cid2']
        }
        self.assertEqual(receipt_data, expected_structure)
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    def test_write_determinism_receipt_empty_cids(self, mock_upload):
        """Should handle empty output_cids gracefully."""
        mock_upload.return_value = 'mock-url'
        
        write_determinism_receipt(
            plan=self.plan,
            execution=self.execution,
            seed=12345,
            memo_key='test-memo-key',
            env_fingerprint='python-3.11-django-5.2',
            output_cids=[]
        )
        
        # Check data contains empty list
        call_args = mock_upload.call_args
        data = call_args[0][0]  # first positional argument
        receipt_data = json.loads(data.decode('utf-8'))
        self.assertEqual(receipt_data['output_cids'], [])
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    def test_write_determinism_receipt_none_cids(self, mock_upload):
        """Should handle None output_cids gracefully."""
        mock_upload.return_value = 'mock-url'
        
        write_determinism_receipt(
            plan=self.plan,
            execution=self.execution,
            seed=12345,
            memo_key='test-memo-key',
            env_fingerprint='python-3.11-django-5.2',
            output_cids=None
        )
        
        # Check data contains empty list
        call_args = mock_upload.call_args
        data = call_args[0][0]  # first positional argument
        receipt_data = json.loads(data.decode('utf-8'))
        self.assertEqual(receipt_data['output_cids'], [])
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    def test_deterministic_json_serialization(self, mock_upload):
        """Should produce stable JSON output for same inputs."""
        mock_upload.return_value = 'mock-url'
        
        inputs = {
            'plan': self.plan,
            'execution': self.execution,
            'seed': 42,
            'memo_key': 'stable-key',
            'env_fingerprint': 'python-3.11-django-5.2',
            'output_cids': ['cid-alpha', 'cid-beta']
        }
        
        # Call twice with identical inputs
        write_determinism_receipt(**inputs)
        write_determinism_receipt(**inputs)
        
        # Both calls should produce identical JSON
        calls = mock_upload.call_args_list
        self.assertEqual(len(calls), 2)
        
        data1 = calls[0][0][0]  # first call, first positional argument
        data2 = calls[1][0][0]  # second call, first positional argument
        
        # Should be byte-for-byte identical
        self.assertEqual(data1, data2)
        
        # Should be valid, compact JSON
        receipt1 = json.loads(data1.decode('utf-8'))
        receipt2 = json.loads(data2.decode('utf-8'))
        self.assertEqual(receipt1, receipt2)


@pytest.mark.unit
class TestSettleExecutionIntegration(TestCase):
    """Test settlement functions integration with receipts and ledger."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.plan = Plan.objects.create(key='test-plan', reserved_micro=10000, spent_micro=0)
        self.transition = Transition.objects.create(
            plan=self.plan, 
            key='t1', 
            status='running'
        )
        self.execution = Execution.objects.create(
            transition=self.transition, 
            attempt_idx=1
        )
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    @patch('apps.ledger.services.LedgerWriter.append_event')
    def test_settle_execution_success_writes_receipt(self, mock_append_event, mock_upload):
        """Should write receipt and emit ledger event on success."""
        mock_upload.return_value = 'mock-url'
        mock_event = MagicMock()
        mock_append_event.return_value = mock_event
        
        result_uri = settle_execution_success(
            plan=self.plan,
            execution=self.execution,
            estimate_hi_micro=5000,
            actual_micro=3000,
            seed=12345,
            memo_key='test-memo',
            env_fingerprint='python-3.11-django-5.2',
            output_cids=['cid1', 'cid2']
        )
        
        # Should return determinism URI
        expected_path = f'/artifacts/execution/{self.execution.id}/determinism.json'
        self.assertEqual(result_uri, expected_path)
        
        # Should update plan budget
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.reserved_micro, 5000)  # 10000 - 5000
        self.assertEqual(self.plan.spent_micro, 3000)     # 0 + 3000
        
        # Should write receipt
        mock_upload.assert_called_once()
        
        # Should emit ledger event with correct payload
        mock_append_event.assert_called_once()
        event_payload = mock_append_event.call_args[0][1]  # Second positional arg
        
        expected_payload = {
            'event_type': 'execution.settle.success',
            'actual_micro': 3000,
            'estimate_hi_micro': 5000,
            'refund_micro': 2000,  # 5000 - 3000
            'determinism_uri': expected_path,
            'execution_id': str(self.execution.id),
            'plan_id': self.plan.key
        }
        self.assertEqual(event_payload, expected_payload)
    
    @patch('apps.ledger.services.LedgerWriter.append_event')
    def test_settle_execution_failure_emits_event(self, mock_append_event):
        """Should emit ledger event on failure without receipt."""
        mock_event = MagicMock()
        mock_append_event.return_value = mock_event
        
        settle_execution_failure(
            plan=self.plan,
            execution=self.execution,
            estimate_hi_micro=5000,
            metered_actual_micro=1000,
            reason='Timeout occurred'
        )
        
        # Should update plan budget
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.reserved_micro, 5000)  # 10000 - 5000
        self.assertEqual(self.plan.spent_micro, 1000)     # 0 + 1000
        
        # Should emit failure event
        mock_append_event.assert_called_once()
        event_payload = mock_append_event.call_args[0][1]
        
        expected_payload = {
            'event_type': 'execution.settle.failure',
            'estimate_hi_micro': 5000,
            'metered_actual_micro': 1000,
            'reason': 'Timeout occurred',
            'execution_id': str(self.execution.id),
            'plan_id': self.plan.key
        }
        self.assertEqual(event_payload, expected_payload)
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    @patch('apps.ledger.services.LedgerWriter.append_event')
    def test_settle_execution_success_zero_refund(self, mock_append_event, mock_upload):
        """Should handle case where actual equals estimate (zero refund)."""
        mock_upload.return_value = 'mock-url'
        mock_event = MagicMock()
        mock_append_event.return_value = mock_event
        
        settle_execution_success(
            plan=self.plan,
            execution=self.execution,
            estimate_hi_micro=4000,
            actual_micro=4000,  # Exact match
            seed=12345,
            memo_key='test-memo',
            env_fingerprint='python-3.11-django-5.2',
            output_cids=[]
        )
        
        # Should have zero refund
        event_payload = mock_append_event.call_args[0][1]
        self.assertEqual(event_payload['refund_micro'], 0)
        self.assertEqual(event_payload['actual_micro'], 4000)
        self.assertEqual(event_payload['estimate_hi_micro'], 4000)
    
    @patch('apps.storage.service.storage_service.upload_bytes')
    @patch('apps.ledger.services.LedgerWriter.append_event')
    def test_settle_execution_success_negative_refund_clamped(self, mock_append_event, mock_upload):
        """Should clamp negative refunds to zero."""
        mock_upload.return_value = 'mock-url'
        mock_event = MagicMock()
        mock_append_event.return_value = mock_event
        
        settle_execution_success(
            plan=self.plan,
            execution=self.execution,
            estimate_hi_micro=3000,
            actual_micro=5000,  # Overrun
            seed=12345,
            memo_key='test-memo',
            env_fingerprint='python-3.11-django-5.2',
            output_cids=[]
        )
        
        # Should clamp refund to 0, not negative
        event_payload = mock_append_event.call_args[0][1]
        self.assertEqual(event_payload['refund_micro'], 0)
        self.assertEqual(event_payload['actual_micro'], 5000)
        self.assertEqual(event_payload['estimate_hi_micro'], 3000)