# tests/tools/asserts.py
"""Shared assertion helpers for envelope and receipt contracts (lane-safe)."""

from __future__ import annotations
from typing import Mapping, Any, Iterable


def assert_success_envelope(env: Mapping[str, Any], *, fingerprint_fragments: Iterable[str] = ()) -> Mapping[str, Any]:
    assert env.get("status") == "success", f"expected success, got: {env}"
    eid = env.get("execution_id")
    assert isinstance(eid, str) and eid, "missing execution_id"

    idx = env.get("index_path")
    assert isinstance(idx, str) and idx.endswith("/outputs.json"), f"invalid index_path: {idx}"

    outs = env.get("outputs")
    assert isinstance(outs, list) and len(outs) >= 1, "outputs must be a non-empty list"
    for i, o in enumerate(outs):
        assert isinstance(o, dict) and "path" in o, f"outputs[{i}] missing path"

    meta = env.get("meta") or {}
    assert isinstance(meta, dict), "meta must be present"
    fp = meta.get("env_fingerprint")
    assert isinstance(fp, str) and fp, "env_fingerprint must be present"
    assert_env_fingerprint(fp, fragments=("cpu:", *fingerprint_fragments))
    return env  # type: ignore[return-value]


def assert_error_envelope(
    env: Mapping[str, Any],
    *,
    code: str | None = None,
    code_fragment: str | None = None,
    message_fragment: str | None = None,
) -> Mapping[str, Any]:
    """Assert canonical error envelope.
    - Prefer exact code via `code=...`; or use `code_fragment=...` if only a fragment is stable.
    - Optionally assert a stable `message_fragment`.
    """
    assert env.get("status") == "error", f"expected error, got: {env}"
    err = env.get("error") or {}
    got_code = err.get("code", "")
    if code is not None:
        assert got_code == code, f"unexpected error code: {err}"
    if code_fragment is not None:
        assert code_fragment in got_code, f"expected code fragment {code_fragment!r} in {got_code!r}"
    if message_fragment is not None:
        msg = err.get("message", "")
        assert message_fragment in msg, f"expected fragment {message_fragment!r} in {msg!r}"
    eid = env.get("execution_id")
    assert isinstance(eid, str) and eid, "missing execution_id"
    return env  # type: ignore[return-value]


def assert_env_fingerprint(fingerprint: str, fragments: Iterable[str] = ()) -> None:
    # sorted key=value pairs joined by ';'
    parts = [p for p in fingerprint.split(";") if p]
    assert parts == sorted(parts), f"env_fingerprint must be sorted; got: {fingerprint}"
    for frag in fragments:
        assert frag in fingerprint, f"missing fragment {frag!r} in env_fingerprint"


def assert_index_under_prefix(index_path: str, write_prefix: str) -> None:
    expected = write_prefix.rstrip("/") + "/"
    assert index_path.startswith(expected), f"index_path {index_path} must start with {expected}"
    assert index_path.endswith("/outputs.json"), f"index_path should end with outputs.json: {index_path}"
