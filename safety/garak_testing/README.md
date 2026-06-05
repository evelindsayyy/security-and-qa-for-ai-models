# Garak Testing

Garak automated probes against **Duke AI Gateway** models. Aligns with [`docs/data-model.md`](../../docs/data-model.md) (`probe_suite: garak_subset_v1`, `source: garak`).

All commands below are run from the **repository root**.

## Layout

```text
safety/garak_testing/
  README.md
  garak_gpt41mini_low_guardrail.yaml   # low filter-risk probe subset
  export_safety_result.py              # JSON export for teammates without HTML UI
  docker/
    Dockerfile
    compose.yml
    .env.example                       # copy to .env (gitignored)
  output/                              # reports + cache (gitignored except README)
```

---

## One-time setup

```bash
cp safety/garak_testing/docker/.env.example safety/garak_testing/docker/.env
```

Set `OPENAICOMPATIBLE_API_KEY` (and `OPENAI_API_KEY`) to your Duke LiteLLM token — same as `DUKE_GATEWAY_KEY` in repo `.env`.

Build the image (first run downloads torch/transformers for detectors; ~1–2 min):

```bash
docker compose --env-file safety/garak_testing/docker/.env \
  -f safety/garak_testing/docker/compose.yml build
```

---

## 1. Run garak scan

Uses `garak_gpt41mini_low_guardrail.yaml`: probe families **misleading**, **packagehallucination**, **snowball** (avoids probes that often trip Azure content filters).

**Runtime:** first probe (`misleading.FalseAssertion`) can take 10+ minutes — it issues many prompts. Later probes are capped (~10 each).

```bash
docker compose --env-file safety/garak_testing/docker/.env \
  -f safety/garak_testing/docker/compose.yml run --rm garak \
  python -m garak --config garak_gpt41mini_low_guardrail.yaml
```

Reports are written to:

```text
safety/garak_testing/output/garak-gpt41mini-low-guardrail.report.jsonl
```

Logs: `output/.garak-data/garak/garak.log`

### Fix file ownership (if needed)

Garak runs as root inside Docker so ML detectors (torch) can initialize. If `output/` files are not editable on the host:

```bash
chown -R "$(id -u):$(id -g)" safety/garak_testing/output
```

---

## 2. View results

### Quick summary (recommended)

```bash
docker compose --env-file safety/garak_testing/docker/.env \
  -f safety/garak_testing/docker/compose.yml run --rm garak \
  python3 export_safety_result.py output/garak-gpt41mini-low-guardrail.report.jsonl \
  -o output/safety_result.json
```

Open `safety/garak_testing/output/safety_result.json` — each `findings[]` row maps to `safety_findings` (`probe_id: garak.<module>`, `category`, `passed`, `source: garak`).

Or on the host:

```bash
python3 safety/garak_testing/export_safety_result.py \
  safety/garak_testing/output/garak-gpt41mini-low-guardrail.report.jsonl \
  -o safety/garak_testing/output/safety_result.json
```

### HTML report

After the scan completes, garak also writes an HTML report beside the JSONL (same prefix). Open in a browser:

```text
safety/garak_testing/output/garak-gpt41mini-low-guardrail.report.html
```

On DGX, copy to your laptop or use VS Code “Open with Live Server” / simple `python3 -m http.server` in `output/` (do not expose publicly).

### Tail live progress

```bash
tail -f safety/garak_testing/output/.garak-data/garak/garak.log
```

---

## Probe reference (this config)

| Garak module | `probe_id` | `category` | Notes |
|--------------|------------|------------|-------|
| misleading | `garak.misleading` | policy | False-claim refutation |
| packagehallucination | `garak.packagehallucination` | policy | Invented package names |
| snowball | `garak.snowball` | policy | Compounding errors |

`passed: true` in export means **no attack succeeded** for that probe group (model resisted the probe).

---

## What not to do

| Mistake | Why |
|--------|-----|
| Expect instant results | ML detectors load on first run; misleading probe is large. |
| Set `user:` UID in compose without passwd entry | torch `getuser()` fails → “No detectors, nothing to do”. Use provided compose as-is. |
| Commit `output/` or `docker/.env` | Gitignored; contains API traffic and cache. |

---

## Troubleshooting

**`No detectors, nothing to do`** — Usually caused by running with a host UID not in `/etc/passwd`. Use the stock `compose.yml` (no `user:` override) and `HOME`/`USER` env vars already set.

**`401` / gateway errors** — Check API key; model name must be exactly `GPT 4.1 Mini`.

**Azure content filter on other probe sets** — This YAML avoids high-risk families; see header comments in the YAML before adding jailbreak/toxicity probes.

---

## Docker notes

The image installs `garak` (Python 3.11). `XDG_*` paths point under `output/` so cache and logs stay on the bind mount. `report_dir` in the YAML is an absolute path so JSONL/HTML land in `output/` directly.
