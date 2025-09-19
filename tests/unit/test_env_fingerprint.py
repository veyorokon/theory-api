from libs.runtime_common.fingerprint import compose_env_fingerprint


def test_env_fingerprint_sorted_and_stable():
    a = compose_env_fingerprint(py="3.11", django="5.0", image_digest="sha256:abc", gpu="none")
    b = compose_env_fingerprint(django="5.0", gpu="none", image_digest="sha256:abc", py="3.11")
    assert a == b
    assert a.split(";") == sorted(a.split(";"))
