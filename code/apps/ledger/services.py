"""
Ledger services for atomic event writing and budget operations.
"""


class LedgerWriter:
    """Service for atomically writing events and managing budget operations."""
    
    def append_event(self, plan, payload):
        """Append an event to the ledger with proper sequencing and hash chaining."""
        raise NotImplementedError("append_event will be implemented in Step B")
    
    def reserve_execution(self, plan, transition, amount_micro):
        """Reserve budget for execution atomically."""
        raise NotImplementedError("reserve_execution will be implemented in Step B")
    
    def settle_execution(self, plan, transition, amount_micro, success: bool):
        """Settle execution budget atomically (success or failure)."""
        raise NotImplementedError("settle_execution will be implemented in Step B")