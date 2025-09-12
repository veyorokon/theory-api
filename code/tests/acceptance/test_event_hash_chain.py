"""
Hash chain continuity tests for ledger events.

Verifies that event hashing includes previous hash for tamper-evidence.
"""

import pytest
from django.test import TestCase
from apps.plans.models import Plan
from apps.ledger.services import LedgerWriter
from apps.ledger.utils import event_hash


@pytest.mark.ledger_acceptance
class TestEventHashChain(TestCase):
    """Test hash chain continuity across events."""

    def setUp(self):
        """Set up test plan and writer."""
        self.plan = Plan.objects.create(key="test-hash-chain", reserved_micro=0, spent_micro=0)
        self.writer = LedgerWriter()

    def test_second_event_hash_includes_prev(self):
        """Verify seq=2 event hash includes prev_hash correctly."""
        # Create first event
        payload1 = {"event_type": "test.one", "plan_id": self.plan.key}
        e1 = self.writer.append_event(self.plan, payload1)

        # Create second event
        payload2 = {"event_type": "test.two", "plan_id": self.plan.key}
        e2 = self.writer.append_event(self.plan, payload2)

        # Verify hash chain linkage
        self.assertEqual(e2.prev_hash, e1.this_hash)

        # Verify second event hash includes previous hash
        expected_hash = event_hash(payload2, prev_hash=e1.this_hash, include_ts=False)
        self.assertEqual(e2.this_hash, expected_hash)

    def test_first_event_hash_no_prev(self):
        """Verify first event hash with no previous hash (empty prefix)."""
        payload = {"event_type": "test.genesis", "plan_id": self.plan.key}
        event = self.writer.append_event(self.plan, payload)

        # First event should have no prev_hash
        self.assertIsNone(event.prev_hash)

        # Hash should match payload-only hash (empty prefix)
        expected_hash = event_hash(payload, prev_hash=None, include_ts=False)
        self.assertEqual(event.this_hash, expected_hash)

    def test_hash_chain_sequence(self):
        """Verify hash chain integrity across multiple events."""
        payloads = [
            {"event_type": "test.alpha", "plan_id": self.plan.key},
            {"event_type": "test.beta", "plan_id": self.plan.key},
            {"event_type": "test.gamma", "plan_id": self.plan.key},
        ]

        events = []
        for payload in payloads:
            event = self.writer.append_event(self.plan, payload)
            events.append(event)

        # Verify chain linkage
        self.assertIsNone(events[0].prev_hash)  # Genesis event
        self.assertEqual(events[1].prev_hash, events[0].this_hash)
        self.assertEqual(events[2].prev_hash, events[1].this_hash)

        # Verify hash computation for each event
        for i, (event, payload) in enumerate(zip(events, payloads, strict=False)):
            prev_hash = events[i - 1].this_hash if i > 0 else None
            expected = event_hash(payload, prev_hash=prev_hash, include_ts=False)
            self.assertEqual(event.this_hash, expected, f"Event {i} hash mismatch")
