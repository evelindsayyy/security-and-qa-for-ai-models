# Promptfoo Output

This directory stores generated Promptfoo evaluation results for safety/red-team testing against Duke AI Gateway models.

Large output files in this directory are intentionally ignored by Git. Keep only this README tracked so the directory exists after cloning or pulling the repo.

Example:

```bash
promptfoo eval -c promptfooconfig.yaml \
  --output output/gpt41mini-results.jsonl \
  --output output/gpt41mini-report.html