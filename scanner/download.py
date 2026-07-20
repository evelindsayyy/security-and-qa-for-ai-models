"""
Download a Hugging Face model repository into ``MODELS_ROOT``.

Used by the full scan pipeline when weights are not already on disk.
Does not run any security tools — see ``pipeline.scan_model`` for that.

Requires ``HF_TOKEN`` (or ``HUGGING_FACE_HUB_TOKEN``) in the environment for
gated repos; public repos download without a token but are rate-limited.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.utils import get_token

from scanner.paths import MODELS_ROOT, model_dir

# Marker written only after snapshot_download returns successfully. A bare
# directory (mkdir before download, or a killed mid-fetch) must not count as
# "already on disk" — that caused quiet re-scans of partial trees.
_COMPLETE_MARKER = ".download_complete"

# Refuse downloads larger than this unless SCAN_MAX_MODEL_GB overrides.
_DEFAULT_MAX_MODEL_GB = 80.0
# Require this much free space beyond the Hub payload (cache + headroom).
_DISK_MARGIN_GB = 5.0
_DISK_FACTOR = 1.15


class DownloadError(RuntimeError):
    """User-facing download failure (token, disk, size, Hub errors)."""


def _max_model_bytes() -> int:
    raw = os.environ.get("SCAN_MAX_MODEL_GB", "").strip()
    try:
        gb = float(raw) if raw else _DEFAULT_MAX_MODEL_GB
    except ValueError:
        gb = _DEFAULT_MAX_MODEL_GB
    return int(gb * 1e9)


def _hub_token() -> str | None:
    return get_token() or (os.environ.get("HF_TOKEN") or "").strip() or None


def model_download_complete(model_id: str) -> bool:
    """True when ``models/<slug>/`` has a successful download marker."""
    target = model_dir(model_id)
    return target.is_dir() and (target / _COMPLETE_MARKER).is_file()


def clear_incomplete_model(model_id: str) -> bool:
    """Remove a partial ``models/<slug>/`` tree so the next run re-downloads."""
    target = model_dir(model_id)
    if not target.is_dir():
        return False
    if (target / _COMPLETE_MARKER).is_file():
        return False
    shutil.rmtree(target, ignore_errors=True)
    return True


def _repo_download_bytes(model_id: str, *, token: str | None) -> tuple[int, int, bool | str]:
    """Return (total_bytes, file_count, gated) from Hub metadata."""
    api = HfApi(token=token)
    info = api.model_info(model_id, files_metadata=True)
    total = sum(int(s.size or 0) for s in (info.siblings or []))
    gated = info.gated if info.gated is not None else False
    return total, len(info.siblings or []), gated


def _preflight(model_id: str, *, token: str | None) -> int:
    """Validate Hub size vs free disk / policy. Returns expected byte size."""
    try:
        total, n_files, gated = _repo_download_bytes(model_id, token=token)
    except Exception as exc:
        raise DownloadError(
            f"cannot read Hub metadata for {model_id!r}: {exc}. "
            f"Check the repo id and HF_TOKEN (gated/private models require a token)."
        ) from exc

    if gated and not token:
        raise DownloadError(
            f"{model_id} is gated/private on Hugging Face but HF_TOKEN is unset. "
            f"Add a read token to the repo-root .env (HF_TOKEN=…) and restart the stack."
        )

    if total <= 0:
        print(
            f"WARNING: Hub reported 0 bytes for {model_id} ({n_files} files) — "
            f"continuing without a size check.",
            file=sys.stderr,
        )
        return 0

    max_bytes = _max_model_bytes()
    if total > max_bytes:
        raise DownloadError(
            f"{model_id} is ~{total / 1e9:.1f} GB on the Hub, above the scan limit "
            f"of {max_bytes / 1e9:.0f} GB (set SCAN_MAX_MODEL_GB to raise). "
            f"Use a smaller quantized mirror for artifact scanning."
        )

    MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(MODELS_ROOT).free
    need = int(total * _DISK_FACTOR) + int(_DISK_MARGIN_GB * 1e9)
    if free < need:
        raise DownloadError(
            f"not enough free disk for {model_id}: need ~{need / 1e9:.1f} GB "
            f"(model ~{total / 1e9:.1f} GB + margin), have {free / 1e9:.1f} GB free "
            f"under {MODELS_ROOT}. Free space or pick a smaller model."
        )

    if not token:
        print(
            "WARNING: HF_TOKEN is unset — downloading anonymously (lower rate limits). "
            "Set HF_TOKEN in .env for reliable multi-GB fetches.",
            file=sys.stderr,
        )

    print(
        f"download preflight: {model_id} ≈ {total / 1e9:.1f} GB "
        f"({n_files} files), free disk {free / 1e9:.1f} GB",
        flush=True,
    )
    return total


def download_model(model_id: str) -> Path:
    """
    Fetch all repo files for ``model_id`` into ``models/<slug>/``.

    Skips some alternate-framework blobs (msgpack, h5, flax, tf) to save space;
    Track A scanners target PyTorch/safetensors/onnx artifacts on typical HF repos.

    Returns the model directory path. Raises ``DownloadError`` on preflight or
    Hub failures (partial trees are removed).
    """
    if model_download_complete(model_id):
        return model_dir(model_id)

    clear_incomplete_model(model_id)

    token = _hub_token()
    _preflight(model_id, token=token)

    target = model_dir(model_id)
    target.mkdir(parents=True, exist_ok=True)

    # Prefer long timeouts for multi-GB shards (Hub default read timeout is 10s).
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")

    try:
        snapshot_download(
            repo_id=model_id,
            local_dir=str(target),
            token=token,
            ignore_patterns=["*.msgpack", "*.h5", "flax_*", "tf_*"],
        )
    except DownloadError:
        raise
    except Exception as exc:
        shutil.rmtree(target, ignore_errors=True)
        msg = str(exc).strip() or type(exc).__name__
        hint = ""
        low = msg.lower()
        if "401" in msg or "403" in msg or "gated" in low or "unauthorized" in low:
            hint = " Check HF_TOKEN in .env for gated/private access."
        elif "429" in msg or "rate" in low:
            hint = " Hub rate-limited anonymous downloads — set HF_TOKEN in .env."
        elif "no space" in low or "enospc" in low or "errno 28" in low:
            hint = " Free disk under scanner/models/ and retry."
        elif "timed out" in low or "timeout" in low:
            hint = (
                " Increase HF_HUB_DOWNLOAD_TIMEOUT (seconds) or set HF_TOKEN "
                "for faster authenticated downloads."
            )
        raise DownloadError(f"download failed for {model_id}: {msg}.{hint}") from exc

    (target / _COMPLETE_MARKER).write_text("ok\n", encoding="utf-8")
    print(f"download complete: {target}", flush=True)
    return target
