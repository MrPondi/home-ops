# free-pool

`free-pool` is a LiteLLM model group of free models from several providers: the "throw cheap work at it" lane. One file per provider in this folder (`nvidia.yaml`, `groq.yaml`, `gemini.yaml`, `openrouter.yaml`), all with `modelName: free-pool`; `gemini.yaml` also holds the standalone `gemini-3.1-flash-lite`.

## Rules

- **Public material only.** Free tiers log prompts and may train on them (Google states this for free Gemini). No secrets, tokens or personal data.
- **Never a fallback.** No other model group, fallback chain or default points at `free-pool`, so private traffic cannot reach it by accident.
- **Opt-in only.** Give a consumer `free-pool` explicitly; keys without a `models:` list can reach it too.

## Routing

Rungs are tried by `order:` across all providers (strongest first): NVIDIA NIM (1-3), Groq gpt-oss (4), Gemini (5), Groq Qwen (6), OpenRouter (7-13), then `openrouter/free` (a random free model) last at 14. Free tiers answer `429` when quota runs out and LiteLLM cools that deployment down. It does **not** cool down on `402`/`403`, so a rung that answers `403` is retried on every request: only list models that answer `200` through LiteLLM.

Limits: NVIDIA NIM 40 requests/minute; Groq about 1,000 requests/day; Gemini free tier 1,500 requests/day. OpenRouter: 20 requests/minute and 1,000/day across all free models once $10 of credits has been bought (far less without credits). A key is required even for `:free` models.

## Keys

`NVIDIA_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` and `AISTUDIO_API_KEY` (Gemini) in the `litellm` Bitwarden item, mapped in `../../externalsecret.yaml`. Context sizes for NVIDIA rungs are conservative guesses; raise them once probed.

## Refreshing the list

Free models rotate often.

1. List candidates: `curl -s https://openrouter.ai/api/v1/models`, keep entries with `pricing.prompt` and `pricing.completion` both `"0"` and `tools` in `supported_parameters`. Do not filter on the `:free` suffix.
2. Probe each through LiteLLM with a one-word request; keep only `200`s. Known gated (403 to non-harness callers as of 2026-10): `thinkingmachines/inkling:free`, `inkling-small:free`.
3. Edit the provider's file: one document per rung named `free-pool-<provider>-<model>`, `maxInputTokens` = the model's context length, `supportsVision` only for image-input models, renumber `order:` with `openrouter/free` last.
