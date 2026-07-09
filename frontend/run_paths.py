"""Re-exports ``dbutils.run_paths`` for the frontend app's call sites.

The real module lives in ``dbutils/`` so pillar loaders running inside their
own containers (``scanner/db/``, ``safety/db/`` — images that never ``COPY
frontend/``) can import it too. Import ``frontend.run_paths`` here for the
app; import ``dbutils.run_paths`` directly from anything that runs inside a
pillar container.
"""

from __future__ import annotations

from dbutils.run_paths import (
    PRIVATE_SEGMENT,
    inflight_scope_key,
    iter_visible_slug_dirs,
    scoped_dir,
)

__all__ = [
    "PRIVATE_SEGMENT",
    "inflight_scope_key",
    "iter_visible_slug_dirs",
    "scoped_dir",
]
