"""Persisted gateway-model → scan-slug links for OSS catalog rollup."""

from __future__ import annotations

import json
from pathlib import Path

from frontend.model_identity import gateway_slug
from frontend.path_safety import is_safe_slug

_LINKS_PATH = Path(__file__).resolve().parent / ".scan-links.json"


def _load_raw() -> dict[str, str]:
    if not _LINKS_PATH.is_file():
        return {}
    try:
        data = json.loads(_LINKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if is_safe_slug(str(v))}


def get_links() -> dict[str, str]:
    """Return gateway slug → scan slug overrides."""
    return _load_raw()


def get_linked_scan(gateway_model_id: str) -> str | None:
    return get_links().get(gateway_slug(gateway_model_id))


def set_link(*, gateway_model_id: str, scan_slug: str) -> str | None:
    """Link a gateway model to an existing scan. Returns error message or None."""
    if not is_safe_slug(scan_slug):
        return f"invalid scan slug: {scan_slug!r}"

    from frontend.scan_data import get_scan_detail

    if get_scan_detail(scan_slug) is None:
        return f"no scan found for slug {scan_slug!r}"

    key = gateway_slug(gateway_model_id)
    links = _load_raw()
    links[key] = scan_slug
    _LINKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LINKS_PATH.write_text(json.dumps(links, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    from frontend import model_rollup

    model_rollup.clear_models_union_cache()
    return None


def remove_link(*, gateway_model_id: str) -> None:
    key = gateway_slug(gateway_model_id)
    links = _load_raw()
    if key not in links:
        return
    del links[key]
    if links:
        _LINKS_PATH.write_text(json.dumps(links, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif _LINKS_PATH.is_file():
        _LINKS_PATH.unlink(missing_ok=True)

    from frontend import model_rollup

    model_rollup.clear_models_union_cache()


def apply_scan_links(by_key: dict[str, dict]) -> None:
    """Attach linked scan summaries to gateway catalog rows."""
    from frontend import scan_data
    from frontend.model_rollup import _row

    scans_by_slug = {s["slug"]: s for s in scan_data.get_scans_data().get("scans", [])}
    for gw_slug, scan_slug in get_links().items():
        scan = scans_by_slug.get(scan_slug)
        if not scan:
            continue
        scan_summary = {
            "slug": scan["slug"],
            "tier": scan["severity_tier"],
            "overall_risk_score": scan["overall_risk_score"],
            "linked": True,
        }
        row = by_key.get(gw_slug)
        if row is None:
            row = _row(by_key, gw_slug, gw_slug.replace("-", " "))
        row["scan"] = scan_summary
