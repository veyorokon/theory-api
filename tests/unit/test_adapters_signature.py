import inspect
from apps.core.adapters.local_adapter import LocalAdapter
from apps.core.adapters.modal_adapter import ModalAdapter


def _kwonly(fn):
    sig = inspect.signature(fn)
    # Skip 'self' parameter for methods
    params = [p for name, p in sig.parameters.items() if name != "self"]
    return all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in params)


def test_invoke_keyword_only():
    for adapter_cls in (LocalAdapter, ModalAdapter):
        adapter = adapter_cls()
        assert _kwonly(adapter.invoke), f"{adapter_cls.__name__}.invoke must be keyword-only"
