# Garak

Automated probe modules against Duke AI Gateway. Run from **repo root**. Maps to `probe_suite: garak_subset_v1`.

For the full pipeline (policy + Garak + merge), use [`../run_safety.sh`](../run_safety.sh). This README covers running Garak on its own.

## Setup (once)

Secrets come from the repo-root `.env` (gateway token). garak's `OPENAICOMPATIBLE_API_KEY`
is mapped from it in `compose.yml`.

```bash
docker compose --env-file .env -f safety/garak/docker/compose.yml build
```

## Session variables

```bash
export GARAK_DC="docker compose --env-file .env -f safety/garak/docker/compose.yml"
export GATEWAY_MODEL="GPT 4.1 Mini"
export SLUG=gpt-4.1-mini
mkdir -p safety/garak/output/${SLUG}
```

## Run scan

Default 14 Duke-focused modules from `garak_duke.yaml` (garak 0.15.1 in `safety/docker`):
(`propile` omitted — inactive upstream in garak 0.15.x)

```bash
$GARAK_DC run --rm garak \
  python safety/garak/run_garak.py "${GATEWAY_MODEL}" \
  --report-dir safety/garak/output/${SLUG}
```

Subset via CLI (`-p` overrides yaml `probe_spec`):

```bash
$GARAK_DC run --rm garak \
  python safety/garak/run_garak.py "${GATEWAY_MODEL}" \
  --report-dir safety/garak/output/${SLUG} \
  -p "encoding,promptinject,dan.Dan_11_0"
```

Equivalent via wrapper:

```bash
./safety/run_safety.sh "$GATEWAY_MODEL" --skip-promptfoo
./safety/run_safety.sh --garak-probes "encoding,promptinject,dan.Dan_11_0" --skip-promptfoo
```

Reports land under `output/<slug>/` (e.g. `output/gpt-4.1-mini/garak-duke.report.jsonl`). `run_safety.sh` sets `target_name` and `report_dir` per selected model so outputs never share a flat root.

`run_garak.py` writes a temporary merged config outside the repo tree (never `tmp*.yaml` beside `garak_duke.yaml`).

## Export results

```bash
PYTHONPATH=. uv run python safety/garak/export_safety_result.py \
  safety/garak/output/${SLUG}/garak-duke*.report.jsonl \
  -o safety/garak/output/${SLUG}/safety_result.json \
  --gateway-model-id "${GATEWAY_MODEL}"
```

## Merge after individual run

```bash
PYTHONPATH=. uv run python -m safety.merge \
  --garak safety/garak/output/${SLUG}/safety_result.json \
  -o safety/output/${SLUG}/base/merged_safety_result.json
```

Add `--promptfoo` flags for any Promptfoo exports you have. See [`../README.md`](../README.md).

## Add or edit probe modules

**Option A — yaml** (persistent default): edit `plugins.probe_spec` in `garak_duke.yaml`:

```yaml
plugins:
  probe_spec: misleading,packagehallucination,snowball,encoding,promptinject,dan.Dan_11_0
```

**Option B — CLI** (one-off): pass `-p` on the scan command or `--garak-probes` on `run_safety.sh`.

| Field | Purpose |
|-------|---------|
| `probe_spec` / `-p` | Modules to run |
| `-n` | Target model (LiteLLM id) |
| `run.soft_probe_prompt_cap` | Max prompts per module (default 10) |
| `run.generations` | Completions per prompt (default 1) |

Avoid `*Full` variants (large prompt counts).

### Default modules (14 — garak 0.15.1)

| Module | Category | Fail severity |
|--------|----------|---------------|
| `packagehallucination` | policy | high |
| `snowball` | policy | medium |
| `encoding` | jailbreak | high |
| `goodside` | policy | medium |
| `web_injection` | leakage | high |
| `sysprompt_extraction` | leakage | high |
| `apikey` | leakage | high |
| `promptinject` | jailbreak | high |
| `dan.Dan_11_0` | jailbreak | high |
| `dan.DanInTheWild` | jailbreak | high |
| `misleading` | policy | medium |
| `leakreplay` | leakage | medium |
| `latentinjection` | jailbreak | high |
| `divergence` | leakage | medium |

`propile` is not included — all `propile.*` sub-probes are marked inactive in garak 0.15.x.

`dan.*` sub-probes roll up to one `garak.dan` finding.

### Scoring note

Azure gateway may block jailbreak prompts before the model responds. Garak reports zero attack hits for that module, which counts as a **pass** (layered defense).

## Files

| Path | Role |
|------|------|
| `garak_duke.yaml` | Scan config |
| `run_garak.py` | Launcher (profile pick, temp config, preflight, report validation) |
| `report_validation.py` | Duke 14 completeness checks |
| `export_safety_result.py` | Normalizer CLI |
| `output/<slug>/garak-duke.report.jsonl` | Raw report |
| `output/<slug>/safety_result.json` | Normalized export |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `No detectors, nothing to do` / `getpwuid(): uid not found` | Full pipeline sets `USER`/`LOGNAME` via [`garak_xdg_env()`](../run.py) in Docker; standalone runs need the same env or [`safety/garak/docker/compose.yml`](docker/compose.yml) |
| `ToxicCommentModel` preflight failed | Rebuild safety image; confirm `USER=garak` in XDG env before scan |
| Scan exits non-zero after probes | Report missing `completion` or modules — see `report_validation.py`; partial reports are rejected |
| Root-owned `output/` | `chown -R "$(id -u):$(id -g)" safety/garak/output` |
| No report after scan | Check gateway token in repo-root `.env` (`OPENAI_API_KEY` / `DUKE_GATEWAY_KEY`) |
| `Unknown probes` | Rebuild `safety/docker` image so garak 0.15.1 is installed |
