"""
Acceptance tests for predicates with PostgreSQL.

Tests that require real database or storage connections.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from django.test import TransactionTestCase

from apps.core.predicates import (
    artifact_exists,
    series_has_new,
    json_schema_ok,
)
from apps.core.predicates.builtins import (
    canon_path_facet_root,
    artifact_read_json,
    series_watermark_idx,
)


class TestPathCanonicalization(TransactionTestCase):
    """Test path canonicalization function."""
    
    def test_canon_basic_path(self):
        """Basic path canonicalization."""
        result = canon_path_facet_root('/ARTIFACTS/test/file.json')
        self.assertEqual(result, '/artifacts/test/file.json')
    
    def test_canon_percent_decode(self):
        """Percent-decoding."""
        result = canon_path_facet_root('/artifacts/test%20file.json')
        self.assertEqual(result, '/artifacts/test file.json')
    
    def test_canon_reject_encoded_slashes(self):
        """Reject encoded slashes."""
        with self.assertRaises(ValueError) as cm:
            canon_path_facet_root('/artifacts/test%2Ffile')
        self.assertIn('Encoded slashes', str(cm.exception))
    
    def test_canon_unicode_nfc(self):
        """Unicode NFC normalization."""
        # Combining characters should normalize
        result = canon_path_facet_root('/artifacts/café')  # é as single char
        composed = '/artifacts/café'  # é as combining chars normalized
        self.assertEqual(result, composed.lower())
    
    def test_canon_collapse_slashes(self):
        """Collapse double slashes."""
        result = canon_path_facet_root('/artifacts//test///file.json')
        self.assertEqual(result, '/artifacts/test/file.json')
    
    def test_canon_forbid_dots(self):
        """Forbid . and .. segments."""
        with self.assertRaises(ValueError):
            canon_path_facet_root('/artifacts/../test')
        
        with self.assertRaises(ValueError):
            canon_path_facet_root('/artifacts/./test')
    
    def test_canon_enforce_facet_root(self):
        """Enforce /artifacts or /streams facet root."""
        # Valid facets
        self.assertEqual(
            canon_path_facet_root('/artifacts/test'),
            '/artifacts/test'
        )
        self.assertEqual(
            canon_path_facet_root('/streams/test'),
            '/streams/test'
        )
        
        # Invalid facet
        with self.assertRaises(ValueError) as cm:
            canon_path_facet_root('/invalid/test')
        self.assertIn('must start with /artifacts or /streams', str(cm.exception))


@pytest.mark.requires_postgres
class TestArtifactExistsAcceptance(TransactionTestCase):
    """Acceptance tests for artifact.exists with storage."""
    
    @patch('apps.storage.service.storage_service')
    def test_artifact_exists_with_minio_mock(self, mock_storage):
        """Test with MinIO mock."""
        # Mock storage service
        mock_storage.file_exists.return_value = True
        
        result = artifact_exists('/artifacts/test/file.json')
        
        self.assertTrue(result)
        mock_storage.file_exists.assert_called_once_with('/artifacts/test/file.json')
    
    @patch('apps.storage.service.storage_service')
    def test_artifact_missing_with_storage(self, mock_storage):
        """Test missing artifact."""
        mock_storage.file_exists.return_value = False
        
        result = artifact_exists('/artifacts/missing.json')
        
        self.assertFalse(result)
    
    def test_artifact_exists_invalid_path(self):
        """Invalid paths return False."""
        # Path with encoded slash
        self.assertFalse(artifact_exists('/artifacts/test%2Ffile'))
        
        # Invalid facet
        self.assertFalse(artifact_exists('/invalid/file'))
        
        # Path with ..
        self.assertFalse(artifact_exists('/artifacts/../file'))


@pytest.mark.requires_postgres  
class TestSeriesHasNewAcceptance(TransactionTestCase):
    """Acceptance tests for series.has_new with PostgreSQL."""
    
    def test_series_has_new_with_model(self):
        """Test with ArtifactSeries model if available."""
        # Try to create test data
        try:
            from apps.artifacts.models import ArtifactSeries
            from apps.plans.models import Plan
            
            # Create test plan first
            plan = Plan.objects.create(key='test-plan', reserved_micro=1000, spent_micro=0)
            
            # Create test series with correct field names
            series = ArtifactSeries.objects.create(
                plan=plan,
                series_key='test-series'
            )
            
            # Since model exists but doesn't have watermark_idx field, 
            # series_watermark_idx should return 0, so series_has_new should return False
            result = series_has_new('/streams/test/series', min_idx=5)
            self.assertFalse(result)  # No watermark tracking yet
            
        except ImportError:
            # Model not available - verify flag-guarded behavior
            result = series_has_new('/streams/test', min_idx=5)
            self.assertFalse(result)  # Returns False when not wired
    
    def test_series_watermark_idx_stub(self):
        """Test watermark accessor stub behavior."""
        # Should return 0 when model not present
        idx = series_watermark_idx('/streams/test')
        self.assertEqual(idx, 0)


class TestJsonSchemaAcceptance(TransactionTestCase):
    """Acceptance tests for json.schema_ok."""
    
    @patch('apps.core.predicates.builtins.artifact_read_json')
    def test_json_schema_with_registry(self, mock_read):
        """Test schema validation with registry."""
        # Mock artifact content
        mock_read.return_value = {
            'name': 'test',
            'value': 42
        }
        
        # Create test schema in registry format
        test_schema = {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'value': {'type': 'number'}
            },
            'required': ['name', 'value']
        }
        
        # Create temporary registry file
        registry_dir = Path('docs/_generated')
        registry_dir.mkdir(parents=True, exist_ok=True)
        registry_file = registry_dir / 'schemas.json'
        
        with open(registry_file, 'w') as f:
            json.dump({'test.schema': test_schema}, f)
        
        try:
            # Should validate successfully
            result = json_schema_ok('/artifacts/data.json', 'test.schema')
            self.assertTrue(result)
        finally:
            # Clean up
            if registry_file.exists():
                registry_file.unlink()
    
    @patch('apps.core.predicates.builtins.artifact_read_json')
    def test_json_schema_validation_failure(self, mock_read):
        """Test schema validation failure."""
        # Invalid data (missing required field)
        mock_read.return_value = {'name': 'test'}  # Missing 'value'
        
        # Create test schema
        test_schema = {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'value': {'type': 'number'}
            },
            'required': ['name', 'value']
        }
        
        # Create temporary schema file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_schema, f)
            schema_path = f.name
        
        try:
            result = json_schema_ok('/artifacts/data.json', schema_path)
            self.assertFalse(result)
        finally:
            Path(schema_path).unlink()

