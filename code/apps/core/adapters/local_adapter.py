"""
Local adapter for host development execution.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import RuntimeAdapter


class LocalAdapter(RuntimeAdapter):
    """Local adapter for host development execution."""
    
    def __init__(self):
        """Initialize local adapter."""
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
        Invoke processor locally using host Python.
        
        Args:
            processor_ref: Processor reference
            image_digest: Container image digest (treated as local path)
            inputs_json: JSON string with processor inputs
            write_prefix: Prefix path for outputs
            plan_id: Plan identifier
            timeout_s: Optional timeout in seconds
            secrets: Optional list of secret names
            adapter_opts_json: Optional adapter-specific options
            
        Returns:
            Execution result from local execution
        """
        # Validate write prefix
        if not self.validate_write_prefix(write_prefix):
            raise ValueError(f"Invalid write_prefix: {write_prefix}")
        
        # Parse adapter options
        adapter_opts = {}
        if adapter_opts_json:
            try:
                adapter_opts = json.loads(adapter_opts_json)
            except json.JSONDecodeError:
                pass
        
        # Resolve secrets from environment
        env = os.environ.copy()
        if secrets:
            secret_values = self.resolve_secrets(secrets)
            env.update(secret_values)
        
        # Determine processor path
        if image_digest.startswith('/'):
            # Absolute path to processor
            processor_path = Path(image_digest)
        else:
            # Relative path from code directory
            processor_path = Path('code/apps/core/processors') / image_digest
        
        # Check if processor exists
        processor_module = processor_path / 'processor.py'
        if not processor_module.exists():
            raise FileNotFoundError(f"Processor not found: {processor_module}")
        
        # Create temporary input file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(inputs_json)
            inputs_file = f.name
        
        try:
            # Execute processor
            cmd = [
                'python',
                str(processor_module),
                '--inputs', inputs_json,
                '--write-prefix', write_prefix
            ]
            
            # Add plan ID if available
            if plan_id:
                cmd.extend(['--plan', plan_id])
            
            # Run with timeout
            timeout = timeout_s or 300
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=processor_path
            )
            
            # Parse result
            if result.returncode == 0:
                try:
                    execution_result = json.loads(result.stdout)
                except json.JSONDecodeError:
                    execution_result = {
                        'status': 'error',
                        'error': 'Failed to parse processor output',
                        'raw_output': result.stdout
                    }
            else:
                execution_result = {
                    'status': 'error',
                    'error': f'Process failed with exit code {result.returncode}',
                    'stderr': result.stderr,
                    'stdout': result.stdout
                }
            
            # Add local execution metadata
            if execution_result.get('status') == 'success':
                execution_result.setdefault('env_fingerprint', f"local-{processor_ref}")
            
            # Track execution
            self.executions.append({
                'processor_ref': processor_ref,
                'plan_id': plan_id,
                'cmd': cmd,
                'result': execution_result
            })
            
            return execution_result
            
        except subprocess.TimeoutExpired:
            return {
                'status': 'error',
                'error': f'Processor timed out after {timeout} seconds'
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': f'Local execution failed: {str(e)}'
            }
        finally:
            # Clean up temporary file
            try:
                os.unlink(inputs_file)
            except OSError:
                pass
    
    def resolve_secrets(self, secret_names: List[str]) -> Dict[str, str]:
        """
        Resolve secret names from environment variables.
        
        Args:
            secret_names: List of secret names
            
        Returns:
            Dictionary of secret name to value from environment
        """
        secrets = {}
        for name in secret_names:
            value = os.environ.get(name)
            if value:
                secrets[name] = value
        return secrets