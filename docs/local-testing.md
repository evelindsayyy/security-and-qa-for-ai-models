# Local testing before VM deploy

Test on DGX (or your laptop) **before** merging to `main`, deploying to the VM, or pasting production secrets. Production rollout: [`https-setup.md`](https-setup.md) → [`auth-setup.md`](auth-setup.md).

---

## What you can vs cannot test locally

| Feature | Local? | How |
|---------|--------|-----|
| Auth logic, visibility, fingerprints | Yes | Unit tests |
| Public / private UI (no Duke login) | Yes | `AUTH_DEV_NETID` bypass |
| Real Duke OIDC login | Yes | `localhost:5000/login` redirect + client secret |
| Caddy + Duke Locksmith TLS | **No** | Needs `model-advisor.colab.duke.edu` on the VM |
| HTTPS without `:5000` | **No** | Caddy is production-only |
| `TRUST_PROXY` / secure cookies | Partially | Unit tests; full path only on VM |

---

## Tier 1 — Automated (no secrets, run every time)

From repo root on the **auth** branch:

```bash
uv sync --group dev
uv run python -m unittest discover -s unit_tests -q
uv run ruff check auth frontend docker db dbutils/run_fingerprint.py dbutils/run_access.py
```

Covers: session helpers, `/login` and `/auth/callback` routes, proxy cookie config, launch reuse, visibility filters.

---

## Tier 2 — Local app smoke (auth bypass, no OAuth)

Use a **local-only** `.env` (do not copy production secrets into git):

```bash
# Keep Caddy off locally
CADDY_DOMAIN=
TRUST_PROXY=0

# Simulate logged-in user without Duke OAuth
AUTH_ENABLED=0
AUTH_DEV_NETID=jkm75
AUTH_ALLOWED_NETIDS=jkm75,jy403,nv93,lz302
SECRET_KEY=dev-local-only
```

Start server:

```bash
uv run python main.py --host &
sleep 2
```

Checks:

```bash
# Health + DB
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool

# Dev user present without login
curl -s http://127.0.0.1:5000/auth/me | python3 -m json.tool
# Expect: authenticated true (dev bypass), view_mode public

# Private mode (browser): toggle Private in header — should work without Duke login
# Custom eval POST needs private session — set view_mode via browser or:
curl -s -c /tmp/cookies -b /tmp/cookies -X POST http://127.0.0.1:5000/auth/view-mode -d mode=private -L -o /dev/null -w "%{http_code}\n"

kill %1 2>/dev/null || pkill -f "main.py --host" || true
```

**Browser:** open `http://127.0.0.1:5000` → Public/Private toggle → Private mode → `/eval-run/new` custom form (no real Shibboleth screen).

---

## Tier 3 — Real Duke OIDC on localhost (optional, before VM)

George registered **`http://localhost:5000/login`** as a redirect URI. You need the **client secret** from his 1Password link.

Local `.env` (temporarily):

```bash
CADDY_DOMAIN=
TRUST_PROXY=0

AUTH_ENABLED=1
SECRET_KEY=dev-local-only-change-me
DUKE_OIDC_CLIENT_ID=codeplus-model-advisor
DUKE_OIDC_CLIENT_SECRET=<from 1Password>
DUKE_OIDC_REDIRECT_URI=http://localhost:5000/login
AUTH_ALLOWED_NETIDS=jkm75,jy403,nv93,lz302
# Leave AUTH_DEV_NETID unset when testing real OIDC
```

Start and test:

```bash
uv run python main.py --host
```

1. Open `http://127.0.0.1:5000` (use `127.0.0.1`, not `localhost`, if cookies act odd).
2. Switch to **Private** → **Sign in with Duke NetID**.
3. Complete Duke login → popup closes or redirects back.
4. Header shows your netID; `/auth/me` shows `"authenticated": true`.

```bash
curl -s http://127.0.0.1:5000/auth/me | python3 -m json.tool
```

**Redirect mismatch?** `DUKE_OIDC_REDIRECT_URI` must be exactly `http://localhost:5000/login` (not `/auth/callback`, not `https`).

---

## Tier 4 — Docker UI locally (still no Caddy)

Same as Tier 2 or 3, but containerized pillar launches:

```bash
# .env must have CADDY_DOMAIN= empty
./docker/build-pillars.sh    # once
./docker/run.sh up -d --build
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool
```

Do **not** set `CADDY_DOMAIN` on DGX — Locksmith will fail and Caddy will not start usefully.

---

## Tier 5 — Production-only (VM after merge)

Only on `model-advisor.colab.duke.edu`:

1. `CADDY_DOMAIN=model-advisor.colab.duke.edu`, `TRUST_PROXY=1`
2. `./docker/run.sh up -d --build` → `https://model-advisor.colab.duke.edu/api/health`
3. Then `AUTH_ENABLED=1` + production redirect `https://model-advisor.colab.duke.edu/login`

See [`https-setup.md`](https-setup.md).

---

## Suggested order before merge to main

```text
1. Tier 1 — unit tests + ruff (auth branch)
2. Tier 2 — AUTH_DEV_NETID browser smoke (private mode, custom eval form)
3. Tier 3 — real OIDC on localhost (once you have 1Password secret)
4. Merge auth → main
5. VM Tier 5 — HTTPS, then AUTH_ENABLED=1 with production .env
```

---

## Common local mistakes

| Mistake | Fix |
|---------|-----|
| `python3 main.py --host` without uv | Use `uv run python main.py --host` (needs venv deps) |
| Old redirect URI `/auth/callback` | Use `http://localhost:5000/login` for local OIDC |
| Spaces in `AUTH_ALLOWED_NETIDS` | Use `jkm75,jy403` not `jkm75, jy403` |
| Caddy on DGX | Leave `CADDY_DOMAIN` empty locally |
| Testing HTTPS locally | Not supported; validate on VM only |
