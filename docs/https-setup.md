# HTTPS setup (Caddy + Duke ACME)

Production TLS for `model-advisor.colab.duke.edu` without `:5000` in the URL. Caddy terminates HTTPS and forwards to the Flask `web` container on port 5000 inside Docker.

**Do this before enabling OIDC** (`AUTH_ENABLED=1`). See [`auth-setup.md`](auth-setup.md) for login configuration after HTTPS works.

---

## Architecture

```text
User browser  →  https://model-advisor.colab.duke.edu  →  Caddy (:443)
                                                          →  web:5000 (Flask)
```

- **Local dev (DGX):** no Caddy — `uv run python main.py --host` or `./docker/run.sh up` on port 5000.
- **Production VM:** set `CADDY_DOMAIN` in `.env` — `./docker/run.sh` auto-includes [`docker/compose.caddy.yml`](../docker/compose.caddy.yml).

Files:

| File | Role |
|------|------|
| [`docker/Caddyfile`](../docker/Caddyfile) | TLS via Duke Locksmith ACME + reverse proxy |
| [`docker/compose.caddy.yml`](../docker/compose.caddy.yml) | `caddy` service; `web` exposed only on internal network |

---

## Phase 1 — Configure VM `.env`

On `model-advisor.colab.duke.edu`, edit `/home/vcm/security-and-qa-for-ai-models/.env`:

```bash
# HTTPS (Caddy)
CADDY_DOMAIN=model-advisor.colab.duke.edu
CADDY_EMAIL=your-netid@duke.edu
CADDY_ACME_HOSTNAME=locksmith.oit.duke.edu
CADDY_BACKEND_PORT=5000
TRUST_PROXY=1

# Auth stays off until HTTPS smoke test passes
AUTH_ENABLED=0
SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_hex(32))">
```

Leave `CADDY_DOMAIN` blank on local machines.

---

## Phase 2 — Deploy and start with Caddy

```bash
cd /home/vcm/security-and-qa-for-ai-models
git pull origin auth    # or main after merge
./docker/run.sh up -d --build
```

When `CADDY_DOMAIN` is set, `run.sh` adds the Caddy overlay automatically. CI deploy ([`docker/deploy-remote.sh`](../docker/deploy-remote.sh)) does the same.

Check containers:

```bash
docker compose --project-name qa-ai-models ps
docker compose --project-name qa-ai-models logs -f caddy
```

First start may take a minute while Caddy obtains a certificate from `locksmith.oit.duke.edu`.

---

## Phase 3 — HTTPS smoke test (auth still off)

```bash
BASE=https://model-advisor.colab.duke.edu

# TLS + health
curl -s "$BASE/api/health" | python3 -m json.tool
# Expect: ok true, db_available true

# No :5000 in URL
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/scans"
# Expect: 200

curl -s "$BASE/auth/me" | python3 -m json.tool
# Expect: authenticated false, auth_enabled false
```

Open `https://model-advisor.colab.duke.edu` in a browser — confirm valid certificate and UI loads.

---

## Phase 4 — Enable OIDC (after HTTPS works)

George registered OAuth client **`codeplus-model-advisor`** with redirect URI:

```text
https://model-advisor.colab.duke.edu/login
```

Add to VM `.env` (secret from George's 1Password link — never commit):

```bash
DUKE_OIDC_CLIENT_ID=codeplus-model-advisor
DUKE_OIDC_CLIENT_SECRET=<from 1Password>
DUKE_OIDC_REDIRECT_URI=https://model-advisor.colab.duke.edu/login
AUTH_ALLOWED_NETIDS=yournetid,teammate1
AUTH_ENABLED=1
TRUST_PROXY=1
```

Restart:

```bash
./docker/run.sh up -d --force-recreate web caddy
```

**Routes:**

| URL | Purpose |
|-----|---------|
| `/auth/login` | User clicks Sign in — starts OIDC flow |
| `/login` | OAuth redirect target (George's registered URI) |
| `/auth/callback` | Alternate callback (also supported) |

Local dev redirect URI: `http://localhost:5000/login`

---

## Phase 5 — Auth smoke test

```bash
BASE=https://model-advisor.colab.duke.edu

curl -s "$BASE/auth/me" | python3 -m json.tool
# auth_enabled true, authenticated false

# Browser (manual):
# 1. Open $BASE/ — Public | Private toggle and Sign in visible
# 2. Public mode: browse /scans without login
# 3. Private → Sign in → Duke login → signed in as <netID>
# 4. /eval-run/new → custom questions in Private mode
```

If login fails with **redirect_uri mismatch**, compare Duke registration character-for-character with `DUKE_OIDC_REDIRECT_URI`.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Caddy won't start | `CADDY_DOMAIN`, `CADDY_EMAIL` set in `.env`; ports 80/443 open on VM firewall |
| Certificate error | `docker compose logs caddy` — Locksmith ACME failures; confirm domain is eligible |
| App still on `:5000` | `CADDY_DOMAIN` set? Restart with `./docker/run.sh up -d` (includes caddy overlay) |
| Session lost after login | `TRUST_PROXY=1` in `.env`; restart `web` |
| OAuth redirect mismatch | `DUKE_OIDC_REDIRECT_URI` must be `https://model-advisor.colab.duke.edu/login` |
| Mixed content / HTTP links | `TRUST_PROXY=1` enables `ProxyFix` and secure session cookies |

---

## Local development

Do **not** run Caddy locally. Use:

```bash
uv run python main.py --host
# or
./docker/run.sh up --build    # CADDY_DOMAIN must be blank in .env
```

For local OIDC testing with George's localhost redirect:

```bash
DUKE_OIDC_REDIRECT_URI=http://localhost:5000/login
AUTH_ENABLED=1
# ... client id + secret ...
```
