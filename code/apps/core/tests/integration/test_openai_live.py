import os, pytest
from django.core.management import call_command

pytestmark = [pytest.mark.integration, pytest.mark.openai]

@pytest.mark.skipif("OPENAI_API_KEY" not in os.environ, reason="OPENAI_API_KEY not set")
def test_openai_hello_cli(capsys):
    call_command("hello_llm", provider="litellm", model="openai/gpt-4o-mini", prompt="ping", json=True)
    out = capsys.readouterr().out
    assert "provider" in out and "litellm" in out