# free-pool

`free-pool` is a LiteLLM model group of free models from several providers: the "throw cheap work at it" lane. One file per provider in this folder (`nvidia.yaml`, `groq.yaml`, `gemini.yaml`, `openrouter.yaml`), all with `modelName: free-pool`.

## Rules

- **Public material only.** Free tiers log prompts and may train on them (Google states this for free Gemini). No secrets, tokens or personal data.
- **Never a fallback.** No other model group, fallback chain or default points at `free-pool`, so private traffic cannot reach it by accident.
- **Opt-in only.** Give a consumer `free-pool` explicitly; keys without a `models:` list can reach it too.

## Routing

Rungs are tried by `order:` across all providers (strongest first): NVIDIA NIM (1-3), Groq gpt-oss (4), Gemini (5), Groq Qwen (6), OpenRouter (7-13), then `openrouter/free` (a random free model) last at 14.

Free tiers answer `429` when quota runs out and LiteLLM cools that deployment down. It does **not** cool down on `402`/`403`, so a rung that answers `403` is retried on every request: only list models that answer `200` through LiteLLM.

| Provider   | Free limit (itsfree.ai, verified 2026-09-02)                                             | Notes                                     |
| ---------- | ---------------------------------------------------------------------------------------- | ----------------------------------------- |
| NVIDIA NIM | 40 requests/minute, no daily cap                                                         | Phone signup                              |
| Groq       | about 1,000 requests/day, per-model TPM                                                  | Preview models can disappear              |
| Gemini     | free tier, quota per model in AI Studio                                                  | Prompts may be used for training          |
| OpenRouter | 20 requests/minute, 1,000/day across all free models once $10 of credits has been bought | A key is required even for `:free` models |

## Keys

`NVIDIA_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` and `AISTUDIO_API_KEY` (Gemini) in the `litellm` Bitwarden item, mapped in `../../externalsecret.yaml`.

## Refreshing the list

Free models rotate often. For each provider: list candidates, probe each with a one-word request, keep only `200`s, then edit that provider's file. Each rung is one document named `free-pool-<provider>-<model>`; set `maxInputTokens` to the model's context length, `supportsVision` only for image-input models, and keep `order:` unique and ascending across all files (see Routing).

Probe request body, used below: `B='{"model":"%s","messages":[{"role":"user","content":"Reply with the single word: ok"}],"max_tokens":16}'`

### NVIDIA NIM (`nvidia.yaml`)

- List: `curl -s https://integrate.api.nvidia.com/v1/models | jq -r '.data[].id'` (public, no key). It carries no context length, so read it from the model's page on build.nvidia.com; the declared values are conservative guesses.
- Probe:
    ```sh
    curl -s https://integrate.api.nvidia.com/v1/chat/completions -H "Authorization: Bearer $NVIDIA_API_KEY" -H 'content-type: application/json' -d "$(printf "$B" <id>)"
    ```
- LiteLLM id: `nvidia_nim/<id>`.

### Groq (`groq.yaml`)

- List: `curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY" | jq -r '.data[] | [.id, .context_window] | @tsv'`. Skip whisper, orpheus and prompt-guard/safeguard models. Preview models can be withdrawn without notice.
- Probe: same call as NIM against `https://api.groq.com/openai/v1/chat/completions` with `$GROQ_API_KEY`.
- LiteLLM id: `groq/<id>`.

### Gemini (`gemini.yaml`)

- List models: `curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" | jq -r '.models[] | select(.supportedGenerationMethods | index("generateContent")) | [.name, .inputTokenLimit, .outputTokenLimit] | @tsv'`.
- Which of them are free is on the pricing page: <https://ai.google.dev/gemini-api/docs/pricing> (free tier = "Free of charge" input and output). Quotas are per project in AI Studio: <https://aistudio.google.com/rate-limit>.
- Probe:
    ```sh
    curl -s "https://generativelanguage.googleapis.com/v1beta/models/<id>:generateContent?key=$GEMINI_API_KEY" -H 'content-type: application/json' -d '{"contents":[{"parts":[{"text":"Reply with the single word: ok"}]}]}'
    ```
- LiteLLM id: `gemini/<id>`.

### OpenRouter (`openrouter.yaml`)

- List: `curl -s https://openrouter.ai/api/v1/models`, keep entries where `pricing.prompt` and `pricing.completion` are both `"0"` and `supported_parameters` includes `tools`. Do **not** filter on the `:free` suffix; the pricing fields are the source of truth.
- Probe:
    ```sh
    curl -s https://openrouter.ai/api/v1/chat/completions -H "Authorization: Bearer $OPENROUTER_API_KEY" -H 'content-type: application/json' -d "$(printf "$B" <id>)"
    ```
- Known gated (403 to non-harness callers as of 2026-10): `thinkingmachines/inkling:free`, `inkling-small:free`. Never list an unverified rung.
- LiteLLM id: `openrouter/<id>`; `openrouter/openrouter/free` stays last.
