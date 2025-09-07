"""
Tests for OpenAI provider via LiteLLM.

Mocks litellm.completion calls to avoid network dependencies and API costs in CI.
"""
import json
import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.core.providers import get_llm_provider
from apps.core.llm import LLMReply


class TestLiteLLMOpenAIProviderCommand(TestCase):
    """Test OpenAI provider via LiteLLM management command."""
    
    @mock.patch('litellm.completion')
    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_command_litellm_openai_provider(self, mock_completion):
        """Management command should work with LiteLLM OpenAI provider."""
        # Mock successful response
        mock_response = mock.Mock()
        mock_response.choices = [mock.Mock()]
        mock_response.choices[0].message = mock.Mock()
        mock_response.choices[0].message.content = "OpenAI response here"
        mock_response.usage = mock.Mock()
        mock_response.usage.prompt_tokens = 3
        mock_response.usage.completion_tokens = 3
        mock_completion.return_value = mock_response
        
        out = StringIO()
        call_command('hello_llm', provider='litellm', model='openai/gpt-4o-mini', 
                    prompt='test openai', stdout=out)
        
        output = out.getvalue()
        self.assertEqual(output.strip(), "OpenAI response here")
    
    @mock.patch('litellm.completion') 
    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_command_litellm_openai_json_output(self, mock_completion):
        """Command should output JSON with LiteLLM OpenAI provider."""
        # Mock response
        mock_response = mock.Mock()
        mock_response.choices = [mock.Mock()]
        mock_response.choices[0].message = mock.Mock()
        mock_response.choices[0].message.content = "JSON test response"
        mock_response.usage = mock.Mock()
        mock_response.usage.prompt_tokens = 2
        mock_response.usage.completion_tokens = 3
        mock_completion.return_value = mock_response
        
        out = StringIO()
        call_command('hello_llm', provider='litellm', model='openai/gpt-4o-mini',
                    prompt='json test', json=True, stdout=out)
        
        output = out.getvalue()
        data = json.loads(output)
        
        self.assertEqual(data["text"], "JSON test response")
        self.assertEqual(data["provider"], "litellm")
        self.assertEqual(data["model"], "openai/gpt-4o-mini")
        self.assertIn("tokens_in", data["usage"])
    
    @mock.patch('litellm.completion')
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_command_litellm_openai_missing_key(self, mock_completion):
        """Command should handle missing OpenAI API key gracefully."""
        # Mock generic exception - our provider will wrap in friendly RuntimeError
        mock_completion.side_effect = Exception("401: Invalid API key provided")
        
        err = StringIO()
        
        # Command should exit with code 1 when OpenAI key is missing
        with self.assertRaises(SystemExit) as cm:
            call_command('hello_llm', provider='litellm', model='openai/gpt-4o-mini', stderr=err)
        
        self.assertEqual(cm.exception.code, 1)
        error_output = err.getvalue()
        self.assertIn("Error:", error_output)
        self.assertIn("OPENAI_API_KEY", error_output)
        self.assertIn("missing or invalid", error_output)