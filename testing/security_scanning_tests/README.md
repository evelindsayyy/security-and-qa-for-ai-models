# security scanning tests

dockerized spike for pillar 1 — download a model, run modelscan + fickling, write json reports.

output schema: [`docs/scanner-output-format.md`](../../docs/scanner-output-format.md)

---

## pipeline (start to end)

```
dgx host                          docker container (/app)
────────                          ──────────────────────
git pull repo
docker compose build    ───────►  image built from:
  │                                 - requirements.txt (deps)
  │                                 - testing/security_scanning_tests/*.py
docker compose run bash ───────►  interactive shell
  │
  │  ./models  ──bind mount──►   /models   (downloaded weights, persists)
  │  ./output  ──bind mount──►   /output  (scan reports, persists)
  │
  │                               python download_model.py  → hf → /models/
  │                               python run_modelscan.py   → /output/modelscan_*
  │                               python run_fickling.py    → /output/fickling_*
  │                               python run_combined_scan.py → /output/<MODEL_ID>/combined_scan.json
  │
exit                            container deleted (models/ + output/ stay on dgx)
```

---

## dgx quick start

```bash
cd ~/security-and-qa-for-ai-models/testing/security_scanning_tests
git pull
mkdir -p models output

docker compose build
docker compose run --rm scanner bash
```

inside container (default model: distilbert-base-uncased):

```bash
python download_model.py
python run_modelscan.py
python run_fickling.py
python run_combined_scan.py
ls /output/distilbert-base-uncased/
exit
```

---

## files

| file | role |
|---|---|
| `Dockerfile` | builds image from repo root requirements.txt + scripts |
| `docker-compose.yml` | mounts models/output, runs as your uid |
| `scan_helpers.py` | shared modelscan + fickling logic |
| `download_model.py` | pulls distilbert to /models/ |
| `run_modelscan.py` | full modelscan → json + txt |
| `run_fickling.py` | fickling on .bin → json + txt |
| `run_combined_scan.py` | merged report for dashboard prototype |

rebuild after `git pull`: `docker compose build`

---

## testing other models

pick a hugging face repo id, set `MODEL_ID`, run the same scripts. outputs go to
`/output/<model-id>/` so different models don't overwrite each other.

### good models to try

| MODEL_ID | size | why test it |
|---|---|---|
| `distilbert-base-uncased` | ~260mb | default — legacy stacked pickle `.bin` |
| `gpt2` | ~500mb | different arch, also has `pytorch_model.bin` |
| `bert-base-uncased` | ~440mb | same era as distilbert, sanity comparison |
| `facebook/opt-125m` | ~250mb | small decoder model |
| `sentence-transformers/all-MiniLM-L6-v2` | ~90mb | tiny, good for quick reruns |

**safetensors-only repos** (no `.bin` file): modelscan still runs, fickling skips with an error.

### commands (inside container)

default model (distilbert):

```bash
python download_model.py
python run_modelscan.py
python run_fickling.py
python run_combined_scan.py
ls /output/distilbert-base-uncased/
```

different model — set env var before each script (or export once in the shell):

```bash
export MODEL_ID=gpt2
python download_model.py
python run_modelscan.py
python run_fickling.py
python run_combined_scan.py
cat /output/gpt2/combined_scan.json
```

org/model ids work too:

```bash
export MODEL_ID=sentence-transformers/all-MiniLM-L6-v2
python download_model.py
python run_combined_scan.py
ls /output/sentence-transformers--all-MiniLM-L6-v2/
```

### from dgx host (before entering container)

pass `MODEL_ID` into docker so it's set automatically:

```bash
export UID=$(id -u) GID=$(id -g)
export MODEL_ID=gpt2
docker compose run --rm scanner bash
# then run scripts inside — MODEL_ID is already set
```

compare two models:

```bash
export MODEL_ID=distilbert-base-uncased
python run_combined_scan.py

export MODEL_ID=gpt2
python download_model.py
python run_combined_scan.py

ls /output/
# distilbert-base-uncased/combined_scan.json
# gpt2/combined_scan.json
```

---

## troubleshooting

| problem | fix |
|---|---|
| `permission denied` on output/ | `sudo chown -R $USER:$USER output/`, always export `UID`/`GID` |
| `UID variable is not set` warning | `export UID=$(id -u) GID=$(id -g)` before compose |
| scripts stale in container | `git pull` then `docker compose build` |
