"""
HF artifact scan catalog for the draft frontend.

Built from scan_result.json files under scanner/output/ (same source as /scans).
Optional team notes are keyed by HF repo id; scan rows add live tier/score metadata.

Week 5+: replace with GET /api/scans inventory from Postgres.
"""

from __future__ import annotations

from typing import Any

from frontend.scan_data import OUTPUT_DIR, get_scans_data

# Optional notes for known regression / calibration models (keyed by HF repo id).
HF_ANNOTATIONS: dict[str, str] = {
    "gpt2": "calibration baseline — low/18 with benign fickling",
    "distilbert-base-uncased": "default scanner regression",
    "BAAI/bge-small-en-v1.5": "safetensors + pickle paths",
    "google/flan-t5-small": "org/model path layout",
    "neimasilk/modelscan-extension-mismatch-poc": (
        "malicious poc — critical/95; modelaudit catches extensionless payload"
    ),
}


def get_hf_scan_catalog() -> dict[str, Any]:
    """
    Catalog rows for /models — one row per completed scan.

    Sorted highest risk first (same order as /scans). Never raises.
    """
    try:
        data = get_scans_data()
    except Exception as exc:  # noqa: BLE001
        return {
            "has_models": False,
            "models": [],
            "count": 0,
            "source": "scanner/output/*/scan_result.json",
            "output_dir": str(OUTPUT_DIR),
            "error": f"Failed to read scan output: {type(exc).__name__}: {exc}",
        }

    models: list[dict[str, Any]] = []
    for row in data["scans"]:
        model_id = row["model_id"]
        annotation = HF_ANNOTATIONS.get(model_id, "")
        live_bits = (
            f"tier {row['severity_tier']} · score {row['overall_risk_score']} · "
            f"{row['n_findings']} finding(s)"
        )
        notes = f"{annotation} · {live_bits}" if annotation else live_bits

        models.append(
            {
                "id": model_id,
                "slug": row["slug"],
                "notes": notes,
                "severity_tier": row["severity_tier"],
                "overall_risk_score": row["overall_risk_score"],
                "n_findings": row["n_findings"],
                "scanned_at": row["scanned_at"],
                "tool_snippet": row.get("tool_snippet", ""),
                "is_warn": (
                    "poc" in model_id.lower()
                    or "malicious" in annotation.lower()
                    or row["severity_tier"] in ("high", "critical")
                ),
            }
        )

    return {
        "has_models": bool(models),
        "models": models,
        "count": len(models),
        "source": "scanner/output/*/scan_result.json",
        "output_dir": data.get("output_dir", str(OUTPUT_DIR)),
        "error": None if models or OUTPUT_DIR.exists() else (
            "No scan results yet — use Start scan in the UI or from repo root: "
            "docker compose --env-file .env -f scanner/docker/compose.yml run --rm scanner "
            f"python -m scanner scan <hf_repo> (outputs under {OUTPUT_DIR})"
        ),
    }
