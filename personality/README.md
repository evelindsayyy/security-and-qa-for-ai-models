# Personality (BFI)

Fun Big Five Inventory runs for gateway models. **Not** part of benchmarks or cross-pillar rollup.

## What it measures

The [Big Five Inventory (BFI-44)](https://www.phenxtoolkit.org/protocols/view/121101) asks 44 self-report Likert items (1–5). Scores are averaged per trait:

- Extraversion
- Agreeableness
- Conscientiousness
- Neuroticism
- Openness

This is entertainment / curiosity — LLM “personality” is not human personality.

## CLI

```bash
# Docker (recommended)
docker compose --env-file .env -f personality/docker/compose.yml run --rm personality \
  python run_personality.py --model "GPT 4.1 Mini"

# Host
uv run python personality/run_personality.py --model "GPT 4.1 Mini"
```

Artifacts land in `personality/results/` as `{timestamp}_bfi_{model}.json`.

## Browser

**Personality** in the sidebar → pick a gateway model → Start run. Requires Duke NetID login (same as other pillars).
