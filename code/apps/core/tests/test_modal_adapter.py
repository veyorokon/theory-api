from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.core.adapters.modal_adapter import ModalAdapter


class TestModalAdapter(TestCase):
    def setUp(self):
        self.adapter = ModalAdapter()
        self.invoke_kwargs = {
            'processor_ref': 'test/proc@1',
            'inputs_json': {'test': True},
            'write_prefix': '/artifacts/test/',
            'execution_id': 'exec-123',
            'registry_snapshot': {'test/proc@1': {'runtime': {'cpu': '1', 'memory_gb': 2}, 'image': {'oci': 'test@sha256:abc123'}}},
            'adapter_opts': {},
            'secrets_present': ['OPENAI_API_KEY']
        }

    @patch('apps.core.adapters.modal_adapter.modal.Function.from_name')
    @patch('apps.core.adapters.modal_adapter.storage_service')
    def test_function_lookup_happy_path(self, mock_storage, mock_from_name):
        """Test successful Modal function lookup and execution"""
        # Mock Modal function and remote execution
        mock_function = MagicMock()
        mock_function.remote.return_value = b'fake tar bytes'
        mock_from_name.return_value = mock_function
        
        # Mock storage service for artifact write
        mock_storage.write_bytes.return_value = None
        
        result = self.adapter.invoke(**self.invoke_kwargs)
        
        # Verify function lookup called with correct parameters
        mock_from_name.assert_called_once()
        app_name_arg = mock_from_name.call_args[1]['app']
        self.assertIn('test-proc-v1-dev', app_name_arg)
        
        # Verify successful envelope
        self.assertEqual(result['status'], 'success')
        self.assertIn('outputs', result)

    @patch('apps.core.adapters.modal_adapter.modal.Function.from_name')
    def test_function_lookup_not_found(self, mock_from_name):
        """Test Modal function lookup failure returns nested error"""
        # Mock Modal not available
        mock_from_name.side_effect = ImportError("Modal not available")
        
        result = self.adapter.invoke(**self.invoke_kwargs)
        
        # Verify nested error envelope  
        self.assertEqual(result['status'], 'error')
        self.assertIn('error', result)

    @patch('apps.core.adapters.modal_adapter.modal.Function.from_name')
    def test_remote_runtime_error(self, mock_from_name):
        """Test Modal remote execution error with stderr tail"""
        mock_function = MagicMock()
        mock_function.remote.side_effect = RuntimeError("processor failed (exit=1):\nstderr tail here")
        mock_from_name.return_value = mock_function
        
        result = self.adapter.invoke(**self.invoke_kwargs)
        
        # Verify nested error with stderr information
        self.assertEqual(result['status'], 'error')
        self.assertIn('error', result)
        self.assertIn('stderr tail here', str(result))

    def test_write_prefix_validation(self):
        """Test write prefix validation"""
        # Valid prefix
        valid = self.adapter.validate_write_prefix('/artifacts/test/')
        self.assertTrue(valid)
        
        # Invalid prefixes
        self.assertFalse(self.adapter.validate_write_prefix('/invalid/'))
        self.assertFalse(self.adapter.validate_write_prefix('artifacts/test/'))
        self.assertFalse(self.adapter.validate_write_prefix('/artifacts/test'))