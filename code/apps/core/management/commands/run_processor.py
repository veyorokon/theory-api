"""
Run processor management command - unified processor execution with attachments.

Supports local, mock, and Modal adapters with attachment materialization.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.plans.models import Plan
from apps.runtime.models import Transition, Execution
from apps.storage.artifact_store import artifact_store
from apps.runtime.determinism import write_determinism_receipt
from apps.runtime.services import settle_execution_success, settle_execution_failure
from apps.core.adapters import MockAdapter, LocalAdapter, ModalAdapter
from apps.core.utils.processor_ref import ref_to_local_dir


class Command(BaseCommand):
    """Run processor with unified adapter interface and attachment support."""
    
    help = "Run processor with adapter selection and attachment materialization"
    
    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            '--ref',
            required=True,
            help='Processor reference (e.g., llm/litellm@1)'
        )
        parser.add_argument(
            '--adapter',
            choices=['local', 'mock', 'modal'],
            default='local',
            help='Execution adapter to use'
        )
        parser.add_argument(
            '--plan',
            help='Plan key for budget tracking (creates if not exists)'
        )
        parser.add_argument(
            '--write-prefix',
            default='/artifacts/outputs/',
            help='Write prefix for outputs (must end with /)'
        )
        parser.add_argument(
            '--inputs-json',
            default='{}',
            help='JSON input for processor'
        )
        parser.add_argument(
            '--adapter-opts-json',
            help='Optional adapter-specific options as JSON'
        )
        parser.add_argument(
            '--attach',
            action='append',
            help='Attach file as name=path (can be used multiple times)'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output JSON response'
        )
        parser.add_argument(
            '--timeout',
            type=int,
            help='Timeout in seconds'
        )
        parser.add_argument(
            '--build',
            action='store_true',
            help='Build container image if not available (requires build spec in registry)'
        )
        parser.add_argument(
            '--save-dir',
            help='Download all outputs into this directory (mirrors world paths)'
        )
        parser.add_argument(
            '--save-first',
            help='Download only the first output into this file path'
        )
    
    def materialize_attachments(self, attachments: List[str]) -> Dict[str, Dict[str, Any]]:
        """Materialize attachment files and return mapping."""
        if not attachments:
            return {}
        
        attachment_map = {}
        
        for attach_spec in attachments:
            if '=' not in attach_spec:
                self.stderr.write(f"Invalid attachment format: {attach_spec} (expected name=path)")
                continue
            
            name, path = attach_spec.split('=', 1)
            file_path = Path(path)
            
            if not file_path.exists():
                self.stderr.write(f"Attachment file not found: {path}")
                continue
            
            # Read file data
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Compute CID
            cid = artifact_store.compute_cid(data)
            
            # Determine MIME type
            import mimetypes
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Store in artifact store
            artifact_path = f"/artifacts/inputs/{cid}/{file_path.name}"
            artifact_store.put_bytes(artifact_path, data, mime_type)
            
            attachment_map[name] = {
                '$artifact': artifact_path,
                'cid': cid,
                'mime': mime_type
            }
            
            if not self.options.get('json'):
                self.stdout.write(f"Materialized {name} -> {artifact_path} ({cid})")
        
        return attachment_map
    
    def rewrite_attach_references(self, obj: Any, attachment_map: Dict[str, Dict[str, Any]]) -> Any:
        """Recursively rewrite $attach references to $artifact."""
        if isinstance(obj, dict):
            if '$attach' in obj and len(obj) == 1:
                attach_name = obj['$attach']
                if attach_name in attachment_map:
                    return attachment_map[attach_name]
                else:
                    self.stderr.write(f"Warning: attachment '{attach_name}' not found")
                    return obj
            return {k: self.rewrite_attach_references(v, attachment_map) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.rewrite_attach_references(item, attachment_map) for item in obj]
        return obj
    
    def get_adapter(self, adapter_name: str):
        """Get adapter instance by name."""
        if adapter_name == 'mock':
            return MockAdapter()
        elif adapter_name == 'modal':
            return ModalAdapter()
        elif adapter_name == 'local':
            return LocalAdapter()
        else:
            raise ValueError(f"Unknown adapter: {adapter_name}")
    
    def get_image_digest(self, processor_ref: str) -> str:
        """Get image digest for processor reference."""
        # For local adapter, return just the folder name (no path prefix)
        # In full implementation, this would load from registry for modal
        return ref_to_local_dir(processor_ref)
    
    def _download_all_outputs(self, outputs: List[Dict[str, Any]], save_dir: str) -> None:
        """Download all outputs to save_dir, mirroring world paths."""
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        
        for output in outputs:
            if not isinstance(output, dict) or 'path' not in output:
                continue
            
            world_path = output['path']
            # Create relative path from world path (strip leading /)
            rel_path = world_path.lstrip('/')
            local_path = save_path / rel_path
            
            # Create parent directories
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Download from artifact store
            try:
                content = artifact_store.get_bytes(world_path)
                with open(local_path, 'wb') as f:
                    f.write(content)
                if not self.options.get('json'):
                    self.stdout.write(f"Downloaded {world_path} -> {local_path}")
            except Exception as e:
                self.stderr.write(f"Failed to download {world_path}: {e}")
    
    def _download_first_output(self, outputs: List[Dict[str, Any]], save_path: str) -> None:
        """Download only the first output to save_path."""
        if not outputs or not isinstance(outputs[0], dict) or 'path' not in outputs[0]:
            return
        
        output = outputs[0]
        world_path = output['path']
        local_path = Path(save_path)
        
        # Create parent directories
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download from artifact store
        try:
            content = artifact_store.get_bytes(world_path)
            with open(local_path, 'wb') as f:
                f.write(content)
            if not self.options.get('json'):
                self.stdout.write(f"Downloaded first output {world_path} -> {local_path}")
        except Exception as e:
            self.stderr.write(f"Failed to download {world_path}: {e}")
    
    def handle(self, *args, **options):
        """Execute the command."""
        self.options = options
        
        # Validate write-prefix
        write_prefix = options['write_prefix']
        if not write_prefix.endswith('/'):
            self.stderr.write("Error: --write-prefix must end with /")
            sys.exit(1)
        
        # Parse inputs
        try:
            inputs = json.loads(options['inputs_json'])
        except json.JSONDecodeError as e:
            self.stderr.write(f"Error: Invalid --inputs-json: {e}")
            sys.exit(1)
        
        # Materialize attachments
        attachment_map = {}
        if options.get('attach'):
            attachment_map = self.materialize_attachments(options['attach'])
        
        # Rewrite $attach references in inputs
        if attachment_map:
            inputs = self.rewrite_attach_references(inputs, attachment_map)
            if not options.get('json'):
                self.stdout.write(f"Rewritten inputs: {json.dumps(inputs, indent=2)}")
        
        # Get or create plan if specified
        plan = None
        execution = None
        if options.get('plan'):
            plan, created = Plan.objects.get_or_create(
                key=options['plan'],
                defaults={'reserved_micro': 100000, 'spent_micro': 0}
            )
            if created and not options.get('json'):
                self.stdout.write(f"Created plan: {plan.key}")
            
            # Create transition and execution
            with transaction.atomic():
                transition = Transition.objects.create(
                    plan=plan,
                    key=f"run-{options['ref']}",
                    status='running'
                )
                execution = Execution.objects.create(
                    transition=transition,
                    attempt_idx=1
                )
        
        try:
            # Get adapter
            adapter = self.get_adapter(options['adapter'])
            
            # Get image digest
            image_digest = self.get_image_digest(options['ref'])
            
            # Pass execution_id to adapter via adapter_opts
            adapter_opts = json.loads(options.get('adapter_opts_json') or '{}')
            if execution:
                adapter_opts['execution_id'] = str(execution.id)
            
            # Invoke processor
            result = adapter.invoke(
                processor_ref=options['ref'],
                image_digest=image_digest,
                inputs_json=json.dumps(inputs),
                write_prefix=write_prefix,
                plan_id=plan.key if plan else 'no-plan',
                timeout_s=options.get('timeout'),
                secrets=['OPENAI_API_KEY'] if 'llm' in options['ref'] else None,
                adapter_opts_json=json.dumps(adapter_opts),
                build=options.get('build', False)
            )
            
            # Write determinism receipt if execution exists and successful
            if execution and result.get('status') == 'success':
                # Derive output_cids from canonical outputs
                outputs = result.get('outputs') or []
                output_cids = [o['cid'] for o in outputs if isinstance(o, dict) and 'cid' in o]
                
                env_fp = result.get('env_fingerprint') or (result.get('meta') or {}).get('env_fingerprint', '')
                determinism_uri = write_determinism_receipt(
                    plan=plan,
                    execution=execution,
                    seed=result.get('seed', 0),
                    memo_key=result.get('memo_key', ''),
                    env_fingerprint=env_fp,
                    output_cids=output_cids
                )
                
                # Settle execution with canonical output metadata
                settle_execution_success(
                    plan=plan,
                    execution=execution,
                    estimate_hi_micro=result.get('estimate_micro', 1000),
                    actual_micro=result.get('actual_micro', 500),
                    seed=result.get('seed', 0),
                    memo_key=result.get('memo_key', ''),
                    env_fingerprint=env_fp,
                    output_cids=output_cids,
                    # Pass canonical output metadata
                    outputs_index=result.get('index_path'),
                    outputs_count=len(outputs) if outputs else 0
                )
                
                result['determinism_uri'] = determinism_uri
            
            # Download outputs if requested
            if result.get('status') == 'success' and result.get('outputs'):
                if options.get('save_dir'):
                    self._download_all_outputs(result['outputs'], options['save_dir'])
                elif options.get('save_first'):
                    self._download_first_output(result['outputs'], options['save_first'])
            
            # Output result
            if options.get('json'):
                self.stdout.write(json.dumps(result, indent=2))
            else:
                if result.get('status') == 'success':
                    self.stdout.write("Processor completed successfully")
                    if result.get('outputs'):
                        self.stdout.write(f"Outputs: {json.dumps(result['outputs'], indent=2)}")
                    if result.get('index_path'):
                        self.stdout.write(f"Index: {result['index_path']}")
                else:
                    self.stderr.write(f"Processor failed: {result.get('error', 'Unknown error')}")
                    sys.exit(1)
                    
        except Exception as e:
            if execution:
                # Settle as failure
                settle_execution_failure(
                    plan=plan,
                    execution=execution,
                    estimate_hi_micro=1000,
                    metered_actual_micro=100,
                    reason=str(e)
                )
            
            self.stderr.write(f"Error: {e}")
            sys.exit(1)