"""Garak XDG env is set per slug in safety.run."""

from safety.run import garak_xdg_env


def test_garak_xdg_env_sets_home_and_cache() -> None:
    env = garak_xdg_env("unit-test-slug")
    assert "HOME" in env
    assert "XDG_CACHE_HOME" in env
    assert "unit-test-slug" in env["HOME"]
