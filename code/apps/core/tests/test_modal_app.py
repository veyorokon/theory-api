import json
import os
import tarfile
import tempfile
from unittest.mock import patch, MagicMock, mock_open
from django.test import SimpleTestCase


class TestModalApp(SimpleTestCase):
    def setUp(self):
        self.test_payload = {
            'inputs_json': {'messages': [{'role': 'user', 'content': 'test'}]},
            'write_prefix': '/artifacts/test/'
        }

    @patch.dict(os.environ, {
        'PROCESSOR_REF': 'test/proc@1',
        'IMAGE_REF': 'test@sha256:abc123',
        'MODAL_ENVIRONMENT': 'dev'
    })
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.dump')
    def test_inputs_json_written(self, mock_json_dump, mock_file, mock_makedirs, mock_subprocess):
        """Test inputs.json is written correctly before execution"""
        from modal_app import run
        
        # Mock successful subprocess execution
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        # Mock os.walk to return empty (no output files)
        with patch('os.walk', return_value=[]):
            with patch('tarfile.open'):
                result = run(self.test_payload)
        
        # Verify inputs.json was written with correct content
        mock_makedirs.assert_called_with('/work', exist_ok=True)
        mock_json_dump.assert_called_with(
            self.test_payload['inputs_json'], 
            mock_file.return_value.__enter__.return_value,
            ensure_ascii=False,
            separators=(',', ':')
        )

    @patch.dict(os.environ, {
        'PROCESSOR_REF': 'test/proc@1', 
        'IMAGE_REF': 'test@sha256:abc123'
    })
    @patch('subprocess.run')
    def test_processor_failure_with_stderr(self, mock_subprocess):
        """Test modal_app.run handles subprocess failure with stderr tail"""
        from modal_app import run
        from subprocess import CalledProcessError
        
        # Mock subprocess failure with stderr
        mock_subprocess.side_effect = CalledProcessError(
            returncode=1,
            cmd=['python', '/app/main.py'],
            stderr='Error line 1\nError line 2\nFatal error occurred'
        )
        
        with self.assertRaises(RuntimeError) as ctx:
            run(self.test_payload)
        
        # Verify error message includes stderr tail
        error_msg = str(ctx.exception)
        self.assertIn('processor failed (exit=1)', error_msg)
        self.assertIn('Fatal error occurred', error_msg)

    def test_app_name_generation(self):
        """Test Modal app name generation from environment"""
        with patch.dict(os.environ, {
            'PROCESSOR_REF': 'llm/litellm@1',
            'MODAL_ENVIRONMENT': 'dev'
        }):
            from modal_app import _modal_app_name_from_env
            app_name = _modal_app_name_from_env()
            self.assertIn('llm-litellm-v1-dev', app_name)