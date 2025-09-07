# Ledger Events

The Theory API ledger provides an immutable, hash-chained audit trail of all execution events.

## Event Structure

Each ledger event contains:

- `plan` - Foreign key to Plan model  
- `seq` - Monotonic sequence number within plan
- `prev_hash` - Hash of previous event in chain (null for first event)
- `this_hash` - BLAKE3 hash of this event's canonical bytes
- `payload` - JSON event data (event_type, parameters)
- `created_at` - Timestamp of event creation

## Event Bytes & Hashing

### Canonical JSON Serialization

Events are canonicalized using JSON serialization with strict ordering rules to ensure deterministic hash computation:

1. **Field Ordering**: Keys are sorted lexicographically 
2. **Compact Format**: No whitespace, separators `(',', ':')`
3. **UTF-8 Encoding**: All strings encoded as UTF-8 bytes
4. **Timestamp Exclusion**: Timestamps excluded from hash in MVP (may be included later with ADR)

### BLAKE3 Hash Chain

Each event includes a BLAKE3 hash computed over the previous hash concatenated with canonical JSON bytes:

```text
canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
canonical_bytes = canonical_json.encode('utf-8')
prev_bytes = bytes.fromhex(prev_hash) if prev_hash else b''
this_hash = BLAKE3(prev_bytes + canonical_bytes).hexdigest()
```

The hash chain links events sequentially:
- First event: `prev_hash = null`
- Subsequent events: `prev_hash = previous_event.this_hash`

### Worked Example

Consider this ledger event payload:

```json
{
  "event_type": "budget.reserved",
  "amount_micro": 150000,
  "plan_id": "media-pipeline-001"
}
```

**Step 1: Canonical JSON Serialization**

Keys sorted lexicographically, compact separators:
```json
{"amount_micro":150000,"event_type":"budget.reserved","plan_id":"media-pipeline-001"}
```

**Step 2: UTF-8 Byte Representation**

Canonical JSON encoded as UTF-8 bytes:
```text
7b 22 61 6d 6f 75 6e 74 5f 6d 69 63 72 6f 22 3a 31 35 30 30 30 30 2c 22 65 76 65 6e 74 5f 74 79 70 65 22 3a 22 62 75 64 67 65 74 2e 72 65 73 65 72 76 65 64 22 2c 22 70 6c 61 6e 5f 69 64 22 3a 22 6d 65 64 69 61 2d 70 69 70 65 6c 69 6e 65 2d 30 30 31 22 7d
```

**Step 3: BLAKE3 Hash Computation**

For the first event, prev_hash is absent, so only canonical bytes are hashed. For subsequent events, include `prev_hash` bytes as a prefix before hashing.

```text
this_hash = BLAKE3(prev_bytes + canonical_bytes).hexdigest()
```

### Tamper Detection

The hash chain provides tamper-evident properties:

1. **Payload Integrity**: Any change to event payload produces different `this_hash`
2. **Chain Continuity**: Modifying an event breaks `prev_hash` links for subsequent events
3. **Sequence Validation**: Missing, reordered, or duplicate events break the hash chain

## Event Types

The ledger records these event types:

### Budget Events
- `budget.reserved` - Resources reserved for execution
- `budget.settled` - Final resource accounting (success/failure)

### Execution Events  
- `execution.started` - Executor begins processing transition
- `execution.succeeded` - Successful completion with artifacts
- `execution.failed` - Failed execution with error details

### Artifact Events
- `artifact.produced` - New artifact created at world:// path
- `artifact.consumed` - Artifact read/used by execution

### Predicate Events
- `predicate.checked` - Rule evaluation result (allow/deny)

Each event type has specific payload schemas defined by the system.

## Concurrency & Sequencing

### Per-Plan Monotonic Sequences

- Sequence numbers are monotonic **per plan** (not globally)
- Database constraint: `UNIQUE(plan, seq)` prevents duplicates
- No global locks required - each plan has independent sequence space
- Concurrent plans can append events simultaneously without interference

### Hash Chain Integrity

Events maintain hash chain continuity within each plan:

```python
# Pseudocode for event appending
def append_event(plan, payload):
    with transaction.atomic():
        # Get last event for this plan
        last_event = Event.objects.filter(plan=plan).order_by('-seq').first()
        
        # Compute next sequence and hash
        next_seq = (last_event.seq if last_event else 0) + 1
        prev_hash = last_event.this_hash if last_event else None
        this_hash = event_hash(payload, prev_hash=prev_hash)
        
        # Atomically create event
        Event.objects.create(
            plan=plan,
            seq=next_seq,
            prev_hash=prev_hash,
            this_hash=this_hash,
            payload=payload
        )
```

### Invariant Enforcement

The ledger maintains these invariants through database constraints and application logic:

1. **Unique Sequences**: `UNIQUE(plan_id, seq)` constraint prevents sequence conflicts
2. **Monotonic Growth**: Sequences increase strictly within each plan  
3. **Hash Continuity**: Each event's `prev_hash` equals the previous event's `this_hash`
4. **Non-negative Budgets**: Budget operations never drive amounts below zero

## Storage & Performance

### Database Schema

The Event model uses these database-level constraints:

```sql
-- Unique constraint on plan + sequence
ALTER TABLE ledger_event 
ADD CONSTRAINT uq_event_plan_seq UNIQUE (plan_id, seq);

-- Index for efficient lookups
CREATE INDEX idx_event_plan_seq ON ledger_event (plan_id, seq);
CREATE INDEX idx_event_plan_created ON ledger_event (plan_id, created_at);
```

### Hash Verification

Hash integrity can be verified by recomputing hashes:

```python
def verify_hash_chain(plan):
    events = Event.objects.filter(plan=plan).order_by('seq')
    
    for i, event in enumerate(events):
        # Verify this_hash matches payload + prev_hash
        prev_hash = events[i-1].this_hash if i > 0 else None
        computed_hash = event_hash(event.payload, prev_hash=prev_hash)
        assert event.this_hash == computed_hash, f"Hash mismatch at seq {event.seq}"
        
        # Verify prev_hash continuity
        if i == 0:
            assert event.prev_hash is None, "First event should have null prev_hash"
        else:
            expected_prev = events[i-1].this_hash
            assert event.prev_hash == expected_prev, f"Chain broken at seq {event.seq}"
```

### Performance Considerations

- **Partitioning**: Consider partitioning by plan_id for large deployments
- **Archival**: Old events can be archived while maintaining recent hash chains
- **Async Verification**: Hash verification can be performed asynchronously
- **Batch Operations**: Multiple events can be created in single transactions

## Implementation Notes

### Hash Algorithm Choice

- **Production**: Use BLAKE3 for performance and security
- **Development**: SHA256 fallback acceptable if BLAKE3 unavailable
- **Consistency**: All environments should use same algorithm

### Timestamp Handling

- **MVP Policy**: Timestamps excluded from hash computation
- **Future**: May include timestamps with appropriate ADR
- **Storage**: Timestamps stored in `created_at` field regardless of hash inclusion

### Error Handling

- **Constraint Violations**: Handle `IntegrityError` for sequence conflicts
- **Hash Mismatches**: Log tampering attempts, fail operations
- **Chain Breaks**: Detect and alert on hash chain discontinuities