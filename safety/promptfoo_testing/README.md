# Promptfoo Testing

This directory is for Promptfoo safety and red-team experiments against Duke AI Gateway models.

Use this space for Promptfoo configs, Docker setup, notes, and reproducible command examples. Generated red-team cases, reports, logs, and Promptfoo local state should go in `output/`, which is ignored by Git except for its README.

Suggested layout:

```text
safety/promptfoo_testing/
  README.md
  promptfooconfig.yaml
  promptfooconfig.redteam.yaml
  docker/
    Dockerfile
    compose.yml
    .env.example
  output/
    README.md
```

Do not commit API keys, `.env` files, or large generated Promptfoo outputs. Keep checked-in files small enough for teammates to inspect and rerun.
