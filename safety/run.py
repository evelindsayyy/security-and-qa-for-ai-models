"""
End-to-end safety pipeline: Promptfoo policy + red-team + Garak + merge.

Usage (from repo root):
    uv run python -m safety.run
    uv run python -m safety.run "gpt-5-chat"
    uv run python -m safety.run --skip-redteam --skip-garak
    uv run python -m safety.run --all-models
    uv run python -m safety.run garak-setup
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dbutils.compose import compose_build, compose_run
from dbutils.env import REPO_ROOT
from safety.garak.report_validation import DEFAULT_PROBE_SPEC, validate_report
from dbutils import run_lock
from safety.gateway_ids import normalize_gateway_model_id

VALID_PROFILES = frozenset({"base", "education", "healthcare", "finance", "rag", "agentic"})

ALL_MODELS = (
    "GPT 4.1 Mini",
    "gpt-5-chat",
    "gpt-5.5",
    "gpt-5-mini",
    "Llama 4 Maverick",
)

PROMPTFOO_COMPOSE = REPO_ROOT / "safety" / "promptfoo" / "docker" / "compose.yml"
GARAK_COMPOSE = REPO_ROOT / "safety" / "garak" / "docker" / "compose.yml"

# Remote-plugin coverage that can't run inside the promptfoo redteam job (needs a
# local LLM grader); run separately against static manual/*.yaml configs.
MANUAL_EVALS = (
    ("harmful", "manual/harmful_content.yaml"),
    ("bias", "manual/bias.yaml"),
    ("remote_policy", "manual/remote_policy.yaml"),
)


@dataclass
class RunConfig:
    model: str
    redteam_profile: str = "base"
    skip_policy: bool = False
    redteam: bool = True
    skip_promptfoo: bool = False
    skip_garak: bool = False
    garak_probes: str = ""


def garak_xdg_env(slug: str) -> dict[str, str]:
    """Per-slug XDG dirs so Garak writes as the container user."""
    base = REPO_ROOT / "safety" / "garak" / "output" / slug
    home = base / ".garak-home"
    data = base / ".garak-data"
    cache = base / ".garak-cache"
    config = base / ".garak-config"
    for d in (home, data / "garak", cache, config):
        d.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home),
        "USER": "garak",
        "LOGNAME": "garak",
        "XDG_DATA_HOME": str(data),
        "XDG_CACHE_HOME": str(cache),
        "XDG_CONFIG_HOME": str(config),
        "TORCHINDUCTOR_CACHE_DIR": str(cache / "torchinductor"),
    }


def run_py(argv: list[str], *, extra_env: dict[str, str] | None = None) -> None:
    """Run a repo Python script; use uv when the venv lacks safety.merge."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), **(extra_env or {})}
    try:
        import safety.merge  # noqa: F401
    except ImportError:
        subprocess.run(
            ["uv", "run", "python", *argv],
            cwd=str(REPO_ROOT),
            env=env,
            check=True,
        )
        return
    subprocess.run(
        [sys.executable, *argv],
        cwd=str(REPO_ROOT),
        env=env,
        check=True,
    )


def _prepare_promptfoo_host_dir() -> None:
    host_repo = os.environ.get("HOST_REPO", "").strip()
    if host_repo:
        os.environ["PROMPTFOO_HOST_DIR"] = f"{host_repo}/safety/promptfoo"


def _promptfoo_compose_env(base: dict[str, str], *, slug: str, profile: str) -> dict[str, str]:
    """Env passed explicitly to nested Promptfoo compose (host bind mounts)."""
    env = dict(base)
    host_repo = os.environ.get("HOST_REPO", "").strip()
    if host_repo:
        env["HOST_REPO"] = host_repo
        env["PROMPTFOO_HOST_DIR"] = f"{host_repo}/safety/promptfoo"
    elif os.environ.get("PROMPTFOO_HOST_DIR", "").strip():
        env["PROMPTFOO_HOST_DIR"] = os.environ["PROMPTFOO_HOST_DIR"].strip()
    env.setdefault("UID", str(os.getuid()))
    env.setdefault("GID", str(os.getgid()))
    env["PROMPTFOO_CONFIG_DIR"] = (
        f"/app/safety/promptfoo/output/{slug}/{profile}/.promptfoo"
    )
    return env


def _promptfoo_sqlite_contention(stderr: str) -> bool:
    needles = (
        'Failed query: update "evals"',
        "SQLITE_BUSY",
        "SQLITE_LOCKED",
        "database is locked",
    )
    lowered = stderr.lower()
    return any(n.lower() in lowered for n in needles)


def _compose_run_promptfoo(
    inner_cmd: list[str],
    *,
    extra_env: dict[str, str],
    label: str,
    retries: int = 2,
) -> None:
    """Run promptfoo via compose with bounded retry on SQLite contention."""
    last_exc: subprocess.CalledProcessError | None = None
    for attempt in range(max(1, retries)):
        try:
            compose_run(
                PROMPTFOO_COMPOSE,
                "promptfoo",
                inner_cmd,
                extra_env=extra_env,
                check=True,
            )
            return
        except subprocess.CalledProcessError as exc:
            last_exc = exc
            detail = (exc.stderr or exc.stdout or "").strip()
            if attempt + 1 < retries and _promptfoo_sqlite_contention(detail):
                delay = 1.5 * (attempt + 1)
                print(
                    f"WARN: {label} hit promptfoo SQLite contention; "
                    f"retrying in {delay:.1f}s ({attempt + 2}/{retries})",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise
    if last_exc is not None:
        raise last_exc


def _ensure_output_dirs(slug: str, profile: str) -> None:
    for path in (
        REPO_ROOT / "safety" / "promptfoo" / "output" / slug / profile,
        REPO_ROOT / "safety" / "garak" / "output" / slug,
        REPO_ROOT / "safety" / "output" / slug / profile,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _latest_garak_report(slug: str) -> Path | None:
    out = REPO_ROOT / "safety" / "garak" / "output" / slug
    candidates = sorted(
        out.glob("garak-duke*.report.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _require_artifact(path: Path, label: str) -> int | None:
    if not path.is_file() or path.stat().st_size == 0:
        print(
            f"ERROR: {label} finished but {path} is missing or empty",
            file=sys.stderr,
        )
        return 1
    return None


def _export_promptfoo_eval(eval_json: Path, *, label: str) -> int | None:
    err = _require_artifact(eval_json, label)
    if err:
        return err
    try:
        run_py(["safety/promptfoo/export_safety_result.py", str(eval_json)])
    except subprocess.CalledProcessError as exc:
        print(
            f"ERROR: export failed for {eval_json} (exit {exc.returncode})",
            file=sys.stderr,
        )
        if eval_json.is_file():
            tail = eval_json.read_bytes()[-500:]
            print(f"  eval tail ({len(tail)} bytes): {tail!r}", file=sys.stderr)
        return exc.returncode or 1
    return None


def run_pipeline(cfg: RunConfig) -> int:
    """Run Promptfoo + Garak + merge for one model. Returns exit code."""
    if cfg.skip_promptfoo and cfg.skip_garak:
        print("ERROR: cannot use --skip-promptfoo and --skip-garak together", file=sys.stderr)
        return 1
    if cfg.skip_policy and not cfg.redteam:
        cfg = RunConfig(
            model=cfg.model,
            redteam_profile=cfg.redteam_profile,
            skip_policy=cfg.skip_policy,
            redteam=cfg.redteam,
            skip_promptfoo=True,
            skip_garak=cfg.skip_garak,
            garak_probes=cfg.garak_probes,
        )

    os.environ["GATEWAY_MODEL"] = cfg.model
    os.environ.setdefault("REDTEAM_GRADER_MODEL", "GPT 4.1 Mini")
    slug = normalize_gateway_model_id(cfg.model)
    out_dir = REPO_ROOT / "safety" / "output" / slug / cfg.redteam_profile
    lock_file = run_lock.lock_path(out_dir)
    if run_lock.should_skip_cli_acquire(lock_file):
        pass
    elif not run_lock.try_acquire(
        lock_file,
        command=f"safety.run {cfg.model} profile={cfg.redteam_profile}",
        source="cli",
    ):
        print(
            f"ERROR: safety run already in progress for {cfg.model!r} "
            f"(profile {cfg.redteam_profile}) — see {lock_file}",
            file=sys.stderr,
        )
        return 2

    try:
        return _run_pipeline_impl(cfg, slug)
    finally:
        if not run_lock.should_skip_cli_acquire(lock_file):
            run_lock.release(lock_file)


def _run_pipeline_impl(cfg: RunConfig, slug: str) -> int:
    _prepare_promptfoo_host_dir()
    _ensure_output_dirs(slug, cfg.redteam_profile)

    if not os.environ.get("HOST_REPO", "").strip():
        print(
            "WARNING: HOST_REPO is unset — nested Promptfoo bind mounts may write "
            "to the wrong host path. Set HOST_REPO to the repo root on the Docker host.",
            file=sys.stderr,
        )

    print(
        f"Safety run: model={cfg.model} slug={slug} "
        f"profile={cfg.redteam_profile} redteam={cfg.redteam}",
        flush=True,
    )

    merge_args: list[str] = []
    exit_rc = 0
    grader = os.environ["REDTEAM_GRADER_MODEL"]
    pf_env = _promptfoo_compose_env({
        "GATEWAY_MODEL": cfg.model,
        "REDTEAM_GRADER_MODEL": grader,
    }, slug=slug, profile=cfg.redteam_profile)

    pf_output = REPO_ROOT / "safety" / "promptfoo" / "output" / slug / cfg.redteam_profile

    if not cfg.skip_promptfoo:
        if not cfg.skip_policy:
            print("--- Promptfoo policy ---", flush=True)
            eval_json = pf_output / "eval.json"
            try:
                _compose_run_promptfoo(
                    [
                        "promptfoo", "eval", "-c", "promptfooconfig.yaml",
                        "-o", f"output/{slug}/{cfg.redteam_profile}/eval.json",
                    ],
                    extra_env=pf_env,
                    label="policy eval",
                )
            except subprocess.CalledProcessError as exc:
                if not eval_json.is_file():
                    print(
                        f"ERROR: policy eval failed (exit {exc.returncode}); no eval.json written",
                        file=sys.stderr,
                    )
                    return exc.returncode or 1

            rc = _export_promptfoo_eval(eval_json, label="policy eval")
            if rc:
                return rc
            merge_args.extend([
                "--promptfoo",
                str(pf_output / "safety_result.json"),
            ])
        else:
            print("--- Promptfoo policy skipped (--skip-policy) ---", flush=True)

        if cfg.redteam:
            print(f"--- Promptfoo red-team (profile={cfg.redteam_profile}) ---", flush=True)
            redteam_json = pf_output / "redteam_eval.json"
            run_py([
                "safety/promptfoo/build_config.py",
                "--profile", cfg.redteam_profile,
                "--output-dir", str(pf_output),
            ])
            redteam_config = pf_output / "redteam_promptfooconfig.yaml"
            config_in_container = (
                f"output/{slug}/{cfg.redteam_profile}/redteam_promptfooconfig.yaml"
            )
            try:
                _compose_run_promptfoo(
                    [
                        "promptfoo", "redteam", "run",
                        "-c", config_in_container,
                        "-o", f"output/{slug}/{cfg.redteam_profile}/redteam_eval.json",
                        "--delay", "500",
                        "--max-concurrency", "1",
                        "--force",
                    ],
                    extra_env=pf_env,
                    label="red-team eval",
                )
            except subprocess.CalledProcessError as exc:
                if not redteam_json.is_file():
                    print(f"ERROR: red-team failed (exit {exc.returncode})", file=sys.stderr)
                    if not redteam_config.is_file():
                        print(
                            f"  red-team config missing: {redteam_config}",
                            file=sys.stderr,
                        )
                    return exc.returncode or 1

            rc = _export_promptfoo_eval(redteam_json, label="red-team eval")
            if rc:
                return rc
            merge_args.extend([
                "--promptfoo",
                str(pf_output / "redteam_safety_result.json"),
            ])

            print("--- Promptfoo manual evals (remote-plugin coverage) ---", flush=True)
            for stem, yaml_rel in MANUAL_EVALS:
                print(f"  running {yaml_rel} ...", flush=True)
                manual_eval = pf_output / f"manual_{stem}_eval.json"
                try:
                    _compose_run_promptfoo(
                        [
                            "promptfoo", "eval", "-c", yaml_rel,
                            "-o", f"output/{slug}/{cfg.redteam_profile}/manual_{stem}_eval.json",
                        ],
                        extra_env=pf_env,
                        label=f"manual eval {stem}",
                    )
                except subprocess.CalledProcessError:
                    pass
                if not manual_eval.is_file():
                    print(f"WARN: manual eval '{stem}' failed, skipping", file=sys.stderr, flush=True)
                    continue

                manual_result = pf_output / f"manual_{stem}_safety_result.json"
                try:
                    run_py([
                        "safety/promptfoo/export_safety_result.py",
                        str(manual_eval),
                        "-o", str(manual_result),
                    ])
                except subprocess.CalledProcessError as exc:
                    print(
                        f"WARN: export failed for manual eval '{stem}' (exit {exc.returncode}), skipping",
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                merge_args.extend(["--promptfoo", str(manual_result)])
        else:
            print("--- Promptfoo red-team skipped (--skip-redteam) ---", flush=True)
    else:
        print("--- Promptfoo skipped (--skip-promptfoo) ---", flush=True)

    garak_failed = False
    garak_rc = 0
    if not cfg.skip_garak:
        print("--- Garak scan ---", flush=True)
        xdg = garak_xdg_env(slug)
        garak_argv = [
            "safety/garak/run_garak.py", cfg.model,
            "--report-dir", str(REPO_ROOT / "safety" / "garak" / "output" / slug),
        ]
        if cfg.garak_probes:
            garak_argv.extend(["-p", cfg.garak_probes])

        try:
            run_py(garak_argv, extra_env=xdg)
        except subprocess.CalledProcessError as exc:
            garak_rc = exc.returncode or 1
            garak_failed = True

        report = _latest_garak_report(slug)
        if report is None:
            garak_failed = True
            print(
                f"ERROR: Garak finished (exit {garak_rc}) but no report in "
                f"safety/garak/output/{slug}/",
                file=sys.stderr,
            )
            if merge_args:
                print(
                    "WARNING: Garak failed; merged result omits garak",
                    file=sys.stderr,
                )
            else:
                return garak_rc or 1
        else:
            probe_spec = cfg.garak_probes or DEFAULT_PROBE_SPEC
            ok, err, _analysis = validate_report(report, probe_spec=probe_spec)
            if not ok:
                garak_failed = True
                garak_rc = 1
                print(f"ERROR: {err}", file=sys.stderr)
                if merge_args:
                    print(
                        "WARNING: Garak failed; merged result omits garak",
                        file=sys.stderr,
                    )
                else:
                    return garak_rc
            else:
                print("--- Garak export ---", flush=True)
                garak_result = (
                    REPO_ROOT / "safety" / "garak" / "output" / slug / "safety_result.json"
                )
                try:
                    run_py([
                        "safety/garak/export_safety_result.py",
                        str(report),
                        "-o", str(garak_result),
                        "--gateway-model-id", cfg.model,
                    ])
                except subprocess.CalledProcessError as exc:
                    garak_failed = True
                    garak_rc = exc.returncode or 1
                    print(
                        f"ERROR: Garak export failed (exit {garak_rc})",
                        file=sys.stderr,
                    )
                    if merge_args:
                        print(
                            "WARNING: Garak failed; merged result omits garak",
                            file=sys.stderr,
                        )
                    else:
                        return garak_rc
                else:
                    merge_args.extend(["--garak", str(garak_result)])
                    profile_copy = (
                        REPO_ROOT / "safety" / "output" / slug / cfg.redteam_profile
                        / "garak_safety_result.json"
                    )
                    try:
                        shutil.copy2(garak_result, profile_copy)
                    except OSError:
                        pass
    else:
        print("--- Garak skipped (--skip-garak) ---", flush=True)

    if not merge_args:
        print("ERROR: nothing to merge — run at least one suite", file=sys.stderr)
        return 1

    merged = (
        REPO_ROOT / "safety" / "output" / slug / cfg.redteam_profile / "merged_safety_result.json"
    )
    print("--- Merge ---", flush=True)
    run_py(["-m", "safety.merge", *merge_args, "--profile", cfg.redteam_profile, "-o", str(merged)])
    if cfg.skip_garak:
        print("Garak: SKIPPED", flush=True)
    elif garak_failed:
        print("Garak: FAILED (merged without garak)", file=sys.stderr, flush=True)
    else:
        print("Garak: OK", flush=True)
    print(f"Complete: {merged.relative_to(REPO_ROOT)}", flush=True)
    print(f"Frontend: /safety/{slug}/{cfg.redteam_profile}", flush=True)
    if garak_failed:
        exit_rc = garak_rc or 1
    return exit_rc


def run_all_models(cfg: RunConfig) -> int:
    """Sequential pipeline for every gateway model in ALL_MODELS."""
    master = REPO_ROOT / "safety" / "output" / "sequential_run.log"
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    master.parent.mkdir(parents=True, exist_ok=True)
    with master.open("a", encoding="utf-8") as fh:
        fh.write(f"=== Sequential safety started {stamp} ===\n")

    rc = 0
    for model in ALL_MODELS:
        slug = normalize_gateway_model_id(model)
        log_path = REPO_ROOT / "safety" / "output" / slug / "run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"\n========================================\n START: {model} (slug={slug})\n========================================")
        with master.open("a", encoding="utf-8") as fh:
            fh.write(f"=== START {model} (slug={slug}) ===\n")
        one = RunConfig(
            model=model,
            redteam_profile=cfg.redteam_profile,
            skip_policy=cfg.skip_policy,
            redteam=cfg.redteam,
            skip_promptfoo=cfg.skip_promptfoo,
            skip_garak=cfg.skip_garak,
            garak_probes=cfg.garak_probes,
        )
        proc_rc = run_pipeline(one)
        log_path.write_text(f"exit={proc_rc}\n", encoding="utf-8")
        if proc_rc != 0:
            rc = proc_rc
        with master.open("a", encoding="utf-8") as fh:
            fh.write(f"=== DONE {model} exit={proc_rc} ===\n")
    with master.open("a", encoding="utf-8") as fh:
        fh.write("=== All models complete ===\n")
    return rc


def garak_setup() -> int:
    """One-time download of Garak detector models into the mounted cache."""
    print("Building garak image (skipped if already built)...")
    compose_build(GARAK_COMPOSE, "garak")
    print("Downloading garak-llm/roberta_toxicity_classifier...")
    compose_run(
        GARAK_COMPOSE,
        "garak",
        [
            "python", "-c",
            "from garak.detectors.unsafe_content import ToxicCommentModel; "
            "ToxicCommentModel(); print('Done.')",
        ],
        check=True,
    )
    cache = REPO_ROOT / "safety" / "garak" / "output" / ".garak-cache" / "huggingface"
    print(f"\nDone. Model cached at {cache.relative_to(REPO_ROOT)}/")
    print("\nNext step: update probe_spec in safety/garak/garak_duke.yaml")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="End-to-end safety: Promptfoo policy, red-team, Garak, merge.",
    )
    ap.add_argument(
        "positional",
        nargs="*",
        help="Optional model name, or 'garak-setup' subcommand",
    )
    ap.add_argument(
        "--redteam-profile",
        choices=sorted(VALID_PROFILES),
        default="base",
        help="Red-team plugin profile (default: base)",
    )
    ap.add_argument("--skip-redteam", action="store_true", help="Skip Promptfoo red-team")
    ap.add_argument("--skip-policy", action="store_true", help="Skip Promptfoo policy eval")
    ap.add_argument("--skip-promptfoo", action="store_true", help="Skip all Promptfoo suites")
    ap.add_argument("--skip-garak", action="store_true", help="Skip Garak")
    ap.add_argument("--garak-probes", default="", metavar="LIST", help="Comma-separated Garak modules")
    ap.add_argument(
        "--all-models",
        action="store_true",
        help="Run sequentially for all default gateway models",
    )
    return ap


def parse_args(argv: list[str] | None = None) -> tuple[str | None, RunConfig | None]:
    if argv and argv[0] == "garak-setup":
        return "garak-setup", None

    ap = build_parser()
    args = ap.parse_args(argv)

    positionals = list(args.positional or [])
    if positionals and positionals[0] == "garak-setup":
        return "garak-setup", None

    model = os.environ.get("GATEWAY_MODEL", "GPT 4.1 Mini")
    if positionals and not positionals[0].startswith("-"):
        model = positionals[0]

    cfg = RunConfig(
        model=model,
        redteam_profile=args.redteam_profile,
        skip_policy=args.skip_policy,
        redteam=not args.skip_redteam,
        skip_promptfoo=args.skip_promptfoo,
        skip_garak=args.skip_garak,
        garak_probes=args.garak_probes or "",
    )
    if args.all_models:
        return "all-models", cfg
    return None, cfg


def main(argv: list[str] | None = None) -> int:
    sub, cfg = parse_args(argv)
    if sub == "garak-setup":
        return garak_setup()
    if sub == "all-models":
        assert cfg is not None
        return run_all_models(cfg)
    assert cfg is not None
    return run_pipeline(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
