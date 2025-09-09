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
        adapter_opts_json: Optional[str] = None,
        build: bool = False
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
            build: Whether to build image (ignored in mock)
            
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
        
        execution_id = adapter_opts.get('execution_id', plan_id)
        
        # Simulate processing time
        time.sleep(0.1)
        
        # Mock different processor types with canonical output format
        from apps.storage.artifact_store import artifact_store
        import mimetypes
        
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
            
            # Build canonical outputs array matching real processor structure
            entries = []
            
            # Response text file (matches /work/out/text/response.txt)
            response_bytes = response_text.encode('utf-8')
            p1 = f"{write_prefix}text/response.txt"
            c1 = artifact_store.compute_cid(response_bytes)
            artifact_store.put_bytes(p1, response_bytes, 'text/plain')
            entries.append({
                'path': p1,
                'cid': c1,
                'size_bytes': len(response_bytes),
                'mime': 'text/plain'
            })
            
            # Metadata file (matches /work/out/meta.json with real processor fields)
            meta_json = json.dumps({
                'model': 'mock-llm',
                'tokens_in': len(response_text.split()),
                'tokens_out': len(response_text.split()),
                'duration_ms': 100
            })
            meta_bytes = meta_json.encode('utf-8')
            p2 = f"{write_prefix}meta.json"
            c2 = artifact_store.compute_cid(meta_bytes)
            artifact_store.put_bytes(p2, meta_bytes, 'application/json')
            entries.append({
                'path': p2,
                'cid': c2,
                'size_bytes': len(meta_bytes),
                'mime': 'application/json'
            })
            
            # Sort entries by path
            entries.sort(key=lambda x: x['path'])
            
            # Create index artifact
            index_path = f"/artifacts/execution/{execution_id}/outputs.json"
            index_bytes = json.dumps(entries, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
            artifact_store.put_bytes(index_path, index_bytes, 'application/json')
            
            result = {
                'status': 'success',
                'execution_id': execution_id,
                'outputs': entries,
                'index_path': index_path,
                'meta': {
                    'image_digest': f'mock-{image_digest}',
                    'env_fingerprint': f"mock-{image_digest}-cpu:1-memory:512",
                    'duration_ms': 100,
                    'io_bytes': sum(e['size_bytes'] for e in entries)
                }
            }
        else:
            # Generic mock processor
            result_data = json.dumps({
                'processed': True,
                'input_keys': list(inputs.keys()),
                'plan_id': plan_id
            })
            result_bytes = result_data.encode('utf-8')
            p1 = f"{write_prefix}result.json"
            c1 = artifact_store.compute_cid(result_bytes)
            artifact_store.put_bytes(p1, result_bytes, 'application/json')
            
            entries = [{
                'path': p1,
                'cid': c1,
                'size_bytes': len(result_bytes),
                'mime': 'application/json'
            }]
            
            # Create index artifact
            index_path = f"/artifacts/execution/{execution_id}/outputs.json"
            index_bytes = json.dumps(entries, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
            artifact_store.put_bytes(index_path, index_bytes, 'application/json')
            
            result = {
                'status': 'success',
                'execution_id': execution_id,
                'outputs': entries,
                'index_path': index_path,
                'meta': {
                    'image_digest': f'mock-{image_digest}',
                    'env_fingerprint': f"mock-{image_digest}-generic",
                    'duration_ms': 50,
                    'io_bytes': len(result_bytes)
                }
            }
        
        # Track execution
        self.executions.append({
            'processor_ref': processor_ref,
            'plan_id': plan_id,
            'result': result,
            'timestamp': time.time()
        })
        
        return result