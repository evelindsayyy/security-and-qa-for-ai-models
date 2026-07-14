# Personality

Fun self-report runs for gateway models. **Not** part of benchmarks or cross-pillar rollup.

## Tests

| Key | What it measures |
|-----|------------------|
| `bfi` | [Big Five Inventory (BFI-44)](https://www.phenxtoolkit.org/protocols/view/121101) — five trait averages on a 1–5 scale |
| `compass` | Custom **20-item forced-choice** political compass — Economic Left↔Right and Social Libertarian↔Authoritarian (−100…+100). Not the branded Political Compass Organisation quiz. |

This is entertainment / curiosity — LLM answers are role-play, not beliefs.

## CLI

```bash
# BFI
docker compose --env-file .env -f personality/docker/compose.yml run --rm personality \
  python run_personality.py --test bfi --model "GPT 4.1 Mini"

# Compass
docker compose --env-file .env -f personality/docker/compose.yml run --rm personality \
  python run_personality.py --test compass --model "GPT 4.1 Mini"
```

Artifacts land in `personality/results/` as `{timestamp}_{test}_{model}.json`.

## Browser

**Personality** in the sidebar → choose BFI or Compass → pick a gateway model → Start run.
