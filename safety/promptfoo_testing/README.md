# Promptfoo Testing

Safety **smoke** runs against Duke AI Gateway **GPT 4.1 Mini**. Output names use a `smoke_` prefix so they stay distinct from production scanner artifacts (`scan_result.json`, etc.). Run everything from the **repo root**.

## Files


| Path                              | What it is                                              |
| --------------------------------- | ------------------------------------------------------- |
| `promptfooconfig.yaml`            | **Input** — smoke + Duke policy (5 tests)               |
| `promptfooconfig.redteam.yaml`    | **Input** — red-team plugins                            |
| `export_safety_result.py`         | Converts `smoke_eval.json` → `smoke_safety_result.json` |
| `output/smoke_eval.json`          | **Output** — raw smoke eval                             |
| `output/smoke_redteam_eval.json`  | **Output** — raw red-team eval                          |
| `output/smoke_safety_result.json` | **Output** — normalized for data model (smoke only)     |
| `output/.promptfoo/`              | **Output** — DB for web UI (not a config)               |


`-c` = input YAML. `-o` = results path you choose (use the `smoke_`* names above). Never `promptfoo eval -c output/*.json`.

---

## Step 0 — Setup (once)

```bash
cp safety/promptfoo_testing/docker/.env.example safety/promptfoo_testing/docker/.env
```

Edit `safety/promptfoo_testing/docker/.env`: set `OPENAI_API_KEY` (same as `DUKE_GATEWAY_KEY`).

On DGX, set UID/GID so you can edit `output/`:

```bash
sed -i "s/^UID=.*/UID=$(id -u)/" safety/promptfoo_testing/docker/.env
sed -i "s/^GID=.*/GID=$(id -g)/" safety/promptfoo_testing/docker/.env
```

Build image:

```bash
docker compose --env-file safety/promptfoo_testing/docker/.env \
  -f safety/promptfoo_testing/docker/compose.yml build
```

Shortcut (use in Steps 1–3):

```bash
export DC="docker compose --env-file safety/promptfoo_testing/docker/.env -f safety/promptfoo_testing/docker/compose.yml"
```

**Fresh output folder** (optional):

```bash
rm -rf safety/promptfoo_testing/output/.promptfoo safety/promptfoo_testing/output/logs
rm -f safety/promptfoo_testing/output/smoke_eval.json \
      safety/promptfoo_testing/output/smoke_redteam_eval.json \
      safety/promptfoo_testing/output/smoke_safety_result.json
```

---

## Step 1 — Smoke + Duke policy

**Config:** `promptfooconfig.yaml` — 5 fixed probes, `probe_suite: promptfoo_duke_policy_v1`.

```bash
$DC run --rm promptfoo promptfoo eval \
  -c promptfooconfig.yaml \
  -o output/smoke_eval.json
```


| Flag                        | Does                       |
| --------------------------- | -------------------------- |
| `-c promptfooconfig.yaml`   | Input config               |
| `-o output/smoke_eval.json` | Writes raw smoke eval JSON |


**Expect:** ~5–15 s. Terminal table with pass/fail per probe. Creates `output/smoke_eval.json` and updates `output/.promptfoo/`. Non-zero exit if any test failed — file is still written.

---

## Step 1b — Export to data-model JSON

**When:** Right after Step 1. **Input:** `output/smoke_eval.json` only.

```bash
$DC run --rm promptfoo python3 export_safety_result.py \
  output/smoke_eval.json \
  -o output/smoke_safety_result.json
```

Or on the host:

```bash
python3 safety/promptfoo_testing/export_safety_result.py \
  safety/promptfoo_testing/output/smoke_eval.json \
  -o safety/promptfoo_testing/output/smoke_safety_result.json
```

**Expect:** Prints `pass_rate=… findings=5`. Open `output/smoke_safety_result.json` — one `findings[]` row per probe (`duke.smoke.001` … `duke.policy.004`).

**Not exported yet:** red-team (`output/smoke_redteam_eval.json`) — use Step 3 or `jq` on raw JSON.

---

## Step 2 — Red-team

**Config:** `promptfooconfig.redteam.yaml`. Needs `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true` in `docker/.env`.

```bash
$DC run --rm promptfoo promptfoo redteam run \
  -c promptfooconfig.redteam.yaml \
  -o output/smoke_redteam_eval.json \
  --delay 500 \
  --max-concurrency 1 \
  --force
```


| Flag                                | Does                                                     |
| ----------------------------------- | -------------------------------------------------------- |
| `-o output/smoke_redteam_eval.json` | Raw red-team eval results (JSON)                         |
| `--delay 500`                       | 500 ms between gateway calls                             |
| `--max-concurrency 1`               | Serial requests                                          |
| `--force`                           | Regenerate attacks; omit to reuse cache in `.promptfoo/` |


**Expect:** ~1–3 min. Writes `output/smoke_redteam_eval.json` + updates `output/.promptfoo/`.

---

## Step 3 — View in browser (optional)

After Step 1 and/or 2. Uses `output/.promptfoo/`, not the `smoke_*.json` files.

```bash
$DC run --rm --service-ports promptfoo promptfoo view -p 15500
```

Open [http://localhost:15500](http://localhost:15500) while the command runs.

**DGX:** `ssh -L 15500:localhost:15500 <host>` on laptop, then run on DGX.

**Port busy:** `PROMPTFOO_REPORT_PORT=15501 $DC run --rm --service-ports promptfoo promptfoo view -p 15500` → [http://localhost:15501](http://localhost:15501)

---

## Probes (smoke)


| `probe_id`        | `category` |
| ----------------- | ---------- |
| `duke.smoke.001`  | smoke      |
| `duke.policy.001` | policy     |
| `duke.policy.002` | leakage    |
| `duke.policy.003` | policy     |
| `duke.policy.004` | jailbreak  |


`duke.policy.004` may show ERROR (Azure block); export still marks it passed.

---

## Troubleshooting


| Symptom                                 | Fix                                                          |
| --------------------------------------- | ------------------------------------------------------------ |
| 401 / 403                               | `OPENAI_API_KEY` in `docker/.env`; model id `GPT 4.1 Mini`   |
| `providers` / `targets` missing on `-c` | You used `output/*.json` — use `promptfooconfig*.yaml`       |
| Empty web UI                            | Run Step 1 or 2 first                                        |
| Red-team 0 tests                        | `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true` in `.env` |


