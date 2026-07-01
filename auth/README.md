# Auth (`auth/`)

Duke **OIDC** login for the nutrition-label UI. Users see the standard Duke Shibboleth screen; the app integrates via OAuth 2.0 / OpenID Connect (no Shibboleth SP on the VM).

## Behavior

| Mode | Login | Browse | Start runs |
|------|-------|--------|------------|
| **Public** (default) | Not required | Public catalog runs | Requires login. Default configs; reuses matching DB rows |
| **Private** | Allowlisted NetID | Public + own private runs | Requires login + allowlist. Custom eval, non-base safety profiles, etc. |

Browsing is always open — anyone can read the public catalog without signing in.
Starting a run (any pillar, any config) or deleting a result requires a
signed-in, allowlisted NetID; the "Start …" and "Delete" controls render
disabled for signed-out visitors, and the underlying `/…/start`, `/…/new`,
and `/…/delete` routes redirect to login (`@require_login`) if hit directly.
Private-mode-only actions (custom eval questions, non-base safety profiles)
add the private-view + allowlist check on top via `@require_private_login` /
`require_private_access()`.

Session state: Flask cookie (`user`, `view_mode`). Run ownership, visibility
scoping, and dedup live in Postgres (`db/auth_schema.sql`) plus per-run
`run_meta.json`/`scan_meta.json` sidecars on disk — see
[`frontend/run_paths.py`](../frontend/run_paths.py) for how private runs are
kept on a separate on-disk path per pillar, and
[`PROJECT_GUIDE.md`](../PROJECT_GUIDE.md) for the full isolation model.

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
| `DUKE_OIDC_REDIRECT_URI` | Optional explicit callback; leave blank to infer `CADDY_DOMAIN` in production or the current loopback host in local dev |
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

Production HTTPS runs through the Caddy compose overlay in [`docker/`](../docker/).

### OIDC callback ports (local dev / IDE port-forwarding)

`DUKE_OIDC_REDIRECT_URI` is normally left **blank** — the callback URL is
computed per request by [`oidc.redirect_uri()`](oidc.py), in this order:

1. `CADDY_DOMAIN` set → `https://<domain>/login` (production).
2. Otherwise, the **current request's Host header** → `http://<host>/login`
   (loopback and RFC1918-private hosts keep `http://`; anything else is
   upgraded to `https://` — see `_is_private_host()` in `oidc.py`).
3. `DUKE_OIDC_REDIRECT_URI` if explicitly set.
4. Fallback: `http://localhost:5000/login`.

Duke's OIDC client (`codeplus-model-advisor`) has a **fixed, short**
registered redirect_uri allowlist — currently `http://localhost:5000/login`
and the production `https://model-advisor.colab.duke.edu/login`. Duke's
server is lenient about the *port* specifically for the `localhost` hostname
(the RFC 8252 §7.3 "loopback native app" pattern), so any `localhost:<port>`
callback is accepted — but a raw IP (including a LAN IP, and including
`10.x.x.x`) is rejected outright with `invalid_grant`, no exceptions. This
means login only works from a URL where the browser's Host header reads
`localhost:<some-port>` — a LAN IP or hostname will never work here,
independent of anything this app computes.

**If login fails locally**, check in this order:
1. Is the app actually reachable on the port the browser is using?
   `docker ps` (is the `web` container running?) and
   `docker compose -f docker/compose.yml logs -f web` — look for the
   `oauth login start host=... redirect_uri=...` line. If the callback
   request never reaches this log at all, it's a connectivity/port-forwarding
   problem outside the app, not something the code can fix.
2. Is the browser's address bar showing `localhost:<port>` (not a LAN IP or
   a custom hostname)? If not, that's the entire problem — see above.
3. If using an IDE's auto-forwarded port (VS Code Remote, JetBrains Gateway,
   or similar): those tools tunnel an arbitrary local port and can silently
   drop/reassign the forward (e.g. after the browser sits idle on Duke's
   external Shibboleth/2FA page for 10–60+ seconds). Prefer a plain, stable
   SSH tunnel on the exact registered port instead of relying on
   auto-detection:
   ```bash
   # From your local machine — replace the host with the remote SSH target
   ssh -L 5000:localhost:5000 <user>@<remote-host>
   ```
   then browse `http://localhost:5000/`. This lands on exactly the
   redirect_uri Duke has registered, with no dynamic reassignment.

`auth/oidc.py` sets a 10s timeout on every Duke network call (discovery
fetch, token exchange) and `login()` catches any exception from
`authorize_redirect(...)` and returns a clean `502` rather than hanging or
raising a bare `500`. The public (signed-out) site is never gated on auth —
a slow or failing login attempt in one request never blocks `/scans` or any
other public read in a concurrent request (see
`unit_tests/test_https_proxy.py`).

## Related code

- Run fingerprints: [`dbutils/run_fingerprint.py`](../dbutils/run_fingerprint.py)
- Launch reuse: [`frontend/run_launch.py`](../frontend/run_launch.py)
- DDL: [`db/auth_schema.sql`](../db/auth_schema.sql)
