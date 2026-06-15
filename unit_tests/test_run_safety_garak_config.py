from pathlib import Path


def test_garak_config_path_uses_absolute_mount_path() -> None:
    script = Path("safety/run_safety.sh").read_text(encoding="utf-8")

    assert 'GARAK_RUN_CFG="/app/safety/garak/output/${SLUG}/garak_run.yaml"' in script
    assert 'python -m garak --config "${GARAK_RUN_CFG}"' in script
