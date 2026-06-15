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

IFEval measures a model's ability to follow exact instructions according to the prompt. The dataset is loaded from HuggingFace. There are also files instructions_registry.py, instructions_util.py, and instructions.py, which helps set up the official judge.

4. Consistency - consistency_test.py

Consistency measures a model's ability to give the same answer when a prompt is paraphrased. The questions are in consistency_questions.json. The similarity of the answers are measured using BERTscore.

5. MBPP - mbpp_test.py

MBPP tests a model's ability to generate correct code. It is a set of Python problems built to be solved by entry-level programmers. The questions are loaded from HuggingFace.

6. QuALITY - quality_test.py

QuALITY tests a model's reading comprehension. The questions are loaded from HuggingFace. It makes the model read a long passage of text, then asks it multiple-choice questions about the passage.

7. ToMi - tomi_test.py

ToMi is a test often used in psychology. It tests one's ability to perceive others' beliefs, even when they might be false. The questions are loaded from tomi_questions.txt. An example question is:

    Jackson entered the hall.
    Chloe entered the hall.
    The boots is in the bathtub.
    Jackson exited the hall.
    Jackson entered the dining_room.
    Chloe moved the boots to the pantry.
    Where does Chloe think that Jackson searches for the boots?

(The correct answer is "bathtub")