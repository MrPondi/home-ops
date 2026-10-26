# free-pool

`free-pool` (`free-pool.yaml`) is a LiteLLM model group of free OpenRouter models: the "throw cheap work at it" lane.

## Rules

- **Public material only.** Free tiers log prompts and may train on them. No secrets, tokens or personal data.
- **Never a fallback.** No other model group, fallback chain or default points at `free-pool`, so private traffic cannot reach it by accident.
- **Opt-in only.** Give a consumer `free-pool` explicitly; keys without a `models:` list can reach it too.

## Routing

Rungs are tried by `order:` (strongest first); `openrouter/free` (a random free model) is always last. Free tiers answer `429` when quota runs out and LiteLLM cools that deployment down. It does **not** cool down on `402`/`403`, so a rung that answers `403` is retried on every request: only list models that answer `200` through LiteLLM.

OpenRouter limits: 20 requests/minute and 1,000/day across all free models once $10 of credits has been bought (far less without credits). A key is required even for `:free` models.

## Key

`OPENROUTER_API_KEY` in the `litellm` Bitwarden item, mapped in `../externalsecret.yaml`.

## Refreshing the list

Free models rotate often.

1. List candidates: `curl -s https://openrouter.ai/api/v1/models`, keep entries with `pricing.prompt` and `pricing.completion` both `"0"` and `tools` in `supported_parameters`. Do not filter on the `:free` suffix.
2. Probe each through LiteLLM with a one-word request; keep only `200`s. Known gated (403 to non-harness callers as of 2026-10): `thinkingmachines/inkling:free`, `inkling-small:free`.
3. Edit `free-pool.yaml`: one document per rung named `free-pool-openrouter-<model>`, `maxInputTokens` = the model's context length, `supportsVision` only for image-input models, renumber `order:` with `openrouter/free` last.
