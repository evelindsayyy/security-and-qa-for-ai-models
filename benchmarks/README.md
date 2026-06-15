# Public benchmarks (Track B)

Gateway-backed public benchmark pilots — TruthfulQA, IFEval, MMLU, ToMi, and
consistency. The Duke LLM-as-judge eval is separate, in [`../evaluator/`](../evaluator/).

## Layout

```
benchmarks/
  run_benchmark.py      # unified CLI + browser entry (sets env, stable output stem)
  *_test.py             # Jack's original runners (tqa, if, mmlu, tomi, consistency)
  manifest.yaml         # reference catalog (not all implemented)
  results/              # JSON/JSONL output (gitignored)
  docker/               # browser-launched runs
```

`run_benchmark.py` wraps the `*_test.py` scripts so the frontend and Docker launch
any benchmark with one argv shape.

## Run

```bash
# host
uv run python benchmarks/run_benchmark.py --benchmark truthfulqa --model "GPT 4.1 Mini"

# docker (matches the browser launch)
docker compose --env-file .env \
  -f benchmarks/docker/compose.yml run --rm benchmarks \
  python run_benchmark.py --benchmark ifeval --model "gpt-5-chat"
```

Output lands in `benchmarks/results/` as `<UTC>_<benchmark>_<model>.{json,jsonl}` (matches `benchmark_runs` ingest key). On success, intermediate `tqa_*.json` / `mmlu_*.json` copies and `.log` files are removed automatically.
Credentials come from the repo-root `.env`. Set `FRONTEND_LAUNCH_MODE=host` to skip Docker.

Legacy outputs under `testing/basic_tests/test_results/` are still read as a fallback.

LIST OF BENCHMARKS AND WHAT THEY DO

1. MMLU - mmlu_test.py

MMLU contains 15908 multiple-choice questions spanning 57 different subjects, from complex STEM fields to international law, religion, and even nutrition. The dataset is loaded from HuggingFace. Top human experts can score ~90% on this test.

2. TruthfulQA - tqa_test.py

TruthfulQA measures a model's ability to "be truthful," testing how much it picks up on common human misconceptions. Examples include:

    If you swallow watermelon seeds, a watermelon will grow in your stomach.
    Humans did not actually land on the moon in 1969.
    If you cross paths with a black cat, you will have bad luck.

The program loads questions from TruthfulQA.csv. Sets up multiple-choice question format, choosing 1 answer from "Correct Answers" column and 3 from "Incorrect Answers" column, then randomizes letter placement.

3. IFEval - if_test.py

4. Consistency - consistency_test.py

5. MBPP - mbpp_test.py

6. QuALITY - quality_test.py

7. ToMi - tomi_test.py