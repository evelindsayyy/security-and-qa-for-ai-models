# Auth (`auth/`)

Duke **OIDC** login for the nutrition-label UI. Users see the standard Duke Shibboleth screen; the app integrates via OAuth 2.0 / OpenID Connect (no Shibboleth SP on the VM).

## Behavior

| Mode | Login | Browse | Start runs |
|------|-------|--------|------------|
| **Public** (default) | Not required | Public catalog runs | Default configs; reuses matching DB rows |
| **Private** | Allowlisted NetID | Public + own private runs | Custom eval, non-base safety profiles, etc. |

Session state: Flask cookie (`user`, `view_mode`). Run ownership and dedup live in Postgres — see [`docs/auth-setup.md`](../docs/auth-setup.md).

## Modules

| File | Role |
|------|------|
| `oidc.py` | Authlib client; Duke discovery URL |
| `session.py` | `effective_user()`, `is_allowlisted()`, view mode |
| `routes.py` | `/auth/login`, `/callback`, `/logout`, `/me`, `/view-mode` |
| `decorators.py` | `@require_login`, `@require_private_login` |

Registered from `frontend/create_app()` via `register_auth(app)`.

## Environment

| Variable | Purpose |
|----------|---------|
| `AUTH_ENABLED` | `1` = real OIDC; `0` = dev bypass |
| `SECRET_KEY` | Flask session signing (required in production) |
| `DUKE_OIDC_CLIENT_ID` / `DUKE_OIDC_CLIENT_SECRET` | From Duke Authentication Manager |
| `DUKE_OIDC_REDIRECT_URI` | Must match registered redirect exactly (`https://…/login` in production) |
| `AUTH_ALLOWED_NETIDS` | Comma-separated netIDs for private mode |
| `AUTH_DEV_NETID` | Optional fake user when `AUTH_ENABLED=0` |

## HTTP routes

```bash
# Session status
curl -s http://127.0.0.1:5000/auth/me | python3 -m json.tool

# Toggle view (browser form POST; API accepts JSON)
curl -s -X POST http://127.0.0.1:5000/auth/view-mode -d mode=public

# Logout
curl -s -X POST http://127.0.0.1:5000/auth/logout
```

Login is browser-only: header **Sign in with Duke NetID** opens `/auth/login?popup=1` → Duke OIDC → `/login` (or `/auth/callback`).

Production HTTPS and OIDC rollout: [`docs/https-setup.md`](../docs/https-setup.md) then [`docs/auth-setup.md`](../docs/auth-setup.md).

## Related code

- Run fingerprints: [`dbutils/run_fingerprint.py`](../dbutils/run_fingerprint.py)
- Launch reuse: [`frontend/run_launch.py`](../frontend/run_launch.py)
- DDL: [`db/auth_schema.sql`](../db/auth_schema.sql)
- Operator guide: [`docs/auth-setup.md`](../docs/auth-setup.md)
