"""Fake garak package for unit tests (CI uses dev deps only, not safety/garak)."""

from __future__ import annotations

import sys
import types
from unittest import mock


def install_fake_garak(
    *,
    rejected: list[str] | None = None,
    names: list[str] | None = None,
    toxic_side_effect: BaseException | None = None,
) -> dict[str, types.ModuleType]:
    """Register minimal garak modules in sys.modules for lazy imports in run_garak."""
    config = types.ModuleType("garak._config")
    config.parse_plugin_spec = mock.Mock(
        return_value=(names if names is not None else ["encoding.InjectHex"], rejected or [])
    )

    toxic_cls = mock.Mock()
    if toxic_side_effect is not None:
        toxic_cls.side_effect = toxic_side_effect

    unsafe = types.ModuleType("garak.detectors.unsafe_content")
    unsafe.ToxicCommentModel = toxic_cls

    detectors = types.ModuleType("garak.detectors")
    detectors.unsafe_content = unsafe

    garak = types.ModuleType("garak")
    garak._config = config
    garak.detectors = detectors

    modules = {
        "garak": garak,
        "garak._config": config,
        "garak.detectors": detectors,
        "garak.detectors.unsafe_content": unsafe,
    }
    sys.modules.update(modules)
    return modules


def remove_fake_garak(modules: dict[str, types.ModuleType]) -> None:
    for name in modules:
        sys.modules.pop(name, None)
