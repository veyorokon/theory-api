import pytest

from apps.core.leases.manager import (
    canonicalize_path,
    canonicalize_selector,
    paths_overlap,
    selectors_overlap,
    any_overlap,
    LeaseManager,
)


def test_canonicalize_and_selector_trailing_slash():
    assert (
        canonicalize_selector({"kind": "exact", "path": "ARTIFACTS//Foo/Bar.txt/"})["path"] == "/artifacts/foo/bar.txt"
    )
    assert canonicalize_selector({"kind": "prefix", "path": "/artifacts/Foo"})["path"] == "/artifacts/foo/"


def test_percent_decode_and_unicode_nfc():
    assert canonicalize_path("/artifacts/f%C3%B6o/") == "/artifacts/föo"
    # Unicode NFD → NFC normalized equality
    import unicodedata

    nfd = unicodedata.normalize("NFD", "föo")
    nfc = unicodedata.normalize("NFC", "föo")
    assert canonicalize_path(f"/artifacts/{nfd}") == f"/artifacts/{nfc}"


def test_dot_segments_forbidden():
    with pytest.raises(ValueError, match="dot-dot segments forbidden"):
        canonicalize_path("/ARTIFACTS//Foo%2Fbar/..")
    # dot segments are filtered out, not forbidden - only .. is forbidden
    assert canonicalize_path("/artifacts/./foo") == "/artifacts/foo"
    with pytest.raises(ValueError, match="dot-dot segments forbidden"):
        canonicalize_path("/artifacts/../foo")


def test_overlap_matrix_and_plan_scope():
    # exact vs exact
    assert selectors_overlap({"kind": "exact", "path": "/artifacts/x"}, {"kind": "exact", "path": "/artifacts/x"})
    assert not selectors_overlap({"kind": "exact", "path": "/artifacts/x"}, {"kind": "exact", "path": "/artifacts/y"})
    # prefix vs exact with slash boundary
    assert selectors_overlap(
        {"kind": "prefix", "path": "/artifacts/foo/"}, {"kind": "exact", "path": "/artifacts/foo/bar"}
    )
    assert not selectors_overlap(
        {"kind": "prefix", "path": "/artifacts/foo/"}, {"kind": "exact", "path": "/artifacts/foobar"}
    )
    # prefix vs prefix ancestor/descendant
    assert selectors_overlap(
        {"kind": "prefix", "path": "/artifacts/a/b/"}, {"kind": "prefix", "path": "/artifacts/a/b/c/"}
    )
    assert selectors_overlap(
        {"kind": "prefix", "path": "/artifacts/a/b/c/"}, {"kind": "prefix", "path": "/artifacts/a/b/"}
    )
    # plan scoping test
    lm = LeaseManager(enabled=False)
    h1 = lm.acquire("planA", [{"kind": "prefix", "path": "/artifacts/out/"}])
    h2 = lm.acquire("planB", [{"kind": "exact", "path": "/artifacts/out/frame.png"}])
    assert selectors_overlap(h1.selectors[0], h2.selectors[0]) is True  # path-only; API will scope by plan later


def test_overlap_exact_same_path():
    assert selectors_overlap(
        {"kind": "exact", "path": "/artifacts/x"},
        {"kind": "exact", "path": "/artifacts/x"},
    )


def test_overlap_exact_vs_exact_false_for_siblings():
    assert not selectors_overlap(
        {"kind": "exact", "path": "/artifacts/x"},
        {"kind": "exact", "path": "/artifacts/y"},
    )


def test_any_overlap_list():
    ws = [
        {"kind": "exact", "path": "/artifacts/x"},
        {"kind": "prefix", "path": "/artifacts/out/"},
    ]
    held = [{"kind": "prefix", "path": "/artifacts/out/frames/"}]
    assert any_overlap(ws, held) is True


def test_facade_noop_acquire_release():
    lm = LeaseManager(enabled=False)
    handle = lm.acquire("planA", [{"kind": "prefix", "path": "artifacts/out/"}], reason="test")
    assert handle.plan_id == "planA"
    assert handle.reason == "test"
    assert handle.id.startswith("lease:planA:")
    assert handle.selectors[0]["path"] == "/artifacts/out/"
    assert lm.release(handle) is None


def test_overlap_enforcement_when_enabled():
    lm = LeaseManager(enabled=True)
    # should raise on overlapping selectors in same request
    with pytest.raises(ValueError, match="overlapping selectors in request"):
        lm.acquire(
            "planA", [{"kind": "prefix", "path": "/artifacts/foo/"}, {"kind": "exact", "path": "/artifacts/foo/bar"}]
        )
