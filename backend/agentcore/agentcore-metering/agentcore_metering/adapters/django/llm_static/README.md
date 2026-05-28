# LLM static data (YAML)

Capability labels, mode mapping, provider/model lists, and reference pricing. Used by the Django adapter for the LLM config UI and resolution.

## Price update time

Reference prices in `providers/*.yaml` were last updated: **2026-02**. Consider updating periodically from provider docs or [LLM Stats](https://llm-stats.com/).

## Reference pricing (schema)

Prices under `reference_pricing` per model are **reference only** and not used for billing. They help compare cost across providers and models in the UI.

### Data sources

- **Official provider pages**: [OpenAI Pricing](https://openai.com/api/pricing), [Anthropic Pricing](https://docs.anthropic.com/en/docs/about-claude/pricing), [Gemini Pricing](https://ai.google.dev/gemini-api/docs/pricing), [DeepSeek Pricing](https://api-docs.deepseek.com/quick_start/pricing), etc.
- **Comparison / benchmarks**: [LLM Stats](https://llm-stats.com/) — leaderboards, benchmarks, and cost comparison for many models (LLM, Coding, Image, etc.). Use it to cross-check model names and compare performance vs cost.

### Schema (per model)

Optional `reference_pricing` on a model entry:

- `input_usd_per_1m`: USD per 1M input tokens (optional)
- `output_usd_per_1m`: USD per 1M output tokens (optional)
- `source`: URL or short label (e.g. provider pricing page)
- `updated`: Date string (e.g. `2026-02`) when the price was last checked
