"""
eval_intake.py — frontend wrapper for the self-serve "add a model" page.

Validates a user-submitted Hugging Face model (by LINK / repo id for now; file
upload of weights is a later, heavier piece) and shapes the result for the
template. Thin on purpose: the validation rules live in evaluator/hf_intake.py
so they stay reusable + unit-tested; this module only adapts them to the view.
"""

from __future__ import annotations

import sys
from pathlib import Path

# evaluator/ is a sibling namespace package; ensure the repo root is importable
# (mirrors how the other frontend data modules reach evaluator/).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evaluator import hf_intake  # noqa: E402


def validate_model(repo_id: str) -> dict:
    """Validate an HF repo id and shape the verdict for ``eval_add_model.html``."""
    res = hf_intake.validate(repo_id)
    info = res.info
    return {
        "ok": res.ok,
        "error": res.error,
        "repo_id": repo_id,
        "architectures": info.architectures if info else None,
        "num_params": info.num_params if info else None,
        "gated": info.gated if info else None,
    }
