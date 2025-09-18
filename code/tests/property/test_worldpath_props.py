import hypothesis.strategies as st
from hypothesis import given
from apps.core.leases.manager import canonicalize_path


@given(st.text(min_size=1, max_size=300))
def test_canon_idempotent(s):
    try:
        a = canonicalize_path(s)
        assert canonicalize_path(a) == a
    except ValueError:
        assert True


@given(st.text(min_size=1, max_size=300))
def test_no_prefix_escape(s):
    try:
        a = canonicalize_path(f"artifacts/outputs/{s}")
        assert a.startswith("/artifacts/outputs/")
    except ValueError:
        assert True
