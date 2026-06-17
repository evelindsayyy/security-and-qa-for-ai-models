from pathlib import Path


def test_garak_config_path_uses_absolute_mount_path() -> None:
    script = Path("safety/run_safety.sh").read_text(encoding="utf-8")

    assert 'GARAK_REPORT_DIR="/app/safety/garak/output/${SLUG}"' in script
    assert 'GARAK_RUN_CFG="${GARAK_REPORT_DIR}/garak_run.yaml"' in script
    assert 'python -m garak --config "${GARAK_RUN_CFG}"' in script


def test_garak_config_rewrites_target_model_from_launch_input() -> None:
    script = Path("safety/run_safety.sh").read_text(encoding="utf-8")

    assert 'GATEWAY_MODEL="$MODEL" GARAK_REPORT_DIR="$GARAK_REPORT_DIR" python -' in script
    assert 'target_name: {json.dumps(model)}' in script
    assert 'report_dir: {report_dir}' in script


def test_garak_default_probe_spec_includes_extended_modules_and_cli_override() -> None:
    config = Path("safety/garak/garak_duke.yaml").read_text(encoding="utf-8")
    script = Path("safety/run_safety.sh").read_text(encoding="utf-8")

    assert "misleading,leakreplay,latentinjection,propile,divergence" in config
    assert 'GARAK_CMD+=(-p "$GARAK_PROBES")' in script

