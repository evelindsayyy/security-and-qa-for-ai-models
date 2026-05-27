# security scanning tests

dockerized spike for pillar 1 — download a HF model, run modelscan + fickling, write json reports.

output schema: [`docs/scanner-output-format.md`](../../docs/scanner-output-format.md)

---

## what lives where

| in git | on dgx only (gitignored) |
|---|---|
| scripts, dockerfile, this readme | `models/` (~850mb download) |
| | `output/` (scan json) |

container = ephemeral. bind-mounted `models/` and `output/` persist on dgx after exit.

---

## dgx quick start

```bash
cd ~/security-and-qa-for-ai-models/testing/security_scanning_tests
git pull
mkdir -p models output

export UID=$(id -u) GID=$(id -g)   # so output/ isn't owned by root
docker compose build
docker compose run --rm scanner bash
```

inside container:

```bash
python download_model.py        # skip if model already in models/
python run_modelscan.py
python run_fickling.py
python run_combined_scan.py
ls /output/
exit
```

on dgx host:

```bash
cat output/combined_scan.json
```

optional — save one result for the team:

```bash
cp output/combined_scan.json ../fixtures/sample_scan_result.distilbert.json
```

---

## files

| file | does |
|---|---|
| `download_model.py` | pulls distilbert-base-uncased |
| `run_modelscan.py` | modelscan via python api |
| `run_fickling.py` | fickling on pytorch_model.bin |
| `run_combined_scan.py` | merges both into one json |
| `scan_helpers.py` | shared logic (zip + legacy .bin formats) |

rebuild image after `git pull`: `docker compose build`

---

## troubleshooting

| problem | fix |
|---|---|
| `permission denied` on output/ | `sudo chown -R $USER:$USER output/`, always export `UID`/`GID` before compose |
| `BadZipFile` on .bin | distilbert uses stacked pickle not zip — handled in scan_helpers |
| scripts stale in container | `git pull` then `docker compose build` |
