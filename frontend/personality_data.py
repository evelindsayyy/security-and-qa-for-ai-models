"""
Data source for /personality and /personality/<slug>.

Postgres when a DSN is reachable (personality_db_data); disk artifacts otherwise.
Not part of model rollup / aggregate score.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from frontend.path_safety import is_safe_slug, resolves_inside
from dbutils.run_paths import PRIVATE_SEGMENT
from personality.compass_scoring import AXIS_ORDER
from personality.test_catalog import TESTS

ROOT = Path(__file__).parent.parent
PRIMARY_DIR = ROOT / "personality" / "results"

TRAIT_LABELS = {
    "extraversion": "Extraversion",
    "agreeableness": "Agreeableness",
    "conscientiousness": "Conscientiousness",
    "neuroticism": "Neuroticism",
    "openness": "Openness",
}

TRAIT_ORDER = tuple(TRAIT_LABELS)

KNOWN_TESTS = frozenset(TESTS)


def _test_label(test_key: str) -> str:
    spec = TESTS.get(test_key) or {}
    return spec.get("label") or test_key.upper()


def _result_dirs(*, view_mode: str = "public", owner_user_id: str | None = None) -> list[Path]:
    """Flat JSON roots — public tree plus the signed-in user's private tree."""
    from dbutils import fs_safe

    dirs: list[Path] = []
    if fs_safe.is_dir(PRIMARY_DIR):
        dirs.append(PRIMARY_DIR)
    if view_mode == "private" and owner_user_id:
        private_root = PRIMARY_DIR / PRIVATE_SEGMENT / owner_user_id
        if fs_safe.is_dir(private_root):
            dirs.append(private_root)
    return dirs


def _format_ts(raw: str) -> str:
    if not raw:
        return "—"
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    except ValueError:
        return raw


def _iso_ts(raw: str) -> str:
    """Machine-readable UTC ISO for client-side local-time rendering."""
    if not raw:
        return ""
    txt = raw.strip()
    dt = None
    try:
        norm = txt[:-1] + "+00:00" if txt.endswith("Z") else txt
        dt = datetime.fromisoformat(norm)
    except ValueError:
        for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S"):
            try:
                dt = datetime.strptime(txt, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_model_name(raw: str) -> str:
    return (raw or "—").strip() or "—"


def _is_result_json(path: Path) -> bool:
    if path.suffix != ".json":
        return False
    stem = path.stem
    if stem.endswith(".progress"):
        return False
    return True


def _personality_visibility_meta(meta: dict | None, *, results_root: Path) -> dict:
    """Only runs under results/.private/<owner>/ are truly private on disk."""
    meta = dict(meta or {})
    try:
        rel = results_root.resolve().relative_to(PRIMARY_DIR.resolve())
        under_private = bool(rel.parts) and rel.parts[0] == PRIVATE_SEGMENT
    except ValueError:
        under_private = False
    if not under_private and meta.get("visibility") == "private":
        meta["visibility"] = "public"
    return meta


def _artifact_visible_for_personality(
    meta_dir: Path,
    *,
    view_mode: str,
    user_id: str | None,
) -> bool:
    from dbutils.run_meta import read_run_meta_for_pillar
    from dbutils.visibility import artifact_visible

    meta = read_run_meta_for_pillar(meta_dir, pillar="personality")
    meta = _personality_visibility_meta(meta, results_root=meta_dir.parent)
    return artifact_visible(meta, view_mode=view_mode, user_id=user_id)


def _canonical_slug(slug: str, test_key: str) -> bool:
    """Browser/UI stems look like 20260713T155439Z_bfi_Llama-3.3."""
    marker = f"_{test_key}_"
    return marker in slug and not slug.startswith(f"{test_key}_")


def _dedupe_twin_artifacts(rows: list[dict]) -> list[dict]:
    """Drop legacy <test>_<model>_<ts>.json twins of the same run artifact."""
    preferred: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        test_key = row.get("test") or ""
        key = (
            test_key,
            _normalize_model_name(row.get("model") or ""),
            row.get("timestamp_raw") or "",
        )
        slug = row.get("slug") or ""
        current = preferred.get(key)
        if current is None:
            preferred[key] = row
            continue
        current_slug = current.get("slug") or ""
        current_test = current.get("test") or test_key
        if current_slug.startswith(f"{current_test}_") and _canonical_slug(slug, test_key):
            preferred[key] = row
        elif slug.startswith(f"{test_key}_") and _canonical_slug(current_slug, current_test):
            continue
        elif _canonical_slug(slug, test_key) and not _canonical_slug(current_slug, current_test):
            preferred[key] = row
    return list(preferred.values())


def _legacy_mirror_paths(d: Path, slug: str) -> list[Path]:
    """Legacy runner filenames left beside a stem artifact."""
    path = d / f"{slug}.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    test_key = data.get("test")
    if test_key not in KNOWN_TESTS:
        return []
    spec = TESTS[test_key]
    ts = data.get("timestamp") or ""
    model = _normalize_model_name(data.get("model") or "")
    mirrors: list[Path] = []
    for candidate in d.glob(spec["legacy_glob"]):
        if candidate.stem == slug:
            continue
        try:
            other = json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if (
            other.get("test") == test_key
            and other.get("timestamp") == ts
            and _normalize_model_name(other.get("model") or "") == model
        ):
            mirrors.append(candidate)
    return mirrors


def _attach_test_fields(row: dict, *, test_key: str, summary: dict) -> dict:
    """Add BFI / compass fields expected by list + detail templates."""
    if test_key == "bfi":
        traits = summary.get("traits") or {}
        row["traits"] = traits
        row["trait_rows"] = [
            {
                "key": key,
                "label": TRAIT_LABELS.get(key, key.title()),
                "score": traits.get(key),
            }
            for key in TRAIT_ORDER
        ]
    elif test_key == "compass":
        axes = summary.get("axes") or {}
        axis_labels = summary.get("axis_labels") or {}
        row["axes"] = axes
        row["quadrant"] = summary.get("quadrant") or "—"
        row["economic_score"] = (axes.get("economic") or {}).get("score")
        row["social_score"] = (axes.get("social") or {}).get("score")
        row["weak_reading"] = bool(summary.get("weak_reading"))
        row["near_even_count"] = int(summary.get("near_even_count") or 0)
        row["axis_rows"] = []
        for key in AXIS_ORDER:
            meta = axes.get(key) or {}
            if key == "economic":
                neg_label, pos_label = "Left", "Right"
            else:
                neg_label, pos_label = "Libertarian", "Authoritarian"
            row["axis_rows"].append(
                {
                    "key": key,
                    "label": axis_labels.get(key) or key.title(),
                    "score": meta.get("score"),
                    "neg_label": neg_label,
                    "pos_label": pos_label,
                    "neg_pct": meta.get("neg_pct"),
                    "pos_pct": meta.get("pos_pct"),
                    "lean": meta.get("lean"),
                    "clarity": meta.get("clarity"),
                    "clarity_label": {
                        "near_even": "Near even",
                        "lean": "Slight lean",
                        "clear": "Clear",
                    }.get(meta.get("clarity") or "", meta.get("clarity") or "—"),
                }
            )
        econ = (axes.get("economic") or {}).get("score")
        social = (axes.get("social") or {}).get("score")
        row["plot_x"] = round((float(econ) + 100) / 2, 1) if econ is not None else 50.0
        row["plot_y"] = round((100.0 - float(social)) / 2, 1) if social is not None else 50.0
    return row


def _summarize_file(path: Path, *, slug: str) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    test_key = data.get("test")
    if test_key not in KNOWN_TESTS:
        return None
    summary = data.get("summary") or {}
    row = {
        "slug": slug,
        "test": test_key,
        "test_label": _test_label(test_key),
        "model": _normalize_model_name(data.get("model") or "—"),
        "timestamp_raw": data.get("timestamp") or "",
        "timestamp": _format_ts(data.get("timestamp") or ""),
        "timestamp_iso": _iso_ts(data.get("timestamp") or ""),
        "filename": path.name,
        "coverage": summary.get("coverage"),
        "attempted": summary.get("attempted"),
        "scored": summary.get("scored"),
    }
    return _attach_test_fields(row, test_key=test_key, summary=summary)


def build_detail_payload(
    *,
    slug: str,
    test_key: str,
    model: str,
    timestamp_raw: str,
    filename: str,
    items: list,
    summary: dict,
    visibility: str = "public",
) -> dict | None:
    """Shared detail dict for disk and Postgres readers."""
    if test_key not in KNOWN_TESTS:
        return None
    summary = summary or {}
    detail = {
        "slug": slug,
        "test": test_key,
        "test_label": _test_label(test_key),
        "model": _normalize_model_name(model or "—"),
        "timestamp_raw": timestamp_raw or "",
        "timestamp": _format_ts(timestamp_raw or ""),
        "timestamp_iso": _iso_ts(timestamp_raw or ""),
        "filename": filename,
        "items": items or [],
        "summary": summary,
        "coverage": summary.get("coverage"),
        "attempted": summary.get("attempted"),
        "scored": summary.get("scored"),
        "is_private": visibility == "private",
    }
    return _attach_test_fields(detail, test_key=test_key, summary=summary)


def _postprocess_runs(rows: list[dict]) -> dict:
    deduped: list[dict] = []
    seen_latest: set[tuple[str, str]] = set()
    for row in sorted(rows, key=lambda r: r.get("timestamp_raw") or "", reverse=True):
        key = (row.get("test") or "", row.get("model") or "")
        if key in seen_latest:
            row = {**row, "superseded": True}
        else:
            seen_latest.add(key)
            row = {**row, "superseded": False}
        deduped.append(row)
    models = sorted({r["model"] for r in deduped if r.get("model")})
    return {
        "has_runs": bool(deduped),
        "runs": deduped,
        "run_count": len(deduped),
        "all_run_count": len(deduped),
        "models": models,
    }


def _get_personality_data_files(
    *, visibility: str = "public", owner_user_id: str | None = None
) -> dict:
    from dbutils import fs_safe

    dirs = _result_dirs(view_mode=visibility, owner_user_id=owner_user_id)
    rows: list[dict] = []
    seen: set[str] = set()
    for d in dirs:
        for path in sorted(fs_safe.glob(d, "*.json")):
            if not _is_result_json(path):
                continue
            slug = path.stem
            if slug in seen:
                continue
            if not _artifact_visible_for_personality(
                d / slug, view_mode=visibility, user_id=owner_user_id
            ):
                continue
            row = _summarize_file(path, slug=slug)
            if row:
                seen.add(slug)
                rows.append(row)
    out = _postprocess_runs(_dedupe_twin_artifacts(rows))
    out["search_paths"] = [str(PRIMARY_DIR)]
    out["trait_order"] = list(TRAIT_ORDER)
    return out


def _get_personality_detail_files(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> dict | None:
    if not is_safe_slug(slug):
        return None
    for d in _result_dirs(view_mode=visibility, owner_user_id=owner_user_id):
        if not _artifact_visible_for_personality(
            d / slug, view_mode=visibility, user_id=owner_user_id
        ):
            continue
        path = d / f"{slug}.json"
        if not path.is_file() or not resolves_inside(d, path):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return build_detail_payload(
            slug=slug,
            test_key=data.get("test") or "",
            model=data.get("model") or "—",
            timestamp_raw=data.get("timestamp") or "",
            filename=path.name,
            items=data.get("items") or [],
            summary=data.get("summary") or {},
            visibility=visibility,
        )
    return None


def get_personality_data(*, visibility: str = "public", owner_user_id: str | None = None) -> dict:
    from frontend import personality_db_data
    from frontend.db_fallback import get_data_with_db_fallback

    return get_data_with_db_fallback(
        personality_db_data.available,
        lambda: personality_db_data.get_personality_data_db(
            visibility=visibility, owner_user_id=owner_user_id
        ),
        lambda: _get_personality_data_files(
            visibility=visibility, owner_user_id=owner_user_id
        ),
        pillar="personality",
    )


def get_personality_detail(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> dict | None:
    """Detail payload for one personality run. Postgres first when DSN reachable."""
    if not is_safe_slug(slug):
        return None
    try:
        from frontend import personality_db_data

        if personality_db_data.available():
            detail = personality_db_data.get_personality_detail_db(
                slug, visibility=visibility, owner_user_id=owner_user_id
            )
            if detail is not None:
                return detail
            return _get_personality_detail_files(
                slug, visibility=visibility, owner_user_id=owner_user_id
            )
    except Exception:
        pass
    return _get_personality_detail_files(
        slug, visibility=visibility, owner_user_id=owner_user_id
    )

def get_latest_for_model(
    model_name: str,
    *,
    test_key: str | None = None,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> dict | None:
    target = _normalize_model_name(model_name).lower()
    data = get_personality_data(visibility=visibility, owner_user_id=owner_user_id)
    for row in data.get("runs") or []:
        if row.get("superseded"):
            continue
        if test_key and row.get("test") != test_key:
            continue
        if (row.get("model") or "").lower() == target:
            return row
    slug_target = re.sub(r"[^a-z0-9]+", "", target)
    for row in data.get("runs") or []:
        if row.get("superseded"):
            continue
        if test_key and row.get("test") != test_key:
            continue
        model_slug = re.sub(r"[^a-z0-9]+", "", (row.get("model") or "").lower())
        if model_slug == slug_target:
            return row
    return None


def delete_personality_run(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> str | None:
    """Remove personality artifacts (and DB row when configured)."""
    from frontend.delete_db import db_delete_error

    if not is_safe_slug(slug):
        return f"invalid slug: {slug!r}"

    exists = False
    try:
        from frontend import personality_db_data

        if personality_db_data.available():
            exists = (
                personality_db_data.get_personality_detail_db(
                    slug, visibility=visibility, owner_user_id=owner_user_id
                )
                is not None
            )
    except Exception:
        pass
    if not exists:
        detail = _get_personality_detail_files(
            slug, visibility=visibility, owner_user_id=owner_user_id
        )
        if detail is None:
            return f"no personality result found for slug {slug!r}"

    removed_files = 0
    for d in _result_dirs(view_mode=visibility, owner_user_id=owner_user_id):
        if not _artifact_visible_for_personality(
            d / slug, view_mode=visibility, user_id=owner_user_id
        ):
            continue
        for suffix in (".json", ".log", ".progress.json"):
            path = d / f"{slug}{suffix}"
            if path.is_file() and resolves_inside(d, path):
                path.unlink(missing_ok=True)
                removed_files += 1
        for mirror in _legacy_mirror_paths(d, slug):
            if mirror.is_file() and resolves_inside(d, mirror):
                mirror.unlink(missing_ok=True)
                removed_files += 1
        meta_path = d / slug / "run_meta.json"
        if meta_path.is_file():
            meta_path.unlink(missing_ok=True)
            removed_files += 1
        meta_dir = d / slug
        if meta_dir.is_dir():
            try:
                meta_dir.rmdir()
            except OSError:
                pass

    removed_db = False
    db_available = False
    db_row_existed = False
    db_exc: BaseException | None = None
    try:
        from frontend import personality_db_data

        db_available = personality_db_data.available()
        if db_available:
            try:
                db_row_existed = (
                    personality_db_data.get_personality_detail_db(
                        slug, visibility=visibility, owner_user_id=owner_user_id
                    )
                    is not None
                )
            except Exception:
                pass
            try:
                removed_db = personality_db_data.delete_run(
                    slug, visibility=visibility, owner_user_id=owner_user_id
                )
            except Exception as exc:
                db_exc = exc
    except Exception as exc:
        db_exc = exc

    err = db_delete_error(
        db_available=db_available,
        db_row_existed=db_row_existed,
        removed_db=removed_db,
        db_exc=db_exc,
    )
    if err:
        return err

    if removed_files == 0 and not removed_db:
        return f"no personality result found for slug {slug!r}"
    return None
