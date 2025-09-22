"""Test Modal app naming contract."""

import pytest
from libs.runtime_common.modal_naming import modal_app_name, processor_slug, parse_ref


class TestProcessorSlug:
    def test_basic_slug(self):
        assert processor_slug("llm/litellm@1") == "llm-litellm-v1"

    def test_complex_slug(self):
        assert processor_slug("replicate/generic@42") == "replicate-generic-v42"

    def test_normalization(self):
        assert processor_slug("LLM/LiteLLM@1") == "llm-litellm-v1"


class TestParseRef:
    def test_valid_ref(self):
        assert parse_ref("llm/litellm@1") == ("llm", "litellm", 1)
        assert parse_ref("replicate/generic@42") == ("replicate", "generic", 42)

    def test_invalid_refs(self):
        with pytest.raises(ValueError, match="invalid processor ref"):
            parse_ref("invalid")

        with pytest.raises(ValueError, match="invalid processor ref"):
            parse_ref("no-slash@1")

        with pytest.raises(ValueError, match="invalid processor ref"):
            parse_ref("ns/name")  # no version

    def test_invalid_version(self):
        with pytest.raises(ValueError, match="invalid version"):
            parse_ref("ns/name@abc")


class TestModalAppName:
    def test_dev_requires_branch_and_user(self):
        with pytest.raises(ValueError, match="dev naming requires branch and user"):
            modal_app_name("llm/litellm@1", env="dev")

        with pytest.raises(ValueError, match="dev naming requires branch and user"):
            modal_app_name("llm/litellm@1", env="dev", branch="feat-x")

        with pytest.raises(ValueError, match="dev naming requires branch and user"):
            modal_app_name("llm/litellm@1", env="dev", user="alex")

    def test_dev_naming(self):
        result = modal_app_name("llm/litellm@1", env="dev", branch="feat-x", user="alex")
        assert result == "feat-x-alex-llm-litellm-v1"

    def test_dev_naming_normalization(self):
        result = modal_app_name("llm/litellm@1", env="dev", branch="feat/complex_branch", user="user.name")
        assert result == "feat-complex-branch-user-name-llm-litellm-v1"

    @pytest.mark.parametrize("env", ["staging", "main"])
    def test_non_dev_is_canonical(self, env):
        result = modal_app_name("llm/litellm@1", env=env)
        assert result == "llm-litellm-v1"

    def test_env_normalization(self):
        # Case insensitive and strips
        result = modal_app_name("llm/litellm@1", env="  STAGING  ")
        assert result == "llm-litellm-v1"

        result = modal_app_name("llm/litellm@1", env="  DEV  ", branch="main", user="alex")
        assert result == "main-alex-llm-litellm-v1"

    def test_complex_processor_refs(self):
        result = modal_app_name("replicate/generic@42", env="staging")
        assert result == "replicate-generic-v42"

        result = modal_app_name("replicate/generic@42", env="dev", branch="feature", user="bob")
        assert result == "feature-bob-replicate-generic-v42"
