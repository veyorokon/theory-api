"""
Tests for Ollama provider via LiteLLM.

Mocks litellm.completion calls to avoid network dependencies in CI.
"""
import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.core.providers import get_llm_provider
from apps.core.llm import LLMReply


class TestLiteLLMOllamaProviderCommand(TestCase):
    """Test Ollama provider via LiteLLM management command."""
    
    @mock.patch('litellm.completion')
    def test_command_litellm_ollama_provider(self, mock_completion):
        """Management command should work with LiteLLM Ollama provider."""
        # Mock successful response
        mock_response = mock.Mock()
        mock_response.choices = [mock.Mock()]
        mock_response.choices[0].message = mock.Mock()
        mock_response.choices[0].message.content = "Ollama response here"
        mock_response.usage = mock.Mock()
        mock_response.usage.prompt_tokens = 4
        mock_response.usage.completion_tokens = 4
        mock_completion.return_value = mock_response
        
        out = StringIO()
        call_command('hello_llm', provider='litellm', model='ollama/qwen2.5:0.5b', 
                    api_base='http://127.0.0.1:11434', prompt='test ollama', stdout=out)
        
        output = out.getvalue()
        self.assertEqual(output.strip(), "Ollama response here")
    
    @mock.patch('litellm.completion')
    def test_command_litellm_ollama_json_output(self, mock_completion):
        """Command should output JSON with LiteLLM Ollama provider."""
        # Mock response
        mock_response = mock.Mock()
        mock_response.choices = [mock.Mock()]
        mock_response.choices[0].message = mock.Mock()
        mock_response.choices[0].message.content = "JSON test response"
        mock_response.usage = mock.Mock()
        mock_response.usage.prompt_tokens = 4
        mock_response.usage.completion_tokens = 4
        mock_completion.return_value = mock_response
        
        out = StringIO()
        call_command('hello_llm', provider='litellm', model='ollama/qwen2.5:0.5b',
                    api_base='http://127.0.0.1:11434', prompt='json test', json=True, stdout=out)
        
        output = out.getvalue()
        data = json.loads(output)
        
        self.assertEqual(data["text"], "JSON test response")
        self.assertEqual(data["provider"], "litellm")
        self.assertEqual(data["model"], "ollama/qwen2.5:0.5b")
        self.assertIn("tokens_in", data["usage"])
    
    @mock.patch('litellm.completion')
    def test_command_litellm_ollama_daemon_down(self, mock_completion):
        """Command should handle Ollama daemon unavailable gracefully."""
        # Mock connection error for Ollama via LiteLLM
        mock_completion.side_effect = Exception("Connection refused")
        
        err = StringIO()
        
        # Command should exit with code 1 when Ollama daemon is down
        with self.assertRaises(SystemExit) as cm:
            call_command('hello_llm', provider='litellm', model='ollama/qwen2.5:0.5b', 
                        api_base='http://127.0.0.1:11434', stderr=err)
        
        self.assertEqual(cm.exception.code, 1)
        error_output = err.getvalue()
        self.assertIn("Error:", error_output)
        self.assertIn("Ollama daemon unreachable", error_output)