# Vulture allowlist for dynamic lookups that static analysis can't see.

# Django management commands discovered by name
apps.core.management.commands.run_processor.Command
apps.core.management.commands.sync_modal.Command
apps.core.management.commands.docs_export.Command

# Django signal receivers referenced by string path
apps.core.apps.ready

# Modal entry function name resolved at runtime
modal_app._exec

# Adapter entrypoints invoked via registry/spec
apps.core.adapters.modal_adapter.ModalAdapter.invoke
apps.core.adapters.local_adapter.LocalAdapter.invoke
apps.core.adapters.mock_adapter.MockAdapter.invoke

# WSGI/ASGI modules loaded by server runners
backend.wsgi.application
backend.asgi.application

# Django model fields that might appear unused but are accessed via ORM
apps.runtime.models.Execution.determinism_uri
apps.runtime.models.Transition.memo_hit
apps.plans.models.Plan.budget_micro

# Processors invoked dynamically
apps.core.processors.llm_litellm.main.main

# Registry loader functions
apps.core.registry.loader.snapshot_for_ref
apps.core.registry.loader.get_secrets_present_for_spec

# Service functions called from management commands
apps.runtime.services.settle_execution_success
apps.runtime.services.settle_execution_failure

# Utility functions used in templates or dynamic contexts
apps.core.utils.processor_ref.registry_path
apps.core.utils.env_fingerprint.compose_env_fingerprint
apps.core.utils.worldpath.canonicalize_worldpath

# Error codes used as string constants
apps.core.errors.ERR_IMAGE_UNPINNED
apps.core.errors.ERR_MISSING_SECRET
apps.core.errors.ERR_ADAPTER_INVOCATION
apps.core.errors.ERR_PREFIX_TEMPLATE
apps.core.errors.ERR_OUTPUT_DUPLICATE

# Test utilities that might not be directly imported
apps.core.tests.test_modal_adapter_parity
apps.core.tests.test_predicates
apps.core.tests.test_litellm_provider_isolation

# Context manager protocol requires these parameters (unused is expected)
self_nonlocal  # Context manager self parameter
exc_type  # Context manager exception type parameter

# Function parameters that may be unused in some implementations
required_secret_names  # Modal adapter parameter for future secret handling
