# Control-plane only integrations - no provider SDKs
# Provider SDKs (litellm, replicate) live in processor containers

from .secret_resolver import resolve_secret
from .types import ProcessorResult, OutputItem, ProviderRunner

__all__ = ["resolve_secret", "ProcessorResult", "OutputItem", "ProviderRunner"]
