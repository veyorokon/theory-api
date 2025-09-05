"""
Tests for Ollama provider.

Mocks HTTP calls to local Ollama daemon to avoid dependency on running service.
"""
import json
import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
import requests

from apps.core.providers.ollama import OllamaProvider
from apps.core.llm import LLMReply


class TestOllamaProvider(TestCase):
    """Test Ollama provider implementation."""
    
    def setUp(self):
        """Set up test environment."""
        self.provider = OllamaProvider()
    
    def test_init_default_host(self):
        """OllamaProvider should use default host."""
        provider = OllamaProvider()
        self.assertEqual(provider.host, "http://localhost:11434")
    
    def test_init_custom_host(self):
        """OllamaProvider should accept custom host."""
        provider = OllamaProvider(host="http://custom:8080")
        self.assertEqual(provider.host, "http://custom:8080")
    
    def test_init_from_env_var(self):
        """OllamaProvider should read host from environment."""
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "http://env-host:9000"}):
            provider = OllamaProvider()
            self.assertEqual(provider.host, "http://env-host:9000")
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    @mock.patch('apps.core.providers.ollama.requests.Session.post')
    def test_chat_success(self, mock_post, mock_get):
        """chat() should return LLMReply with Ollama response."""
        
        # Mock daemon availability check
        mock_get.return_value.status_code = 200
        
        # Mock successful Ollama response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Hello from Ollama!",
            "prompt_eval_count": 5,
            "eval_count": 4,
            "done": True
        }
        mock_post.return_value = mock_response
        
        reply = self.provider.chat("Hello world", model="qwen2.5:0.5b")
        
        # Verify daemon check
        mock_get.assert_called_once_with(
            "http://localhost:11434/api/version", 
            timeout=5
        )
        
        # Verify generation request
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], "http://localhost:11434/api/generate")
        
        request_data = call_args[1]['json']
        self.assertEqual(request_data['model'], "qwen2.5:0.5b")
        self.assertEqual(request_data['prompt'], "Hello world")
        self.assertFalse(request_data['stream'])
        
        # Verify response
        self.assertIsInstance(reply, LLMReply)
        self.assertEqual(reply.text, "Hello from Ollama!")
        self.assertEqual(reply.provider, "ollama")
        self.assertEqual(reply.model, "qwen2.5:0.5b")
        self.assertEqual(reply.usage["tokens_in"], 5)
        self.assertEqual(reply.usage["tokens_out"], 4)
        self.assertEqual(reply.usage["usd_micros"], 0)  # Local is free
        self.assertGreaterEqual(reply.usage["latency_ms"], 0)  # Latency is calculated
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    @mock.patch('apps.core.providers.ollama.requests.Session.post')
    def test_chat_default_model(self, mock_post, mock_get):
        """chat() should use default model when none specified."""
        mock_get.return_value.status_code = 200
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "response": "Default model response",
            "done": True
        }
        mock_post.return_value = mock_response
        
        reply = self.provider.chat("test prompt")
        
        # Should use default model
        request_data = mock_post.call_args[1]['json']
        self.assertEqual(request_data['model'], "qwen2.5:0.5b")
        self.assertEqual(reply.model, "qwen2.5:0.5b")
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    def test_chat_daemon_unavailable(self, mock_get):
        """chat() should raise RequestException when daemon unavailable."""
        mock_get.side_effect = requests.RequestException("Connection refused")
        
        with self.assertRaises(requests.RequestException) as cm:
            self.provider.chat("test prompt")
        
        error_msg = str(cm.exception)
        self.assertIn("Ollama daemon unavailable", error_msg)
        self.assertIn("ollama serve", error_msg)
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    @mock.patch('apps.core.providers.ollama.requests.Session.post')
    def test_chat_model_not_found(self, mock_post, mock_get):
        """chat() should handle model not found error."""
        mock_get.return_value.status_code = 200
        
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "error": "model not found: unknown-model"
        }
        mock_post.return_value = mock_response
        
        with self.assertRaises(ValueError) as cm:
            self.provider.chat("test", model="unknown-model")
        
        error_msg = str(cm.exception)
        self.assertIn("Model 'unknown-model' not found", error_msg)
        self.assertIn("ollama pull", error_msg)
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    @mock.patch('apps.core.providers.ollama.requests.Session.post')
    def test_chat_other_api_error(self, mock_post, mock_get):
        """chat() should handle other API errors."""
        mock_get.return_value.status_code = 200
        
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "error": "Some other error occurred"
        }
        mock_post.return_value = mock_response
        
        with self.assertRaises(ValueError) as cm:
            self.provider.chat("test")
        
        self.assertIn("Ollama error: Some other error occurred", str(cm.exception))
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    @mock.patch('apps.core.providers.ollama.requests.Session.post')
    def test_chat_http_404_model_not_found(self, mock_post, mock_get):
        """chat() should handle HTTP 404 as model not found."""
        mock_get.return_value.status_code = 200
        
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError("Not Found")
        mock_post.return_value = mock_response
        
        # Mock the model list response
        with mock.patch.object(self.provider, '_get_available_models', return_value="qwen2.5:0.5b, llama3:8b"):
            with self.assertRaises(ValueError) as cm:
                self.provider.chat("test", model="missing-model")
        
            error_msg = str(cm.exception)
            self.assertIn("Model 'missing-model' not found", error_msg)
            self.assertIn("qwen2.5:0.5b, llama3:8b", error_msg)
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    def test_get_available_models_success(self, mock_get):
        """_get_available_models should return model list."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "qwen2.5:0.5b"},
                {"name": "llama3:8b"}
            ]
        }
        mock_get.return_value = mock_response
        
        models = self.provider._get_available_models()
        self.assertEqual(models, "qwen2.5:0.5b, llama3:8b")
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    def test_get_available_models_empty(self, mock_get):
        """_get_available_models should handle empty model list."""
        mock_response = mock.Mock()
        mock_response.json.return_value = {"models": []}
        mock_get.return_value = mock_response
        
        models = self.provider._get_available_models()
        self.assertIn("none", models)
        self.assertIn("ollama pull", models)
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    def test_get_available_models_daemon_down(self, mock_get):
        """_get_available_models should handle daemon unavailable."""
        mock_get.side_effect = requests.RequestException("Connection refused")
        
        models = self.provider._get_available_models()
        self.assertIn("unable to list", models)
        self.assertIn("daemon may be down", models)
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    @mock.patch('apps.core.providers.ollama.requests.Session.post')
    def test_logging_behavior(self, mock_post, mock_get):
        """Ollama provider should emit structured logs."""
        mock_get.return_value.status_code = 200
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "response": "Test response",
            "prompt_eval_count": 3,
            "eval_count": 2
        }
        mock_post.return_value = mock_response
        
        with self.assertLogs('apps.core.providers.ollama', level='INFO') as log:
            self.provider.chat("test", model="qwen2.5:0.5b")
            
            messages = [record.message for record in log.records]
            
            # Should log start and finish
            self.assertTrue(any("ollama.start" in msg for msg in messages))
            self.assertTrue(any("ollama.finish" in msg for msg in messages))
            
            # Should include extra data
            start_record = next(r for r in log.records if "ollama.start" in r.message)
            self.assertTrue(hasattr(start_record, 'model'))
            self.assertEqual(start_record.model, "qwen2.5:0.5b")


class TestOllamaProviderCommand(TestCase):
    """Test Ollama provider through management command."""
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    @mock.patch('apps.core.providers.ollama.requests.Session.post')
    def test_command_ollama_provider(self, mock_post, mock_get):
        """Command should work with Ollama provider when mocked."""
        mock_get.return_value.status_code = 200
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "response": "Ollama response here",
            "done": True
        }
        mock_post.return_value = mock_response
        
        out = StringIO()
        call_command('hello_llm', provider='ollama', model='qwen2.5:0.5b',
                    prompt='test ollama', stdout=out)
        
        output = out.getvalue()
        self.assertEqual(output.strip(), "Ollama response here")
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    @mock.patch('apps.core.providers.ollama.requests.Session.post')
    def test_command_ollama_json_output(self, mock_post, mock_get):
        """Command should output JSON with Ollama provider."""
        mock_get.return_value.status_code = 200
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "response": "JSON test from Ollama",
            "prompt_eval_count": 4,
            "eval_count": 4
        }
        mock_post.return_value = mock_response
        
        out = StringIO()
        call_command('hello_llm', provider='ollama', json=True, stdout=out)
        
        output = out.getvalue()
        data = json.loads(output)
        
        self.assertEqual(data["text"], "JSON test from Ollama")
        self.assertEqual(data["provider"], "ollama")
        self.assertEqual(data["model"], "qwen2.5:0.5b")
        self.assertEqual(data["usage"]["tokens_in"], 4)
        self.assertEqual(data["usage"]["tokens_out"], 4)
    
    @mock.patch('apps.core.providers.ollama.requests.Session.get')
    def test_command_ollama_daemon_down(self, mock_get):
        """Command should handle Ollama daemon unavailable gracefully."""
        mock_get.side_effect = requests.RequestException("Connection refused")
        
        err = StringIO()
        
        # Command should exit with code 1 when Ollama daemon is down
        with self.assertRaises(SystemExit) as cm:
            call_command('hello_llm', provider='ollama', stderr=err)
        
        self.assertEqual(cm.exception.code, 1)
        error_output = err.getvalue()
        self.assertIn("Unexpected error:", error_output)
        self.assertIn("daemon unavailable", error_output)