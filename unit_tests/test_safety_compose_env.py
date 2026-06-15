from pathlib import Path


def test_safety_compose_sets_garak_home_dirs() -> None:
    compose = Path("safety/docker/compose.yml").read_text(encoding="utf-8")

    assert "HOME=/app/safety/garak/output/.garak-home" in compose
    assert "XDG_DATA_HOME=/app/safety/garak/output/.garak-data" in compose
    assert "XDG_CACHE_HOME=/app/safety/garak/output/.garak-cache" in compose
    assert "XDG_CONFIG_HOME=/app/safety/garak/output/.garak-config" in compose


def test_safety_compose_forwards_garak_api_key_env() -> None:
    compose = Path("safety/docker/compose.yml").read_text(encoding="utf-8")

    assert "OPENAICOMPATIBLE_API_KEY=${OPENAI_API_KEY:-}" in compose
    assert "OPENAI_API_KEY=${OPENAI_API_KEY:-}" in compose
