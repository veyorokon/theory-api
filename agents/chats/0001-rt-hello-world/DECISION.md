Status: Completed

Decision
- Ship the minimal LLM Hello World: `LLMReply` dataclass, `LLMProvider` protocol, deterministic `MockLLM`, `hello_llm` management command with `--json`, Django tests with logging assertions, and a Hello LLM use‑case page linked in the docs index.

Notes
- Patterns established here allow drop‑in provider replacements without changing call sites.

