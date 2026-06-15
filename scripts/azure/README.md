# Azure Examples

These scripts are intentionally small examples for a Foundry endpoint and API key.

They use environment variables instead of Azure CLI login so they can run without Azure subscription access.

## Requirements

Set these environment variables before running the examples:

- `FOUNDRY_BASE_URL` or `FOUNDRY_ENDPOINT`
- `FOUNDRY_API_KEY`
- `FOUNDRY_MODEL` (optional default model name)

The scripts also accept common Azure aliases such as `OPENAI_BASE_URL`, `AZURE_OPENAI_ENDPOINT`, `OPENAI_API_KEY`, and `AZURE_OPENAI_API_KEY`.

Example:

```bash
export FOUNDRY_BASE_URL="https://your-resource.services.ai.azure.com/openai/v1"
export FOUNDRY_API_KEY="your-key"
export FOUNDRY_MODEL="DeepSeek-V4-Flash"
```

## Scripts

- `infer_chat.py`: send a single chat prompt to a deployed model

## Examples

Run a simple prompt:

```bash
uv run python scripts/azure/infer_chat.py \
  --prompt "Explain matrix multiplication in simple terms."
```

Override the model name:

```bash
uv run python scripts/azure/infer_chat.py \
  --model "DeepSeek-V4-Flash" \
  --prompt "Summarize the role of attention in transformers."
```

## Notes

- These examples assume an OpenAI-compatible Foundry endpoint.
- Use the Foundry UI to inspect deployments for a project endpoint. This script set is focused on runtime validation.
- Keep keys out of shell history when possible.
- For classroom demos, prefer short prompts and small `max_tokens` values to control cost.
