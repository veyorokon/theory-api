"""
Mock adapter for testing without real infrastructure.
"""
import json
import time
from typing import Any, Dict, List, Optional

from .base import RuntimeAdapter


class MockAdapter(RuntimeAdapter):
    """Mock adapter that simulates execution locally."""
    
    def __init__(self):
        """Initialize mock adapter."""
        self.executions = []
    
    def invoke(
        self,
        processor_ref: str,
        image_digest: str,
        inputs_json: str,
        write_prefix: str,
        plan_id: str,
        timeout_s: Optional[int] = None,
        secrets: Optional[List[str]] = None,
        adapter_opts_json: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke processor in mock mode.
        
        Args:
            processor_ref: Processor reference
            image_digest: Container image digest (ignored in mock)
            inputs_json: JSON string with processor inputs
            write_prefix: Prefix path for outputs
            plan_id: Plan identifier
            timeout_s: Optional timeout
            secrets: Optional secret names
            adapter_opts_json: Optional adapter options
            
        Returns:
            Mock execution result
        """
        # Validate write prefix
        if not self.validate_write_prefix(write_prefix):
            raise ValueError(f"Invalid write_prefix: {write_prefix}")
        
        # Parse inputs
        try:
            inputs = json.loads(inputs_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid inputs_json: {e}")
        
        # Parse adapter options if provided
        adapter_opts = {}
        if adapter_opts_json:
            try:
                adapter_opts = json.loads(adapter_opts_json)
            except json.JSONDecodeError:
                pass
        
        # Simulate processing time
        time.sleep(0.1)
        
        # Mock different processor types
        outputs = {}
        if 'llm' in processor_ref:
            # Mock LLM processor
            messages = inputs.get('messages', [])
            response_text = f"Mock response to {len(messages)} messages"
            
            # Handle attachment references
            for msg in messages:
                if isinstance(msg, dict):
                    content = msg.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and '$artifact' in item:
                                response_text += f" (saw attachment: {item['$artifact']})"
            
            outputs = {
                f"{write_prefix}text/response.txt": response_text,
                f"{write_prefix}metadata.json": json.dumps({
                    'model': 'mock-llm',
                    'tokens': len(response_text.split()),
                    'timestamp': time.time(),
                    'plan_id': plan_id
                })
            }
            
            result = {
                'status': 'success',
                'outputs': outputs,
                'seed': 12345,
                'memo_key': f"mock-{processor_ref}-{hash(inputs_json)}",
                'env_fingerprint': f"mock-{image_digest}-cpu:1-memory:512",
                'output_cids': ['mock-cid-1', 'mock-cid-2'],
                'estimate_micro': 1000,
                'actual_micro': 500
            }
        else:
            # Generic mock processor
            outputs = {
                f"{write_prefix}result.json": json.dumps({
                    'processed': True,
                    'input_keys': list(inputs.keys()),
                    'plan_id': plan_id
                })
            }
            
            result = {
                'status': 'success',
                'outputs': outputs,
                'seed': 67890,
                'memo_key': f"mock-generic-{processor_ref}",
                'env_fingerprint': f"mock-{image_digest}-generic",
                'output_cids': ['mock-generic-cid'],
                'estimate_micro': 500,
                'actual_micro': 250
            }
        
        # Track execution
        self.executions.append({
            'processor_ref': processor_ref,
            'plan_id': plan_id,
            'result': result,
            'timestamp': time.time()
        })
        
        return result