# Summary — Thread 0003 (LLM LiteLLM Consolidation)

Scope
- Standardize LLM providers on a single LiteLLM substrate; retain MockLLM for deterministic tests.
- Make model a first‑class argument; support vendor‑qualified models (e.g., `openai/gpt-4o-mini`, `ollama/qwen2.5:0.5b`).
- Add streaming hook now to avoid interface break later.
- Remove bespoke OpenAI/Ollama providers and aliases; update docs/tests.

Key Changes
- Added `LiteLLMProvider` implementing `LLMProvider.chat()` and `stream_chat()` via `litellm.completion`.
- CLI `hello_llm` extended with `--provider {mock,litellm}`, `--model`, `--api-base`, `--stream`.
- Provider factory locked to `{mock, litellm}`; lazy construction with per‑run defaults; friendly errors.
- Normalized `LLMReply.usage` keys (`tokens_in`, `tokens_out`, `latency_ms`, `usd_micros`).
- Docs updated (Hello LLM, Providers) to LiteLLM substrate, streaming examples, env guidance.
- Tests aligned: command tests mock `litellm.completion`; assertions target friendly messages; integration tests gated via pytest markers.
- Docker/ASGI updated: Channels ready (Daphne), MinIO healthcheck fixed; settings carry LLM defaults.

Decisions
- Explicit behavior via flags/settings (no env‑driven logic). Secrets only in env; one requirements for parity.
- Streaming added now (CLI/UI only) to keep contract stable; WS/Channels streaming deferred.
- Integration tests are opt‑in (pytest); unit tests via Django runner remain fast and deterministic.

Outcomes
- Single substrate for 100+ providers; legacy codepaths removed.
- Green unit suite with substrate‑accurate mocking; live integration available when env/daemon provided.
- Documentation aligned; no references to removed providers.

Follow‑ups (next slices)
- Modal runtime wiring (same contract), WS/Channels streaming surface, budgeting/cost integration.

Acceptance & Smoke
- Unit: `python theory_api/code/manage.py test -v`
- Providers (mocked): `python theory_api/code/manage.py test apps.core.tests.test_providers -v`
- Integration (opt-in): `cd theory_api/code && pytest -m integration -q`
- Docs: `make -C theory_api/docs -W html`

Risks & Mitigations
- External exceptions/strings drift → assert on friendly messages; mock generic Exception in unit tests; keep integration tests gated.
- Accidental legacy usage → factory locked to {mock, litellm}; grep CI to detect legacy flags.

Docs/Generated Drift
- `_generated/**`: unchanged
- Sphinx: passes with `-W`

Links & Artifacts
- PR: <#>
- Commit: `<sha>`
- Docs: `theory_api/docs/_build/html/use-cases/hello-llm.html`
