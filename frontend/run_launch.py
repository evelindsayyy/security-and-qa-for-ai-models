"""Shared launch helpers — fingerprint, reuse lookup, run metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from auth.session import effective_user, get_view_mode
from dbutils.run_access import ReusableRun, ensure_user_link, try_lookup_reusable
from dbutils.run_fingerprint import Pillar, fingerprint, is_public_default, resolve_visibility
from dbutils.run_meta import merge_into_scan_meta, write_run_meta


@dataclass(frozen=True)
class LaunchPlan:
    config: dict[str, Any]
    config_fingerprint: str
    visibility: str
    owner_user_id: str | None
    owner_netid: str | None
    reused: ReusableRun | None


def _enrich_launch_config(pillar: Pillar, config: dict[str, Any]) -> dict[str, Any]:
    """Persist run-time spec digests in sidecar config_json for staleness checks."""
    enriched = dict(config)
    if pillar == "safety" and not enriched.get("skip_garak"):
        from dbutils.staleness_spec import (
            current_safety_garak_probe_spec,
            garak_probe_spec_digest,
        )

        probes = (enriched.get("garak_probes") or "").strip()
        spec = probes or current_safety_garak_probe_spec()
        enriched["garak_probe_spec_digest"] = garak_probe_spec_digest(spec)
    if pillar == "eval":
        suite_key = (enriched.get("suite_key") or "").strip()
        if suite_key and not suite_key.startswith("custom_"):
            from dbutils.staleness_spec import current_eval_suite_file_digests

            digests = current_eval_suite_file_digests(suite_key)
            if digests:
                enriched["eval_suite_file_digests"] = digests
    if pillar == "benchmark":
        benchmark_key = (enriched.get("benchmark_key") or "").strip()
        if benchmark_key:
            from dbutils.staleness_spec import current_benchmark_spec_digest

            digest = current_benchmark_spec_digest(benchmark_key)
            if digest:
                enriched["benchmark_spec_digest"] = digest
    return enriched


def build_launch_plan(
    pillar: Pillar,
    *,
    force_private: bool = False,
    **config_kwargs: Any,
) -> LaunchPlan:
    from dbutils.run_fingerprint import normalize_config

    config = _enrich_launch_config(pillar, normalize_config(pillar, **config_kwargs))
    fp = fingerprint(pillar, config)
    private_mode = get_view_mode() == "private"
    visibility = resolve_visibility(
        pillar,
        config,
        private_mode=private_mode,
        force_private=force_private,
    )
    # A non-default config can never land in the shared public catalog, even
    # in public view mode — this is the only thing that can downgrade an
    # already-"public" result; it never overrides an explicit private choice.
    if visibility == "public" and not is_public_default(pillar, config):
        visibility = "private"

    user = effective_user()
    user_id = user.get("id") if user else None
    netid = user.get("netid") if user else None

    if visibility == "private" and not user_id:
        # No one to own a private artifact — an ownerless private row is
        # permanently invisible to everyone, including whoever launched it
        # (artifact_visible() requires an owner match). Fall back to public.
        visibility = "public"

    reused = try_lookup_reusable(
        pillar,
        fp,
        user_id=user_id if visibility == "private" else None,
        visibility=visibility,
    )

    if reused and user_id:
        _link_reuse(user_id, reused)

    return LaunchPlan(
        config=config,
        config_fingerprint=fp,
        visibility=visibility,
        owner_user_id=user_id if visibility == "private" else None,
        owner_netid=netid if visibility == "private" else None,
        reused=reused,
    )


def _link_reuse(user_id: str, reused: ReusableRun) -> None:
    from dbutils.connection import psycopg_available
    from dbutils.env import load_repo_env, resolve_dsn

    load_repo_env()
    dsn = resolve_dsn("POSTGRES_DSN", "DATABASE_URL", "EFFICACY_DB_DSN")
    if not dsn or not psycopg_available():
        return
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=2) as conn:
            ensure_user_link(
                conn,
                user_id=user_id,
                pillar=reused.pillar,
                run_id=reused.run_id,
                link_type="reused",
            )
    except Exception:
        pass


def persist_run_meta_scan(scan_dir: Path, plan: LaunchPlan) -> None:
    meta = {
        "visibility": plan.visibility,
        "config_fingerprint": plan.config_fingerprint,
        "config_json": plan.config,
        "owner_user_id": plan.owner_user_id,
        "owner_netid": plan.owner_netid,
    }
    merge_into_scan_meta(scan_dir, meta)


def persist_run_meta_dir(directory: Path, plan: LaunchPlan) -> None:
    write_run_meta(
        directory,
        visibility=plan.visibility,
        config_fingerprint=plan.config_fingerprint,
        config_json=plan.config,
        owner_user_id=plan.owner_user_id,
        owner_netid=plan.owner_netid,
    )


def reused_slug(plan: LaunchPlan) -> str | None:
    if not plan.reused:
        return None
    return plan.reused.slug


def reused_run_key(plan: LaunchPlan) -> str | None:
    """Safety returns slug/profile; others return slug."""
    if not plan.reused:
        return None
    if plan.reused.profile:
        return f"{plan.reused.slug}/{plan.reused.profile}"
    return plan.reused.slug
