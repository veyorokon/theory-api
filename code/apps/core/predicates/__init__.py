"""
Predicates for admission and success conditions.

Predicates are pure functions that evaluate conditions for plan execution.
They return boolean values and must be deterministic and fast.
"""

from .builtins import (
    artifact_exists,
    series_has_new,
    json_schema_ok,
    tests_pass,
)

__all__ = [
    'artifact_exists',
    'series_has_new', 
    'json_schema_ok',
    'tests_pass',
]

# Registry entries for predicates
PREDICATE_REGISTRY = {
    'artifact.exists@1': {
        'fn': artifact_exists,
        'params': {'path': 'str'},
        'returns': 'bool',
        'description': 'Check if artifact exists at path',
    },
    'series.has_new@1': {
        'fn': series_has_new,
        'params': {'path': 'str', 'min_idx': 'int'},
        'returns': 'bool',
        'description': 'Check if series has new items after min_idx',
    },
    'json.schema_ok@1': {
        'fn': json_schema_ok,
        'params': {'path': 'str', 'schema_ref': 'str'},
        'returns': 'bool',
        'description': 'Validate JSON at path against schema',
    },
    'tests.pass@1': {
        'fn': tests_pass,
        'params': {'path_or_glob': 'str', 'timeout_ms': 'int'},
        'returns': 'bool',
        'description': 'Run tests and check if they pass',
    },
}