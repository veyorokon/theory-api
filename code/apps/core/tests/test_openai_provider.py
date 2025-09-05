"""
Tests for OpenAI provider.

Mocks HTTP calls to avoid network dependencies and API costs in CI.
"""
import json
import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
import requests

from apps.core.providers.openai_api import OpenAIProvider
from apps.core.llm import LLMReply


class TestOpenAIProvider(TestCase):
    """Test OpenAI provider implementation."""
    
    def setUp(self):
        """Set up test environment."""
        # Mock API key for testing
        self.api_key = "test-key-123"
        self.provider = OpenAIProvider(api_key=self.api_key)
    
    def test_init_with_api_key(self):
        """OpenAIProvider should initialize with provided API key."""
        provider = OpenAIProvider(api_key="custom-key")
        self.assertEqual(provider.api_key, "custom-key")
        self.assertEqual(provider.base_url, "https://api.openai.com/v1")
    
    def test_init_from_env_var(self):
        """OpenAIProvider should read API key from environment."""
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            provider = OpenAIProvider()
            self.assertEqual(provider.api_key, "env-key")
    
    def test_init_missing_api_key_raises(self):
        """OpenAIProvider should raise ValueError if no API key."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as cm:
                OpenAIProvider()
            
            self.assertIn("OpenAI API key required", str(cm.exception))
            self.assertIn("OPENAI_API_KEY", str(cm.exception))
    
    @mock.patch('apps.core.providers.openai_api.requests.Session.post')
    def test_chat_success(self, mock_post):
        """chat() should return LLMReply with OpenAI response."""
        
        # Mock successful OpenAI response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello there!"}}],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5
            }
        }
        mock_post.return_value = mock_response
        
        reply = self.provider.chat("Hello world", model="gpt-4o-mini")
        
        # Verify request
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], "https://api.openai.com/v1/chat/completions")
        
        request_data = call_args[1]['json']
        self.assertEqual(request_data['model'], "gpt-4o-mini")
        self.assertEqual(request_data['messages'], [{"role": "user", "content": "Hello world"}])
        
        # Verify response
        self.assertIsInstance(reply, LLMReply)
        self.assertEqual(reply.text, "Hello there!")
        self.assertEqual(reply.provider, "openai")
        self.assertEqual(reply.model, "gpt-4o-mini")
        self.assertEqual(reply.usage["tokens_in"], 3)
        self.assertEqual(reply.usage["tokens_out"], 2)
        self.assertGreaterEqual(reply.usage["latency_ms"], 0)  # Latency is calculated
    
    @mock.patch('apps.core.providers.openai_api.requests.Session.post')
    def test_chat_default_model(self, mock_post):
        """chat() should use default model when none specified."""
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Response"}}],
            "usage": {}
        }
        mock_post.return_value = mock_response
        
        reply = self.provider.chat("test prompt")
        
        # Should use default model
        request_data = mock_post.call_args[1]['json']
        self.assertEqual(request_data['model'], "gpt-4o-mini")
        self.assertEqual(reply.model, "gpt-4o-mini")
    
    @mock.patch('apps.core.providers.openai_api.requests.Session.post')
    def test_chat_http_error(self, mock_post):
        """chat() should raise RequestException on HTTP error."""
        mock_post.side_effect = requests.RequestException("Network error")
        
        with self.assertRaises(requests.RequestException):
            self.provider.chat("test prompt")
    
    @mock.patch('apps.core.providers.openai_api.requests.Session.post')
    def test_chat_api_error_response(self, mock_post):
        """chat() should handle API error responses."""
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = requests.HTTPError("Bad Request")
        mock_post.return_value = mock_response
        
        with self.assertRaises(requests.HTTPError):
            self.provider.chat("test prompt")
    
    def test_estimate_cost_micros(self):
        """_estimate_cost_micros should calculate reasonable estimates."""
        usage_data = {"prompt_tokens": 1000, "completion_tokens": 500}
        
        # Test gpt-4o-mini pricing (should be cheap)
        cost = self.provider._estimate_cost_micros(usage_data, "gpt-4o-mini")
        self.assertGreater(cost, 0)
        self.assertLess(cost, 10000)  # Should be less than 1 cent
        
        # Test gpt-4 pricing (should be more expensive)
        cost_gpt4 = self.provider._estimate_cost_micros(usage_data, "gpt-4")
        self.assertGreater(cost_gpt4, cost)
    
    @mock.patch('apps.core.providers.openai_api.requests.Session.post')
    def test_logging_behavior(self, mock_post):
        """OpenAI provider should emit structured logs."""
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2}
        }
        mock_post.return_value = mock_response
        
        with self.assertLogs('apps.core.providers.openai_api', level='INFO') as log:
            self.provider.chat("test", model="gpt-4o-mini")
            
            messages = [record.message for record in log.records]
            
            # Should log start and finish
            self.assertTrue(any("openai.start" in msg for msg in messages))
            self.assertTrue(any("openai.finish" in msg for msg in messages))
            
            # Should include extra data
            start_record = next(r for r in log.records if "openai.start" in r.message)
            self.assertTrue(hasattr(start_record, 'model'))
            self.assertEqual(start_record.model, "gpt-4o-mini")


class TestOpenAIProviderCommand(TestCase):
    """Test OpenAI provider through management command."""
    
    @mock.patch('apps.core.providers.openai_api.requests.Session.post')
    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_command_openai_provider(self, mock_post):
        """Command should work with OpenAI provider when mocked."""
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OpenAI response here"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 3}
        }
        mock_post.return_value = mock_response
        
        out = StringIO()
        call_command('hello_llm', provider='openai', model='gpt-4o-mini', 
                    prompt='test openai', stdout=out)
        
        output = out.getvalue()
        self.assertEqual(output.strip(), "OpenAI response here")
    
    @mock.patch('apps.core.providers.openai_api.requests.Session.post') 
    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_command_openai_json_output(self, mock_post):
        """Command should output JSON with OpenAI provider."""
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "JSON test"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2}
        }
        mock_post.return_value = mock_response
        
        out = StringIO()
        call_command('hello_llm', provider='openai', json=True, stdout=out)
        
        output = out.getvalue()
        data = json.loads(output)
        
        self.assertEqual(data["text"], "JSON test")
        self.assertEqual(data["provider"], "openai")
        self.assertEqual(data["model"], "gpt-4o-mini")
        self.assertIn("tokens_in", data["usage"])
    
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_command_openai_missing_key(self):
        """Command should handle missing OpenAI API key gracefully."""
        err = StringIO()
        
        # Command should exit with code 1 when OpenAI key is missing
        with self.assertRaises(SystemExit) as cm:
            call_command('hello_llm', provider='openai', stderr=err)
        
        self.assertEqual(cm.exception.code, 1)
        error_output = err.getvalue()
        self.assertIn("Error:", error_output)
        self.assertIn("required", error_output)