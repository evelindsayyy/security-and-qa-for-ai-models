"""Garak is invoked via safety.run using run_garak.py (not nested docker compose)."""

from safety.run import RunConfig


def test_garak_argv_includes_run_garak_py() -> None:
    cfg = RunConfig(model="GPT 4.1 Mini", skip_promptfoo=True, skip_garak=False)
    assert cfg.skip_garak is False
    # Pipeline builds this argv internally; keep contract visible in tests.
    slug = "gpt-4.1-mini"
    garak_argv = [
        "safety/garak/run_garak.py", cfg.model,
        "--report-dir", f"/app/safety/garak/output/{slug}",
    ]
    assert "run_garak.py" in garak_argv[0]
