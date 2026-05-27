# security scanning tests — modelscan + fickling

exploratory scripts for **pillar 1 (security)**. proves we can download a HF model,
run modelscan + fickling in an isolated container, and produce json output our
future `scanner/` module can match.

---

## what lives where

| thing | location | in git? |
|---|---|---|
| scripts, dockerfile, this readme | `testing/scanner_spike/` | yes |
| downloaded model (~850mb) | `testing/scanner_spike/models/` | no (gitignored) |
| scan output json | `testing/scanner_spike/output/` | no (gitignored) |
| example output for the team | `testing/fixtures/sample_scan_result.distilbert.json` | yes (small file, copy one run) |

**container filesystem** = ephemeral (gone on exit).
**bind-mounted `models/` and `output/`** = on dgx disk, persists after exit.

---

## files in this folder

| file | what it does |
|---|---|
| `Dockerfile` | builds isolated python 3.11 image with huggingface_hub, modelscan, fickling |
| `docker-compose.yml` | mounts `./models` and `./output`, optional `HF_TOKEN` |
| `download_model.py` | pulls `distilbert-base-uncased` from hugging face |
| `run_modelscan.py` | runs modelscan, writes json + txt reports |
| `run_fickling.py` | analyzes `pytorch_model.bin` pickle with fickling |
| `run_combined_scan.py` | merges both into one json (near-future scanner output shape) |

output schema docs: [`docs/scanner-output-format.md`](../../docs/scanner-output-format.md)

---


## step 1 - dgx setup (one time)

ssh in:

```bash
ssh netid@asus-dgx-04.oit.duke.edu
```

clone the repo (or pull if you already have it):

```bash
cd ~
git clone https://gitlab.oit.duke.edu/codeplus/security-and-qa-for-ai-models.git
# or if already cloned
# cd ~/security-and-qa-for-ai-models && git pull
```

go to the security_scanning_tests folder:

```bash
cd ~/security-and-qa-for-ai-models/testing/security_scanning_tests
mkdir -p models output
```

---

## step 2 — build the docker image (on dgx)

from `testing/security_scanning_tests/`:

```bash
docker compose build
```

this reads `Dockerfile`, installs deps, copies `*.py` into the image.
re-run after you change scripts and `git pull`.

---

## step 4 — enter the container (on dgx)

```bash
docker compose run --rm scanner bash
```

you'll see a prompt like `root@....:/app#`. 
`/models` and `/output` are the same folders as `./models` and `./output` on the dgx.

---

## step 3 — run scripts (inside container, in order)

```bash
# 1) download model 
python download_model.py

# 2) modelscan — checks model files for unsafe pickle ops etc.
python run_modelscan.py

# 3) fickling — deep dive on pytorch_model.bin pickle AST
python run_fickling.py

# 4) combined report — single json merging both tools
python run_combined_scan.py
```

exit when done:

```bash
exit
```

---

## step 4 — check output persisted on dgx (outside container)

```bash
ls ~/security-and-qa-for-ai-models/testing/scanner_spike/output/
cat ~/security-and-qa-for-ai-models/testing/scanner_spike/output/combined_scan.json
```

these files stay on the dgx even though the container is gone.

---

## step 5 — record results for the team (optional)

copy one representative combined report into git as a fixture:

```bash
cp output/combined_scan.json ../fixtures/sample_scan_result.distilbert.json
git add ../fixtures/sample_scan_result.distilbert.json
git commit -m "add sample distilbert scan output fixture"
git push
```

do **not** commit `models/` or every scan run — too big.

---


