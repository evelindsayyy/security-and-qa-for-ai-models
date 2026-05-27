# security scanning tests — modelscan + fickling

exploratory scripts for **pillar 1 (security)**. proves we can download a HF model,
run modelscan + fickling in an isolated container, and produce json output our
future `scanner/` module can match.

---

## what lives where

| thing | location | in git? |
|---|---|---|
| scripts, dockerfile, this readme | `testing/security_scanning_tests/` | yes |
| downloaded model (~850mb) | `testing/security_scanning_tests/models/` | no (gitignored) |
| scan output json | `testing/security_scanning_tests/output/` | no (gitignored) |
| example output for the team | `testing/fixtures/sample_scan_result.distilbert.json` | yes (small file, copy one run) |

**container filesystem** = ephemeral (gone on exit).
**bind-mounted `models/` and `output/`** = on dgx disk, persists after exit.

**inside the container**, output is at `/output/` (leading slash).
**on the dgx host**, the same files are at `./output/` in this folder.

---

## files in this folder

| file | what it does |
|---|---|
| `Dockerfile` | builds isolated python 3.11 image with huggingface_hub, modelscan, fickling |
| `docker-compose.yml` | mounts `./models` and `./output`, optional `HF_TOKEN` |
| `scan_helpers.py` | shared modelscan api + fickling pytorch zip handling |
| `download_model.py` | pulls `distilbert-base-uncased` from hugging face |
| `run_modelscan.py` | runs modelscan, writes json + txt reports |
| `run_fickling.py` | analyzes pickle inside `pytorch_model.bin` with fickling |
| `run_combined_scan.py` | merges both into one json (near-future scanner output shape) |

output schema docs: [`docs/scanner-output-format.md`](../../docs/scanner-output-format.md)

---

## step 1 — local (your mac)

commit and push after pulling latest changes:

```bash
git add testing/security_scanning_tests/
git commit -m "fix modelscan and fickling api usage in security scanning tests"
git push
```

---

## step 2 — dgx setup

ssh in:

```bash
ssh jkm75@asus-dgx-04.oit.duke.edu
```

pull latest:

```bash
cd ~/security-and-qa-for-ai-models
git pull
cd testing/security_scanning_tests
mkdir -p models output
```

**optional:** faster HF downloads:

```bash
export HF_TOKEN=hf_your_token_here
```

---

## step 3 — rebuild docker image (required after script changes)

```bash
docker compose build
```

re-run this every time you `git pull` script changes. the image bakes in `*.py` at build time.

---

## step 4 — enter the container

```bash
docker compose run --rm scanner bash
```

prompt looks like `root@....:/app#`. you are inside the isolated env now.

---

## step 5 — run scripts (inside container, in order)

model already downloaded? skip step 1.

```bash
# 1) download model (skip if models/distilbert-base-uncased/ already exists)
python download_model.py

# 2) modelscan — checks model files for unsafe pickle ops etc.
python run_modelscan.py

# 3) fickling — analyzes pickle inside pytorch_model.bin
python run_fickling.py

# 4) combined report — single json merging both tools
python run_combined_scan.py
```

check output **inside container** (note the leading slash):

```bash
ls /output/
cat /output/combined_scan.json
```

exit when done:

```bash
exit
```

---

## step 6 — check output on dgx host (outside container)

```bash
ls ~/security-and-qa-for-ai-models/testing/security_scanning_tests/output/
cat ~/security-and-qa-for-ai-models/testing/security_scanning_tests/output/combined_scan.json
```

these files stay on the dgx even though the container is gone.

---

## step 7 — record results for the team (optional)

```bash
cp output/combined_scan.json ../fixtures/sample_scan_result.distilbert.json
git add ../fixtures/sample_scan_result.distilbert.json
git commit -m "add sample distilbert scan output fixture"
git push
```

do **not** commit `models/` or every scan run — too big.

---

## fixes applied (may 2026)

| issue | cause | fix |
|---|---|---|
| `No such option '--output-format'` | modelscan cli changed | scripts now use modelscan python api |
| `fickling has no attribute 'Pickled'` | wrong import path | use `from fickling.fickle import Pickled` via `scan_helpers.py` |
| fickling crash on `.bin` | pytorch .bin is a zip, not raw pickle | extract `archive/data.pkl` first |
| `ls output/` fails in container | wrong path | use `/output/` inside container |

---

## troubleshooting

| problem | fix |
|---|---|
| `permission denied` on docker | try `sudo docker compose ...` |
| `ModuleNotFoundError` on dgx host | expected — run scripts **inside** the container |
| stale scripts in container | `git pull` then `docker compose build` again |
| old bad json in output/ | safe to delete and re-run: `rm output/*` |

---

## what comes next

- spike learnings → refactor into `scanner/` (weeks 3–4)
- combined json shape → persisted via api + postgres later
- see `docs/architecture.md` for the full system picture
