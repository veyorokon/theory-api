"""
Hello LLM management command - minimal LLM processor demo.

Demonstrates Theory's LLM provider interface with deterministic mock implementation.
"""
import json
from dataclasses import asdict

from django.core.management.base import BaseCommand

from apps.core.llm import MockLLM


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
    
    def handle(self, *args, **options):
        """Execute the command."""
        llm = MockLLM()
        reply = llm.chat(options['prompt'])
        
        if options.get('json'):
            self.stdout.write(json.dumps(asdict(reply), indent=2))
        else:
            self.stdout.write(reply.text)