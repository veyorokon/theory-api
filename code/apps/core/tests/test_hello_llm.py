"""
Tests for LLM Hello World functionality.

Covers MockLLM provider, LLMReply dataclass, management command, and logging.
"""
import json
import logging
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.core.llm import MockLLM, LLMReply


class TestMockLLM(TestCase):
    """Test the MockLLM provider implementation."""
    
    def test_chat_returns_reply_object(self):
        """MockLLM.chat() should return LLMReply instance."""
        llm = MockLLM()
        reply = llm.chat("hello")
        
        assert isinstance(reply, LLMReply)
        assert isinstance(reply.text, str)
        assert reply.provider == "mock"
        assert isinstance(reply.usage, dict)
    
    def test_chat_echoes_prompt(self):
        """MockLLM should echo the input prompt in response."""
        llm = MockLLM()
        reply = llm.chat("hello there")
        
        assert "hello there" in reply.text
        assert reply.text.startswith("Hello from MockLLM!")
    
    def test_chat_strips_whitespace(self):
        """MockLLM should strip whitespace from prompt."""
        llm = MockLLM()
        reply = llm.chat("  hello world  ")
        
        assert "hello world" in reply.text
        assert "  hello world  " not in reply.text
    
    def test_usage_tracking(self):
        """MockLLM should populate usage statistics."""
        llm = MockLLM()
        reply = llm.chat("hello world")
        
        assert "prompt_tokens" in reply.usage
        assert "completion_tokens" in reply.usage
        assert reply.usage["prompt_tokens"] > 0
        assert reply.usage["completion_tokens"] > 0


class TestLLMReply(TestCase):
    """Test the LLMReply dataclass."""
    
    def test_default_values(self):
        """LLMReply should have sensible defaults."""
        reply = LLMReply(text="hello")
        
        assert reply.text == "hello"
        assert reply.provider == "mock"
        assert reply.usage == {}
    
    def test_custom_values(self):
        """LLMReply should accept custom provider and usage."""
        usage = {"tokens": 100}
        reply = LLMReply(text="hello", provider="custom", usage=usage)
        
        assert reply.text == "hello"
        assert reply.provider == "custom"
        assert reply.usage == usage


class TestHelloLLMCommand(TestCase):
    """Test the hello_llm management command."""
    
    def test_command_default_prompt(self):
        """Command should work with default prompt."""
        out = StringIO()
        call_command('hello_llm', stdout=out)
        output = out.getvalue()
        
        self.assertIn("hello world", output)
        self.assertIn("Hello from MockLLM!", output)
    
    def test_command_custom_prompt(self):
        """Command should accept custom prompt."""
        out = StringIO()
        call_command('hello_llm', prompt='hi there', stdout=out)
        output = out.getvalue()
        
        self.assertIn("hi there", output)
        self.assertIn("Hello from MockLLM!", output)
    
    def test_command_json_output(self):
        """Command should output JSON when --json flag is used."""
        out = StringIO()
        call_command('hello_llm', prompt='test', json=True, stdout=out)
        output = out.getvalue()
        
        # Should be valid JSON
        data = json.loads(output)
        self.assertIsInstance(data, dict)
        self.assertIn("text", data)
        self.assertIn("provider", data)
        self.assertIn("usage", data)
        self.assertIn("test", data["text"])
        self.assertEqual(data["provider"], "mock")
    
    def test_command_json_structure(self):
        """Command JSON output should have expected structure."""
        out = StringIO()
        call_command('hello_llm', prompt='hello', json=True, stdout=out)
        output = out.getvalue()
        
        data = json.loads(output)
        
        # Verify all expected fields are present
        expected_fields = {"text", "provider", "usage"}
        self.assertEqual(set(data.keys()), expected_fields)


class TestLogging(TestCase):
    """Test logging behavior of MockLLM."""
    
    def test_start_finish_logs(self):
        """MockLLM should log start and finish events."""
        with self.assertLogs('apps.core.llm', level='INFO') as log:
            llm = MockLLM()
            llm.chat("hello")
            
            messages = [record.message for record in log.records]
            
            # Should log both start and finish
            self.assertTrue(any("mockllm.start" in msg for msg in messages))
            self.assertTrue(any("mockllm.finish" in msg for msg in messages))
    
    def test_log_extra_data(self):
        """MockLLM should include extra data in log records."""
        with self.assertLogs('apps.core.llm', level='INFO') as log:
            llm = MockLLM()
            llm.chat("hello world")
            
            # Find the start log record
            start_record = None
            finish_record = None
            
            for record in log.records:
                if "mockllm.start" in record.message:
                    start_record = record
                elif "mockllm.finish" in record.message:
                    finish_record = record
            
            # Verify extra data is present
            self.assertIsNotNone(start_record)
            self.assertTrue(hasattr(start_record, 'prompt_len'))
            self.assertGreater(start_record.prompt_len, 0)
            
            self.assertIsNotNone(finish_record)
            self.assertTrue(hasattr(finish_record, 'resp_len'))
            self.assertGreater(finish_record.resp_len, 0)
    
    def test_logging_with_command(self):
        """Management command should trigger expected logging."""
        with self.assertLogs('apps.core.llm', level='INFO') as log:
            out = StringIO()
            call_command('hello_llm', prompt='test logging', stdout=out)
            
            messages = [record.message for record in log.records]
            
            # Command should trigger MockLLM logging
            self.assertTrue(any("mockllm.start" in msg for msg in messages))
            self.assertTrue(any("mockllm.finish" in msg for msg in messages))