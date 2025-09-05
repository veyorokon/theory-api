"""
Hello LLM management command - minimal LLM processor demo.

Demonstrates Theory's LLM provider interface with deterministic mock implementation.
"""
import json
import sys
from dataclasses import asdict

from django.core.management.base import BaseCommand

from apps.core.providers import get_llm_provider


class Command(BaseCommand):
    """Run a minimal LLM hello world using a mock adapter."""
    
    help = "Run a minimal LLM hello world using a mock adapter"
    
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
            help='Emit JSON reply instead of plain text'
        )
        parser.add_argument(
            '--provider',
            choices=['mock', 'openai', 'ollama'],
            default='mock',
            help='LLM provider to use (default: mock)'
        )
        parser.add_argument(
            '--model',
            help='Model name (uses provider default if not specified)'
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        # Default models per provider
        default_models = {
            'mock': 'mock',
            'openai': 'gpt-4o-mini', 
            'ollama': 'qwen2.5:0.5b'
        }
        
        try:
            provider = get_llm_provider(options['provider'])
            model = options.get('model') or default_models[options['provider']]
            
            reply = provider.chat(options['prompt'], model=model)
            
            if options.get('json'):
                self.stdout.write(json.dumps(asdict(reply), indent=2))
            else:
                self.stdout.write(reply.text)
                
        except ValueError as e:
            self.stderr.write(f"Error: {e}")
            sys.exit(1)
        except Exception as e:
            self.stderr.write(f"Unexpected error: {e}")
            sys.exit(1)