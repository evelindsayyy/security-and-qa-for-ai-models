# Auth (`auth/`)

Duke **OIDC** login for the nutrition-label UI. Users see the standard Duke Shibboleth screen; the app integrates via OAuth 2.0 / OpenID Connect (no Shibboleth SP on the VM).

## Behavior

| Mode | Login | Browse | Start runs |
|------|-------|--------|------------|
| **Public** (default) | Not required | Public catalog runs | Requires login. Default configs; reuses matching DB rows |
| **Private** | Allowlisted NetID | Public + own private runs | Requires login + allowlist. Custom eval, non-base safety profiles, etc. |

Browsing is always open — anyone can read the public catalog without signing in.
Starting a run (any pillar, any config) requires a signed-in, allowlisted
NetID; the "Start …" buttons render disabled for signed-out visitors and the
`/…/start` and `/…/new` routes redirect to login (`@require_login`) if hit
directly. Private-mode-only actions (custom eval questions, non-base safety
profiles) add the private-view + allowlist check on top via
`@require_private_login` / `require_private_access()`.

Session state: Flask cookie (`user`, `view_mode`). Run ownership and dedup live in Postgres.

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
   (loopback hosts keep `http://`; anything else is upgraded to `https://`).
3. `DUKE_OIDC_REDIRECT_URI` if explicitly set.
4. Fallback: `http://localhost:5000/login`.

Step 2 is why local dev needs **no port configuration at all**, including
behind an IDE's auto-forwarded port (VS Code Remote, JetBrains Gateway,
`ssh -L`, …): those tools tunnel an arbitrary, unpredictable local port to
this app and rewrite nothing else, so whatever port shows up in the
browser's Host header is read straight off the request and echoed back as
the callback port — no `.env` value to keep in sync, so it can't go stale
when the IDE picks a different port on the next reconnect (which it does,
often). Duke's OIDC client (`codeplus-model-advisor`) accepts the callback
on any localhost/127.0.0.1 port — verified against the live discovery
endpoint, not just assumed.

**If login still fails locally:** it's almost always that the *server*
isn't reachable on the port the browser is using — not an OIDC/redirect_uri
problem. Check with `docker ps` (is the `web` container even running?) and
`docker compose -f docker/compose.yml logs -f web` (look for the
`oauth login start host=... redirect_uri=...` line — the host and the
redirect_uri port must match; if the request never reaches the log at all,
it's a connectivity/port-forwarding problem outside the app, not something
this app's code can fix).

### "The Shibboleth page worked, but the callback / the whole site broke afterward"

Observed symptom: click **Sign in**, Duke's real Shibboleth login page
loads and you authenticate successfully, then the *callback*
(`localhost:<port>/login?code=...`) fails with something like "the server
unexpectedly dropped the connection" — and afterward, even a plain reload
of the main tab on that same port fails the same way, surviving a full
`docker compose down && up`.

Diagnosed 2026-07-01 by reproducing the flow end-to-end (curl against the
live container, and an in-process concurrency test — see
`unit_tests.test_https_proxy.TestLoginSurvivesOAuthNetworkFailure`) plus
reading the container's access log line by line:

- The container's log showed the **initial** `/auth/login` request served
  cleanly (`302`, correct `redirect_uri` for that session's port) and then
  **nothing** — not even an attempt — for the callback request. If our
  Flask app had received it, it would be in the log (every request is,
  successful or not) and the app would have handled it cleanly either way
  (see `oauth_callback()` — bad/missing state and token-exchange failures
  both return a plain 400, never a hang or a crash).
- That rules out anything in this app's Python code: the request to
  `/login?code=...` never arrived. Restarting the container doesn't
  create a new *client-side* tunnel entry for the old port, which is
  consistent with what actually happened — **the IDE's port-forward for
  that specific local port died while the browser was away on Duke's
  external Shibboleth/2FA page** (which can easily take 10–60+ seconds;
  some port-forwarding tools tear down a local listener that's had no
  traffic for a while). Once that forward is gone, *every* request on
  that port fails identically, login-related or not — that's why the
  plain page reload broke too, and why it didn't matter that the server
  itself was healthy.
- **This is a property of the IDE's local port-forwarding, not something
  this app's code can detect or recover from** — there is no request
  reaching the server for it to act on. If this happens: open the IDE's
  **Ports panel** and use whatever URL/port it's forwarding *right now*
  (it's very likely different from the tab you had open) instead of
  reloading the stale one.
- Hardened anyway, for a *different* failure mode that **is** within the
  app's control — a slow or unreachable Duke endpoint hanging the
  request instead of failing fast: `auth/oidc.py` now sets a 10s
  `default_timeout` on every Duke network call (discovery fetch, token
  exchange), and `login()`'s `client.authorize_redirect(...)` call —
  previously unguarded — now catches any exception and returns a clean
  `502` instead of an unhandled `500`.
- **Verified the public (signed-out) site is never gated on auth
  completing**, including while a login attempt is slow or actively
  failing: fired a real concurrent request to `/scans` while
  `/auth/login` was mid-flight against the live container (65ms vs.
  166ms, no serialization), and a controlled in-process test with a
  1s artificial delay on the Duke call shows the same
  (`test_public_page_not_blocked_while_login_is_still_in_flight`). This
  was already true — `flask run`'s dev server is threaded by default in
  Flask 3.x — but it's now asserted by a test so it can't silently
  regress.

**Recurred (same day) with a different browser (Chrome, not just Safari) —
ruling out browser-specific privacy features.** `ERR_EMPTY_RESPONSE` (Chrome's
error) specifically means a TCP connection was accepted and then closed with
no bytes sent back — different from a refused/blocked connection, and
identical across two browsers with unrelated security implementations. Four
separate incidents' container logs were read end to end (timestamps,
`OOMKilled`, exit codes) and every one shows the same shape: the initial
`/auth/login` served correctly, the container stayed alive and kept serving
*other* requests successfully seconds to minutes later (`GET /` → 200 in every
case), and it never logged the callback request at all. Every container exit
observed was `137`/no error/`OOMKilled: false` — i.e. something (usually the
user restarting) killed it, not a crash. None of that is explainable by
anything in this app's Python process; the request the browser reports
failing never reached it.

Ruled out or fixed along the way (all now covered by
`unit_tests/test_https_proxy.py`):
- Response headers checked clean — no `Strict-Transport-Security`, no
  `upgrade-insecure-requests`; nothing here nudges a browser toward HTTPS.
- Real found-and-fixed bug: reaching the app on the dev box's **LAN IP**
  directly (e.g. `http://10.x.x.x:5000/`, bypassing IDE port-forwarding
  entirely) computed an `https://` redirect_uri — this server never speaks
  TLS, so that path was silently broken. `_is_private_host()` now treats any
  RFC1918-private IP the same as loopback (verified against the live Duke
  discovery endpoint too — it accepts a LAN-IP redirect_uri the same way it
  accepts a loopback one).

**Confirmed 2026-07-01, from Duke's own server — the LAN-IP suggestion above
was wrong, and here's the exact reason why.** Testing the LAN IP produced a
Duke-hosted `invalid_grant` error page (MITREid Connect, the stack Duke runs):

```
Invalid redirect: http://10.236.144.14:5000/login does not match one of the
registered values: [http://localhost:5000/login,
https://model-advisor.colab.duke.edu/login]
```

That's the **exact, complete registered redirect_uri allowlist** for the
`codeplus-model-advisor` client — a raw IP was never going to work no matter
what this app computes, since Duke's server rejects it outright before ever
generating a code. `_is_private_host()` (the LAN-IP fix above) is still
correct to keep — it fixes a real bug (an unreachable `https://` URL on a
plain-HTTP dev server) — but it doesn't unblock login unless the DGX's LAN
IP is *also* added to that registered list on Duke's side. Not needed: see
below.

This also explains something that looked contradictory before: `localhost:5000`
is the *only* localhost entry registered — not a wildcard port — yet every
failed attempt used a different, unregistered port (59187, 61570, …, 64725)
and still got past Shibboleth and back to a real `?code=...&state=...` on
`localhost:<that port>`. Duke's server is evidently lenient about the port
specifically for the `localhost` hostname (the RFC 8252 §7.3 "loopback
native app" pattern — common for OAuth providers, and *not* extended to a
raw IP like `10.x.x.x`, which gets the strict-match rejection above instead).
So the OIDC exchange itself was completing correctly every time; the
callback never arriving was **still** purely about the browser reaching this
app's forwarded `localhost:<port>` for that one specific request — Cursor's
(the IDE in use here) auto-port-forwarder remains the prime suspect, now
with the OIDC-registration explanation fully ruled out.

**The fix: stop relying on the IDE's auto-forwarded (and constantly
reassigned) port. Use a fixed, stable port instead — ideally `5000`, since
that's the exact port already registered with Duke:**

```bash
# From the Mac — replace the host with the DGX's SSH target
ssh -L 5000:localhost:5000 <user>@<dgx-host>
```

Then browse `http://localhost:5000/` on the Mac. This is a dumb, boring,
well-understood TCP forward — no dynamic reassignment, no IDE-specific proxy
behavior — and it lands on exactly the redirect_uri Duke already has
registered, removing any remaining doubt about the loopback-port leniency
above. (If `5000` is taken locally on the Mac, `-L <anything>:localhost:5000`
still works — this app accepts and reflects back any `localhost:<port>`, as
established above — but starting with `5000:5000` is the cleanest test since
it's the one Duke is guaranteed to accept.) Alternative within the IDE
itself: in Cursor/VS Code's **Ports** panel, manually add a forward for port
`5000` rather than relying on auto-detection, which is the piece that keeps
reassigning to a new local port on each reconnect.

## Related code

- Run fingerprints: [`dbutils/run_fingerprint.py`](../dbutils/run_fingerprint.py)
- Launch reuse: [`frontend/run_launch.py`](../frontend/run_launch.py)
- DDL: [`db/auth_schema.sql`](../db/auth_schema.sql)
