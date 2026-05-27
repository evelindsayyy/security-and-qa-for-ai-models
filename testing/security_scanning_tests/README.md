# security scanning tests

dockerized spike for pillar 1 — download a model, run modelscan + fickling, write json reports.

output schema: [`docs/scanner-output-format.md`](../../docs/scanner-output-format.md)

---

## one-time dgx setup

tell docker to run as **your user**, not root. otherwise `models/` and `output/` files
are owned by root and you can't write or delete them without a workaround.

```bash
cd ~/security-and-qa-for-ai-models/testing/security_scanning_tests
cp .env.example .env
sed -i "s/^UID=.*/UID=$(id -u)/" .env
sed -i "s/^GID=.*/GID=$(id -g)/" .env
cat .env    # should show your numeric UID/GID, not 1000
```

`UID`/`GID` here is **not sudo** — just your normal user id from `id -u`.

if you already ran scans before creating `.env`, fix folder ownership once (no sudo).

**must run from `testing/security_scanning_tests/`** — not repo root:

```bash
cd ~/security-and-qa-for-ai-models/testing/security_scanning_tests

docker run --rm -v "${PWD}/models:/work" ubuntu chown -R $(id -u):$(id -g) /work
docker run --rm -v "${PWD}/output:/work" ubuntu chown -R $(id -u):$(id -g) /work
```

if that still fails, nuke and recreate `models/` (from same directory):

```bash
cd ~/security-and-qa-for-ai-models/testing/security_scanning_tests
docker run --rm -v "${PWD}:/work" -w /work ubuntu rm -rf models
mkdir models
ls -ld models    # should show jkm75, not root
```

prompt may show `I have no name!` — harmless, your uid just isn't in the container's passwd file.

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
echo $MODEL_ID
python download_model.py
python run_modelscan.py
python run_fickling.py
python run_combined_scan.py
ls /output/distilbert-base-uncased/
exit
```

do **not** run python on the dgx host — deps only exist inside the container.

---

## models to test

set `MODEL_ID` in `.env` or pass when starting compose: `MODEL_ID=gpt2 docker compose run --rm scanner bash`

on disk, org/model ids use `--` not `/` (e.g. `facebook/opt-125m` → `/models/facebook--opt-125m/`).

### tier 1 — start here (small, both tools work)

| MODEL_ID | size | notes |
|---|---|---|
| `distilbert-base-uncased` | ~260mb | default — legacy stacked pickle `.bin` |
| `gpt2` | ~500mb | classic decoder, has `.bin` |
| `bert-base-uncased` | ~440mb | same era as distilbert |
| `EleutherAI/pythia-160m` | ~300mb | tiny open lm |
| `facebook/opt-125m` | ~250mb | small decoder, org/model id |
| `sentence-transformers/all-MiniLM-L6-v2` | ~90mb | fast reruns |

### tier 2 — medium (more disk/time on shared dgx)

| MODEL_ID | size | notes |
|---|---|---|
| `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | ~2gb | modern small llm |
| `microsoft/phi-2` | ~5gb | popular small model, long download |
| `google/gemma-2-2b` | ~5gb | **needs HF_TOKEN** + license accept on huggingface.co |

### gemma — read before trying

- gemma repos require accepting Google's license on huggingface + `HF_TOKEN` in `.env`
- most gemma weights are **safetensors-only** — modelscan runs, fickling skips (no `.bin`)
- too big for a quick spike unless you specifically need it — try `google/gemma-2-2b` not 7b/9b

### tier 3 — skip on shared dgx unless you need them

7b+ models (llama, mistral, gemma-7b, etc.) — long downloads, eat shared disk.

### what each tool covers

| format | modelscan | fickling |
|---|---|---|
| `pytorch_model.bin` (pickle) | yes | yes |
| `model.safetensors` | skipped by modelscan 0.8.x often | n/a (not pickle) |
| config, tokenizer, vocab | skipped | n/a |

safetensors-only repos: modelscan still useful, fickling will error — expected.

### example — facebook/opt-125m

in `.env`: `MODEL_ID=facebook/opt-125m`

```bash
docker compose build
docker compose run --rm scanner bash
python download_model.py    # -> /models/facebook--opt-125m/
python run_combined_scan.py
cat /output/facebook--opt-125m/combined_scan.json
```

---

## fixing root-owned files (no sudo)

delete old output:

```bash
docker run --rm -v "${PWD}/output:/work" -w /work ubuntu rm -rf /work/*
```

fix `models/` or `output/` permissions:

```bash
docker run --rm -v "${PWD}/models:/work" ubuntu chown -R $(id -u):$(id -g) /work
docker run --rm -v "${PWD}/output:/work" ubuntu chown -R $(id -u):$(id -g) /work
```

use `${PWD}` uppercase in bash.

---

## troubleshooting

| problem | cause | fix |
|---|---|---|
| `Permission denied: '/models/...'` | `models/` owned by root, or chown ran from **repo root** not `testing/security_scanning_tests/` | cd to correct dir, chown again (see above) or rm+mkdir models |
| `Permission denied: '/.cache'` | hf cache defaults to container home | fixed via `HF_HOME` in compose — rebuild image and re-run compose |
| `Permission denied` deleting output | same for `output/` | chown or rm via ubuntu container |
| `UID variable is not set` | no `.env` file | copy `.env.example`, set UID/GID |
| `I have no name!` in prompt | uid not in container passwd | harmless, ignore |
| still downloads distilbert | stale docker image | `git pull` + `docker compose build` |
| gemma download fails | license / token | accept license on hf, set `HF_TOKEN` in `.env` |
| fickling errors on gemma/modern models | safetensors-only, no `.bin` | expected — modelscan still runs |
| `python` not found on dgx host | ran script outside container | use `docker compose run` |
