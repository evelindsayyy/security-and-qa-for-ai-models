from pathlib import Path


def test_garak_run_uses_per_slug_xdg_dirs() -> None:
    script = Path("safety/run_safety.sh").read_text(encoding="utf-8")

    assert 'GARAK_XDG_BASE="${ROOT}/safety/garak/output/${SLUG}"' in script
    assert 'export XDG_DATA_HOME="${GARAK_XDG_BASE}/.garak-data"' in script
    assert 'mkdir -p "${HOME}" "${XDG_DATA_HOME}/garak"' in script
