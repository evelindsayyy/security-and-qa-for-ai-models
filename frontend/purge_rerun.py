"""Purge prior pillar results (disk + Postgres) before a browser relaunch."""

from __future__ import annotations

import uuid
from pathlib import Path


def _ignore_not_found(err: str | None, *, phrases: tuple[str, ...]) -> str | None:
    if not err:
        return None
    if any(p in err for p in phrases):
        return None
    return err


def _db_scope_safe(visibility: str, owner_user_id: str | None) -> bool:
    if visibility != "private":
        return True
    if not owner_user_id:
        return False
    try:
        uuid.UUID(str(owner_user_id))
    except ValueError:
        return False
    return True


def _has_prior_scan(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> bool:
    from frontend.scan_launch import _existing_scan_slugs

    if slug in _existing_scan_slugs(visibility=visibility, owner_user_id=owner_user_id):
        return True
    if not _db_scope_safe(visibility, owner_user_id):
        return False
    try:
        from frontend import scan_db_data

        if scan_db_data.available():
            return (
                scan_db_data.resolve_delete_run_id(
                    slug, visibility=visibility, owner_user_id=owner_user_id
                )
                is not None
            )
    except Exception:
        pass
    return False


def purge_scan_for_launch(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> str | None:
    if not _has_prior_scan(slug, visibility=visibility, owner_user_id=owner_user_id):
        return None
    from frontend.scan_data import delete_scan

    return _ignore_not_found(
        delete_scan(slug, visibility=visibility, owner_user_id=owner_user_id),
        phrases=("no scan result found",),
    )


def _has_prior_safety(
    slug: str,
    profile: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> bool:
    from safety.merged_paths import merged_result_path

    from frontend.safety_launch import ROOT

    owner = owner_user_id if visibility == "private" else None
    if merged_result_path(
        ROOT / "safety" / "output", slug, profile, owner_user_id=owner
    ).is_file():
        return True
    if not _db_scope_safe(visibility, owner_user_id):
        return False
    try:
        from frontend import safety_db_data

        if safety_db_data.available():
            return (
                safety_db_data.resolve_delete_run_id(
                    slug, profile, visibility=visibility, owner_user_id=owner_user_id
                )
                is not None
            )
    except Exception:
        pass
    return False


def purge_safety_for_launch(
    slug: str,
    profile: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> str | None:
    if not _has_prior_safety(
        slug, profile, visibility=visibility, owner_user_id=owner_user_id
    ):
        return None
    from frontend.safety_data import delete_safety

    return _ignore_not_found(
        delete_safety(
            slug, profile, visibility=visibility, owner_user_id=owner_user_id
        ),
        phrases=("no safety result found",),
    )


def _scoped_meta_matches(
    meta: dict,
    *,
    visibility: str,
    owner_user_id: str | None,
) -> bool:
    if (meta.get("visibility") or "public") != visibility:
        return False
    if visibility == "private" and meta.get("owner_user_id") != owner_user_id:
        return False
    return True


def _purge_timestamped_stems(
    results_dir: Path,
    suffix: str,
    *,
    pillar: str,
    visibility: str,
    owner_user_id: str | None,
    delete_fn,
    not_found_phrase: str,
) -> str | set[str]:
    from dbutils import fs_safe
    from dbutils.run_meta import read_run_meta_for_pillar

    stems: set[str] = set()
    for path in fs_safe.glob(results_dir, f"*{suffix}*"):
        if path.suffix not in (".jsonl", ".log", ".json"):
            continue
        stem = _stem_from_artifact_path(path)
        if stem in stems:
            continue
        meta = read_run_meta_for_pillar(results_dir / stem, pillar=pillar)
        if not _scoped_meta_matches(
            meta, visibility=visibility, owner_user_id=owner_user_id
        ):
            continue
        stems.add(stem)
        err = delete_fn(stem, visibility=visibility, owner_user_id=owner_user_id)
        if err and not_found_phrase not in err:
            return err
    return stems


def _stem_from_artifact_path(path: Path) -> str:
    name = path.name
    for artifact_suffix in ("_trace.jsonl", ".jsonl", ".log", ".json"):
        if name.endswith(artifact_suffix):
            return name[: -len(artifact_suffix)]
    return path.stem


def purge_eval_for_launch(
    suite_key: str,
    candidate: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> str | None:
    from frontend.eval_launch import RESULTS_DIR, _safe_slug
    from frontend.eval_run_data import delete_eval_run

    suffix = f"_{suite_key}_{_safe_slug(candidate)}"
    stems = _purge_timestamped_stems(
        RESULTS_DIR,
        suffix,
        pillar="eval",
        visibility=visibility,
        owner_user_id=owner_user_id,
        delete_fn=delete_eval_run,
        not_found_phrase="no eval run found",
    )
    if isinstance(stems, str):
        return stems

    if _db_scope_safe(visibility, owner_user_id):
        try:
            from frontend import eval_db_data

            if eval_db_data.available():
                eval_db_data.delete_runs_for_combo(
                    suite_key,
                    candidate,
                    visibility=visibility,
                    owner_user_id=owner_user_id,
                )
        except Exception:
            pass
    return None


def purge_benchmark_for_launch(
    benchmark_key: str,
    model: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> str | None:
    from benchmarks.run_benchmark import _safe_slug
    from frontend.benchmark_data import delete_benchmark
    from frontend.benchmark_launch import RESULTS_DIR

    suffix = f"_{benchmark_key}_{_safe_slug(model)}"
    stems = _purge_timestamped_stems(
        RESULTS_DIR,
        suffix,
        pillar="benchmark",
        visibility=visibility,
        owner_user_id=owner_user_id,
        delete_fn=delete_benchmark,
        not_found_phrase="no benchmark result found",
    )
    if isinstance(stems, str):
        return stems

    if _db_scope_safe(visibility, owner_user_id):
        try:
            from frontend import benchmark_db_data

            if benchmark_db_data.available():
                benchmark_db_data.delete_runs_for_combo(
                    benchmark_key,
                    model,
                    visibility=visibility,
                    owner_user_id=owner_user_id,
                )
        except Exception:
            pass
    return None
