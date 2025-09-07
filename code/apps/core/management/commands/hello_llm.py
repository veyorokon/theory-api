"""
Hello LLM management command - minimal LLM processor demo.

Demonstrates Theory's LLM provider interface with streaming support.
"""
import json
import sys
from dataclasses import asdict

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.providers import get_llm_provider


class Command(BaseCommand):
    """Run LLM hello world with multiple providers and streaming support."""
    
    help = "Run LLM hello world with multiple providers and streaming support"
    
    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            '--prompt', 
            required=False, 
            default='hello world',
            help='Input prompt for the LLM (default: "hello world")'
        )
        parser.add_argument(
            '--json', 
            action='store_true', 
            help='Emit JSON reply instead of plain text (not available with --stream)'
        )
        parser.add_argument(
            '--provider',
            choices=['mock', 'litellm'],
            default=None,
            help='LLM provider to use (default from settings or mock)'
        )
        parser.add_argument(
            '--model',
            help='Model name (e.g., openai/gpt-4o-mini, ollama/qwen3:0.6b)'
        )
        parser.add_argument(
            '--api-base',
            help='API base URL (e.g., http://127.0.0.1:11434 for Ollama)'
        )
        parser.add_argument(
            '--stream',
            action='store_true',
            help='Stream tokens to stdout in real-time (no JSON in stream mode)'
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        # Get defaults from Django settings
        llm_settings = getattr(settings, 'LLM_SETTINGS', {})
        
        # Resolve provider, model, and api_base with fallbacks
        provider_name = (
            options.get('provider') or 
            llm_settings.get('default_provider', 'mock')
        )
        
        
        model = (
            options.get('model') or 
            llm_settings.get('default_model', 'openai/gpt-4o-mini')
        )
        
        api_base = (
            options.get('api_base') or 
            llm_settings.get('api_base') or 
            None
        )
        
        try:
            # Get provider instance with configuration
            provider = get_llm_provider(
                provider_name, 
                model_default=model, 
                api_base=api_base
            )
            
            if options.get('stream'):
                # Stream mode - output tokens as they arrive
                if options.get('json'):
                    self.stderr.write("Warning: JSON output not available in stream mode\n")
                
                try:
                    for chunk in provider.stream_chat(options['prompt'], model=model):
                        self.stdout.write(chunk, ending='')
                        self.stdout.flush()
                    self.stdout.write('')  # Final newline
                except AttributeError:
                    self.stderr.write(
                        f"Error: Provider '{provider_name}' does not support streaming"
                    )
                    sys.exit(1)
            else:
                # Non-stream mode - regular chat
                reply = provider.chat(options['prompt'], model=model)
                
                if options.get('json'):
                    self.stdout.write(json.dumps(asdict(reply), indent=2))
                else:
                    self.stdout.write(reply.text)
                    
        except ValueError as e:
            self.stderr.write(f"Error: {e}")
            sys.exit(1)
        except RuntimeError as e:
            # Friendly errors from LiteLLMProvider
            self.stderr.write(f"Error: {e}")
            sys.exit(1)
        except Exception as e:
            self.stderr.write(f"Unexpected error: {e}")
            sys.exit(1)