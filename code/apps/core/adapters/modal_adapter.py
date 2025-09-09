"""
Modal adapter for cloud execution.
"""
import json
import os
from typing import Any, Dict, List, Optional

from django.conf import settings

from .base import RuntimeAdapter


class ModalAdapter(RuntimeAdapter):
    """Real Modal adapter for cloud execution."""
    
    def __init__(self):
        """Initialize Modal adapter."""
        self.modal_available = False
        self.modal = None
        
        # Check if Modal should be enabled
        if not getattr(settings, 'MODAL_ENABLED', False):
            return
        
        # Try to import Modal
        try:
            import modal
            self.modal_available = True
            self.modal = modal
        except ImportError:
            pass
    
    def _ensure_modal(self):
        """Ensure Modal is available and configured."""
        if not self.modal_available:
            raise RuntimeError(
                "Modal not available. Install 'modal' package and set MODAL_ENABLED=True"
            )
        
        # Check for Modal token
        if not os.environ.get('MODAL_TOKEN_ID'):
            raise RuntimeError(
                "MODAL_TOKEN_ID not set. Run 'modal token new' to authenticate"
            )
    
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
        Invoke processor on Modal.
        
        Args:
            processor_ref: Processor reference
            image_digest: Container image digest
            inputs_json: JSON string with processor inputs
            write_prefix: Prefix path for outputs
            plan_id: Plan identifier
            timeout_s: Optional timeout in seconds
            secrets: Optional list of secret names
            adapter_opts_json: Optional adapter-specific options
            
        Returns:
            Execution result from Modal
        """
        self._ensure_modal()
        
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
        
        # Get or create stub
        stub_name = adapter_opts.get('stub_name', processor_ref.replace('/', '_').replace('@', '_'))
        stub = self.modal.Stub(stub_name)
        
        # Configure image
        if image_digest.startswith('oci:'):
            # Use pre-built OCI image
            image = self.modal.Image.from_registry(image_digest[4:])
        else:
            # Use digest as dockerfile path
            image = self.modal.Image.from_dockerfile(image_digest)
        
        # Configure runtime
        cpu = float(adapter_opts.get('cpu', 1))
        memory = int(adapter_opts.get('memory', 512))
        timeout = timeout_s or 300
        gpu = adapter_opts.get('gpu')
        
        # Validate GPU if specified
        if gpu and not self._validate_gpu(gpu):
            raise ValueError(f"Invalid GPU specification: {gpu}")
        
        # Create function kwargs
        function_kwargs = {
            'image': image,
            'cpu': cpu,
            'memory': memory,
            'timeout': timeout,
        }
        
        if gpu:
            function_kwargs['gpu'] = gpu
        
        # Resolve secrets
        if secrets:
            modal_secrets = self._resolve_modal_secrets(secrets)
            if modal_secrets:
                function_kwargs['secrets'] = modal_secrets
        
        # Define the function
        @stub.function(**function_kwargs)
        def process(inputs: str, prefix: str, plan: str) -> str:
            """Process function that runs in Modal."""
            import subprocess
            result = subprocess.run(
                ['python', '-m', 'processor', '--inputs', inputs, '--write-prefix', prefix, '--plan', plan],
                capture_output=True,
                text=True
            )
            return result.stdout
        
        # Run on Modal
        with stub.run():
            result_json = process.remote(
                inputs=inputs_json,
                prefix=write_prefix,
                plan=plan_id
            )
        
        # Parse result
        try:
            result = json.loads(result_json)
        except json.JSONDecodeError:
            result = {
                'status': 'error',
                'error': 'Failed to parse processor output',
                'raw_output': result_json
            }
        
        return result
    
    def _validate_gpu(self, gpu_spec: str) -> bool:
        """Validate GPU specification against Modal's supported GPUs."""
        valid_gpus = ['t4', 'a10g', 'a100', 'a100-80gb', 'h100']
        gpu_lower = gpu_spec.lower()
        return any(gpu in gpu_lower for gpu in valid_gpus)
    
    def _resolve_modal_secrets(self, secret_names: List[str]) -> List:
        """Resolve secret names to Modal secret references."""
        if not self.modal_available:
            return []
        
        secrets = []
        for name in secret_names:
            # Map to Modal secret (must be pre-created in Modal)
            try:
                secret = self.modal.Secret.from_name(name)
                secrets.append(secret)
            except Exception:
                # Skip secrets that don't exist
                pass
        
        return secrets