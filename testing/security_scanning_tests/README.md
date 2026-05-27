# security scanning tests

dockerized spike for pillar 1 — download a model, run modelscan + fickling, write json reports.

output schema: [`docs/scanner-output-format.md`](../../docs/scanner-output-format.md)

---

## one-time dgx setup 

tell docker to run as **your user**, not root. otherwise scan output
files are owned by root and you can't delete them normally.

```bash
cd ~/security-and-qa-for-ai-models/testing/security_scanning_tests
cp .env.example .env
sed -i "s/^UID=.*/UID=$(id -u)/" .env
sed -i "s/^GID=.*/GID=$(id -g)/" .env
cat .env    # should show your numeric UID/GID, not 1000
```

---

## pipeline (start to end)

```
dgx host                          docker container (/app)
────────                          ──────────────────────
git pull repo
create .env (once)      ───────►  docker runs as your uid (not root)
docker compose build    ───────►  image built from requirements.txt + scripts
docker compose run bash ───────►  interactive shell
  │
  │  ./models  ──bind mount──►   /models
  │  ./output  ──bind mount──►   /output/<MODEL_ID>/
  │
  │                               python download_model.py
  │                               python run_modelscan.py
  │                               python run_fickling.py
  │                               python run_combined_scan.py
  │
exit                            container deleted (models/ + output/ stay on dgx)
```

---

## dgx quick start

**after every `git pull`, run `docker compose build`** 

```bash
cd ~/security-and-qa-for-ai-models/testing/security_scanning_tests
git pull
mkdir -p models output

docker compose build
docker compose run --rm scanner bash
```

inside container:

```bash
echo $MODEL_ID    # from .env — default distilbert-base-uncased
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
| `.env` | your UID/GID/MODEL_ID — create once from `.env.example`, gitignored |
| `Dockerfile` | builds image from repo root requirements.txt + scripts |
| `docker-compose.yml` | mounts models/output, runs as your uid from `.env` |
| `scan_helpers.py` | shared modelscan + fickling logic |
| `download_model.py` | pulls model to /models/ |
| `run_modelscan.py` | full modelscan → json + txt |
| `run_fickling.py` | fickling on .bin → json + txt |
| `run_combined_scan.py` | merged report |

---

## testing other models

set `MODEL_ID` in `.env` or export before `docker compose run`:

```bash
# option a — edit .env permanently
echo "MODEL_ID=gpt2" >> .env   # or edit the line

# option b — one-off for this session
MODEL_ID=gpt2 docker compose run --rm scanner bash
```

| MODEL_ID | size | why |
|---|---|---|
| `distilbert-base-uncased` | ~260mb | default — legacy stacked pickle |
| `gpt2` | ~500mb | different arch |
| `bert-base-uncased` | ~440mb | compare to distilbert |
| `facebook/opt-125m` | ~250mb | small decoder |
| `sentence-transformers/all-MiniLM-L6-v2` | ~90mb | quick reruns |

safetensors-only repos: modelscan works, fickling errors (no `.bin`) — expected.

inside container after `export MODEL_ID=gpt2` or setting in `.env`:

```bash
python download_model.py      # MODEL_ID=gpt2, -> /models/gpt2
python run_combined_scan.py
cat /output/gpt2/combined_scan.json
```

---


## troubleshooting

| problem | fix |
|---|---|
| `UID variable is not set` warning | create `.env` from `.env.example`, set UID/GID with `id -u` / `id -g` |
| output owned by root, can't delete | cleanup command above, then fix `.env` so it doesn't happen again |
| still downloads distilbert after MODEL_ID=gpt2 | `docker compose build` after `git pull`, check `echo $MODEL_ID` in container |
| `python` not found on dgx host | run scripts inside container only |
| scripts stale | `git pull` then `docker compose build` |
