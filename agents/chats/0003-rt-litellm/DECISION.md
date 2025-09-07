Status: Completed

Decision
- Standardize LLM providers on LiteLLM with explicit provider/model flags and optional api_base; retain MockLLM for deterministic tests. Remove bespoke OpenAI/Ollama providers and aliases. Add streaming hook and CLI flag now to avoid interface break. Update docs and tests to reflect the canonical substrate.

Evidence
- Provider factory exposes only {mock, litellm}; openai/ollama classes removed.
- Docs updated (Hello LLM, Providers) with vendor‑qualified models and streaming examples; no legacy references remain.
- Tests updated to target LiteLLM and mock litellm.completion; error assertions match friendly messages; integration tests gated under pytest markers.

Notes
- Integration tests remain opt‑in via pytest; Django runner covers fast unit suite.

