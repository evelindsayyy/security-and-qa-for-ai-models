from pathlib import Path


def test_garak_run_uses_direct_python_command() -> None:
    script = Path("safety/run_safety.sh").read_text(encoding="utf-8")

    assert '"${GARAK_CMD[@]}"' in script
    assert "run_garak.py" in script
