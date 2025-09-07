import os, pytest, requests

pytestmark = [pytest.mark.integration, pytest.mark.ollama]
OLLAMA = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

def _ollama_alive():
    try:
        requests.get(OLLAMA, timeout=1)
        return True
    except Exception:
        return False

@pytest.mark.skipif(not _ollama_alive(), reason="Ollama daemon not running")
def test_ollama_cli(capsys):
    from django.core.management import call_command
    call_command("hello_llm", provider="litellm", model="ollama/qwen3:0.6b", api_base=OLLAMA, prompt="ping", json=True)
    assert "ollama/qwen3:0.6b" in capsys.readouterr().out