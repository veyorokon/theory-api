# Compatibility shim for deleted proc module
# All CLI proc helpers were removed in HTTP-first architecture
# Tests should use FastAPI TestClient or adapter calls instead


def run_cmd(*args, **kwargs):
    """Legacy CLI runner - removed in HTTP-first architecture"""
    raise NotImplementedError("Use FastAPI TestClient or adapter calls instead of CLI proc")


def build_error_message(*args, **kwargs):
    """Legacy error builder - use envelope helpers instead"""
    raise NotImplementedError("Use envelope error helpers instead")
