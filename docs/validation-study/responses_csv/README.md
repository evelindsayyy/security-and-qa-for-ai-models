# Drop the rater survey exports here

`analyze.py` reads every `rater_*.csv` in this folder. To produce the headline
Cohen's κ:

1. In Qualtrics, export **each rater's survey** as CSV (numeric or text values —
   the answer cells must read `Response 1` / `Response 2` / `About the same`).
2. Save them here named exactly **`rater_01.csv` … `rater_06.csv`**. The two-digit
   number is the join key and MUST match the `rater` column in
   `../rater_map.csv` (which uses `01`–`06`).
3. From the repo root, run:

   ```
   uv run python docs/validation-study/analyze.py
   ```

   (Optionally `--responses-dir docs/validation-study/responses_csv`; that's the
   default.)

The CSV shape `analyze.py` expects (Qualtrics default export): header row 1 has
question-ID columns starting `itm_`, then two Qualtrics metadata rows (skipped),
then one data row per response.

This folder is intentionally empty except for this README until the exports are
added.
