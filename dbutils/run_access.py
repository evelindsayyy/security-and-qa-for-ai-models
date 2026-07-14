"""Postgres lookup for reusable runs and user_run_links."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from dbutils.run_fingerprint import Pillar


@dataclass(frozen=True)
class ReusableRun:
    run_id: str
    pillar: Pillar
    visibility: str
    slug: str
    profile: str | None = None  # safety only


_LOOKUP_SQL: dict[Pillar, str] = {
    "scan": """
        SELECT id, visibility, scan_metadata, hf_repo
        FROM public.scans
        WHERE config_fingerprint = %(fp)s
          AND visibility = %(vis)s
          AND status = 'complete'
          {owner_clause}
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
    """,
    "safety": """
        SELECT id, visibility, gateway_model_id, config_json
        FROM public.safety_runs
        WHERE config_fingerprint = %(fp)s
          AND visibility = %(vis)s
          AND status = 'complete'
          {owner_clause}
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
    """,
    "eval": """
        SELECT id, visibility, adaptation
        FROM public.eval_runs
        WHERE config_fingerprint = %(fp)s
          AND visibility = %(vis)s
          AND status = 'complete'
          {owner_clause}
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
    """,
    "benchmark": """
        SELECT id, visibility, output_slug
        FROM public.benchmark_runs
        WHERE config_fingerprint = %(fp)s
          AND visibility = %(vis)s
          AND status = 'complete'
          {owner_clause}
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
    """,
    "personality": """
        SELECT id, visibility, output_slug
        FROM public.personality_runs
        WHERE config_fingerprint = %(fp)s
          AND visibility = %(vis)s
          AND status = 'complete'
          {owner_clause}
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
    """,
}


def _row_to_reusable(pillar: Pillar, row: tuple, cols: list[str]) -> ReusableRun:
    data = dict(zip(cols, row, strict=False))
    run_id = str(data["id"])
    visibility = str(data["visibility"])

    if pillar == "scan":
        meta = data.get("scan_metadata") or {}
        slug = meta.get("output_slug") if isinstance(meta, dict) else None
        if not slug:
            hf_repo = data.get("hf_repo") or ""
            slug = hf_repo.replace("/", "--")
        return ReusableRun(run_id=run_id, pillar=pillar, visibility=visibility, slug=str(slug))

    if pillar == "safety":
        from safety.gateway_ids import normalize_gateway_model_id

        cfg = data.get("config_json") or {}
        profile = cfg.get("redteam_profile", "base") if isinstance(cfg, dict) else "base"
        slug = normalize_gateway_model_id(data.get("gateway_model_id") or "")
        return ReusableRun(
            run_id=run_id,
            pillar=pillar,
            visibility=visibility,
            slug=slug,
            profile=str(profile),
        )

    if pillar == "eval":
        adaptation = data.get("adaptation") or {}
        slug = ""
        if isinstance(adaptation, dict):
            slug = adaptation.get("output_slug") or adaptation.get("output_name") or ""
        if not slug:
            slug = run_id
        return ReusableRun(run_id=run_id, pillar=pillar, visibility=visibility, slug=str(slug))

    slug = str(data.get("output_slug") or run_id)
    return ReusableRun(run_id=run_id, pillar=pillar, visibility=visibility, slug=slug)


def lookup_reusable_run(
    conn,
    pillar: Pillar,
    config_fingerprint: str,
    *,
    user_id: str | None,
    visibility: str,
) -> ReusableRun | None:
    owner_clause = "AND owner_user_id IS NULL"
    params: dict[str, Any] = {"fp": config_fingerprint, "vis": visibility}
    if visibility == "private":
        if not user_id:
            return None
        owner_clause = "AND owner_user_id = %(uid)s"
        params["uid"] = user_id

    sql = _LOOKUP_SQL[pillar].format(owner_clause=owner_clause)
    with conn.cursor() as cur:
        try:
            cur.execute(sql, params)
        except Exception:
            return None
        row = cur.fetchone()
        if not row:
            return None
        cols = [d.name if hasattr(d, "name") else d[0] for d in cur.description]
    return _row_to_reusable(pillar, row, cols)


def ensure_user_link(
    conn,
    *,
    user_id: str,
    pillar: Pillar,
    run_id: str,
    link_type: Literal["owner", "reused"] = "reused",
) -> None:
    sql = """
        INSERT INTO public.user_run_links (user_id, pillar, run_id, link_type)
        VALUES (%(user_id)s, %(pillar)s, %(run_id)s, %(link_type)s)
        ON CONFLICT (user_id, pillar, run_id) DO NOTHING
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "user_id": user_id,
                "pillar": pillar,
                "run_id": run_id,
                "link_type": link_type,
            },
        )
    conn.commit()


def upsert_user(conn, *, netid: str, email: str | None, display_name: str | None) -> str:
    sql = """
        INSERT INTO public.users (netid, email, display_name)
        VALUES (%(netid)s, %(email)s, %(display_name)s)
        ON CONFLICT (netid) DO UPDATE SET
            email = COALESCE(EXCLUDED.email, public.users.email),
            display_name = COALESCE(EXCLUDED.display_name, public.users.display_name)
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {"netid": netid.lower(), "email": email, "display_name": display_name},
        )
        row = cur.fetchone()
    conn.commit()
    return str(row[0])


def get_user_by_netid(conn, netid: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, netid, email, display_name FROM public.users WHERE netid = %(n)s",
            {"n": netid.lower()},
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"id": str(row[0]), "netid": row[1], "email": row[2], "display_name": row[3]}


def try_lookup_reusable(
    pillar: Pillar,
    config_fingerprint: str,
    *,
    user_id: str | None,
    visibility: str,
) -> ReusableRun | None:
    from dbutils.connection import psycopg_available
    from dbutils.env import load_repo_env, resolve_dsn

    load_repo_env()
    dsn = resolve_dsn("POSTGRES_DSN", "DATABASE_URL", "EFFICACY_DB_DSN")
    if not dsn or not psycopg_available():
        return None
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=2) as conn:
            return lookup_reusable_run(
                conn,
                pillar,
                config_fingerprint,
                user_id=user_id,
                visibility=visibility,
            )
    except Exception:
        return None
