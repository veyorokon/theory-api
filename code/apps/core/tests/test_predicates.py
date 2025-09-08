"""
Tests for predicate implementations.

Tests both unit behavior and acceptance paths with fixtures.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase

from apps.core.predicates import (
    artifact_exists,
    series_has_new,
    json_schema_ok,
    artifact_jsonpath_eq,
    PREDICATE_REGISTRY,
)


class TestPredicateRegistry(TestCase):
    """Test predicate registry structure and entries."""
    
    def test_registry_has_all_predicates(self):
        """Registry should contain all 4 predicates."""
        expected = {
            'artifact.exists@1',
            'series.has_new@1',
            'json.schema_ok@1',
            'artifact.jsonpath_eq@1',
        }
        self.assertEqual(set(PREDICATE_REGISTRY.keys()), expected)
    
    def test_registry_entries_have_required_fields(self):
        """Each registry entry should have required fields."""
        for name, entry in PREDICATE_REGISTRY.items():
            with self.subTest(predicate=name):
                self.assertIn('fn', entry)
                self.assertIn('params', entry)
                self.assertIn('returns', entry)
                self.assertIn('description', entry)
                self.assertEqual(entry['returns'], 'bool')


class TestArtifactExists(TestCase):
    """Test artifact.exists predicate."""
    
    @patch('apps.storage.service.storage_service')
    def test_exists_returns_true_when_artifact_exists(self, mock_storage):
        """Should return True when artifact exists."""
        mock_storage.file_exists.return_value = True
        
        result = artifact_exists('/artifacts/test.json')
        
        self.assertTrue(result)
        mock_storage.file_exists.assert_called_once_with('/artifacts/test.json')
    
    @patch('apps.storage.service.storage_service')
    def test_exists_returns_false_when_artifact_missing(self, mock_storage):
        """Should return False when artifact doesn't exist."""
        mock_storage.file_exists.return_value = False
        
        result = artifact_exists('/artifacts/missing.json')
        
        self.assertFalse(result)
    
    @patch('apps.storage.service.storage_service')
    def test_exists_returns_false_on_error(self, mock_storage):
        """Should return False on any error."""
        mock_storage.file_exists.side_effect = Exception('Storage error')
        
        result = artifact_exists('/artifacts/error.json')
        
        self.assertFalse(result)


class TestSeriesHasNew(TestCase):
    """Test series.has_new predicate."""
    
    @patch('apps.core.predicates.builtins.series_watermark_idx')
    def test_has_new_returns_true_when_newer(self, mock_watermark):
        """Should return True when watermark > min_idx."""
        mock_watermark.return_value = 15
        
        result = series_has_new('/streams/telemetry', min_idx=10)
        self.assertTrue(result)
    
    @patch('apps.core.predicates.builtins.series_watermark_idx')
    def test_has_new_returns_false_when_older(self, mock_watermark):
        """Should return False when watermark <= min_idx."""
        mock_watermark.return_value = 5
        
        result = series_has_new('/streams/data', min_idx=10)
        self.assertFalse(result)


class TestJsonSchemaOk(TestCase):
    """Test json.schema_ok predicate."""
    
    @patch('apps.core.predicates.builtins.artifact_read_json')
    def test_schema_ok_validates_correct_json(self, mock_read):
        """Should return True for valid JSON."""
        # Create test data and schema
        test_data = {'name': 'test', 'value': 42}
        test_schema = {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'value': {'type': 'number'}
            },
            'required': ['name', 'value']
        }
        
        # Mock artifact reader to return test data
        mock_read.return_value = test_data
        
        # Create temporary schema file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_schema, f)
            schema_path = f.name
        
        try:
            result = json_schema_ok('/artifacts/data.json', schema_path)
            self.assertTrue(result)
        finally:
            Path(schema_path).unlink()
    
    @patch('apps.core.predicates.builtins.artifact_read_json')
    def test_schema_ok_rejects_invalid_json(self, mock_read):
        """Should return False for invalid JSON."""
        # Invalid data (missing required field)
        test_data = {'name': 'test'}  # Missing 'value'
        test_schema = {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'value': {'type': 'number'}
            },
            'required': ['name', 'value']
        }
        
        # Mock artifact reader
        mock_read.return_value = test_data
        
        # Create temporary schema file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_schema, f)
            schema_path = f.name
        
        try:
            result = json_schema_ok('/artifacts/data.json', schema_path)
            self.assertFalse(result)
        finally:
            Path(schema_path).unlink()
    
    @patch('apps.core.predicates.builtins.artifact_read_json')
    def test_schema_ok_handles_malformed_json(self, mock_read):
        """Should return False for malformed JSON."""
        # Mock artifact reader to return None (read error)
        mock_read.return_value = None
        
        result = json_schema_ok('/artifacts/bad.json', 'any_schema')
        self.assertFalse(result)


class TestArtifactJsonPathEq(TestCase):
    """Test artifact.jsonpath_eq predicate."""
    
    @patch('apps.storage.service.storage_service')
    def test_jsonpath_eq_simple_field(self, mock_service):
        """Should return True when JSONPath matches expected value."""
        mock_service.read_file.return_value = b'{"name": "test", "version": 1}'
        
        result = artifact_jsonpath_eq('/artifacts/config.json', '$.name', 'test')
        
        self.assertTrue(result)
        mock_service.read_file.assert_called_with('/artifacts/config.json')
    
    @patch('apps.storage.service.storage_service')
    def test_jsonpath_eq_nested_field(self, mock_service):
        """Should handle nested field access."""
        mock_service.read_file.return_value = b'{"config": {"debug": true, "port": 8080}}'
        
        result = artifact_jsonpath_eq('/artifacts/settings.json', '$.config.debug', True)
        
        self.assertTrue(result)
        
        result = artifact_jsonpath_eq('/artifacts/settings.json', '$.config.port', 8080)
        
        self.assertTrue(result)
    
    @patch('apps.storage.service.storage_service')
    def test_jsonpath_eq_array_index(self, mock_service):
        """Should handle array index access."""
        mock_service.read_file.return_value = b'{"items": ["first", "second", "third"]}'
        
        result = artifact_jsonpath_eq('/artifacts/list.json', '$.items[0]', 'first')
        
        self.assertTrue(result)
        
        result = artifact_jsonpath_eq('/artifacts/list.json', '$.items[1]', 'second')
        
        self.assertTrue(result)
    
    @patch('apps.storage.service.storage_service')
    def test_jsonpath_eq_returns_false_on_mismatch(self, mock_service):
        """Should return False when values don't match."""
        mock_service.read_file.return_value = b'{"status": "active"}'
        
        result = artifact_jsonpath_eq('/artifacts/status.json', '$.status', 'inactive')
        
        self.assertFalse(result)
    
    @patch('apps.storage.service.storage_service')
    def test_jsonpath_eq_handles_missing_path(self, mock_service):
        """Should return False when JSONPath doesn't exist."""
        mock_service.read_file.return_value = b'{"name": "test"}'
        
        result = artifact_jsonpath_eq('/artifacts/data.json', '$.nonexistent', 'value')
        
        self.assertFalse(result)
        
        result = artifact_jsonpath_eq('/artifacts/data.json', '$.nested.field', 'value')
        
        self.assertFalse(result)
    
    @patch('apps.storage.service.storage_service')
    def test_jsonpath_eq_handles_invalid_json(self, mock_service):
        """Should return False on invalid JSON."""
        mock_service.read_file.return_value = b'invalid json{'
        
        result = artifact_jsonpath_eq('/artifacts/bad.json', '$.field', 'value')
        
        self.assertFalse(result)
    
    @patch('apps.storage.service.storage_service')
    def test_jsonpath_eq_handles_missing_file(self, mock_service):
        """Should return False when file doesn't exist."""
        mock_service.read_file.return_value = None
        
        result = artifact_jsonpath_eq('/artifacts/missing.json', '$.field', 'value')
        
        self.assertFalse(result)
    
    def test_jsonpath_eq_validates_path_canonicalization(self):
        """Should validate and canonicalize paths."""
        # Invalid paths should return False
        self.assertFalse(artifact_jsonpath_eq('/streams/data.json', '$.field', 'value'))
        self.assertFalse(artifact_jsonpath_eq('/invalid/path', '$.field', 'value'))
        self.assertFalse(artifact_jsonpath_eq('artifacts/no-slash', '$.field', 'value'))


# Acceptance tests
@pytest.mark.unit
class TestPredicateAcceptance(TestCase):
    """Acceptance tests for predicate evaluation paths."""
    
    def test_predicate_functions_are_callable(self):
        """All registry predicates should be callable."""
        for name, entry in PREDICATE_REGISTRY.items():
            with self.subTest(predicate=name):
                self.assertTrue(callable(entry['fn']))
    
    @patch('apps.storage.service.storage_service')
    def test_predicates_return_boolean(self, mock_storage):
        """All predicates should return boolean values."""
        # Provide basic stubs for storage access
        mock_storage.file_exists.return_value = False
        # json.schema_ok will use artifact_read_json; patching that separately below
        self.assertIsInstance(artifact_exists('/artifacts/test'), bool)
        self.assertIsInstance(series_has_new('/streams/test', 0), bool)

        with patch('apps.core.predicates.builtins.artifact_read_json') as mock_read:
            mock_read.return_value = {}
            self.assertIsInstance(json_schema_ok('/artifacts/test.json', 'schema'), bool)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            self.assertIsInstance(artifact_jsonpath_eq('/artifacts/test.json', '$.field', 'value'), bool)
