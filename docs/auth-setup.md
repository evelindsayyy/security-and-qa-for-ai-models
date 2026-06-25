# Authentication setup

Operator guide for Duke OIDC on the application VM (`model-advisor.colab.duke.edu`). Code lives in [`auth/`](../auth/README.md).

**Model:** Public view needs no login. Private view and custom runs require an allowlisted Duke netID. Runs are deduplicated by config fingerprint in Postgres.

---

## Phase 1 — Deploy code (auth off)

Do this first on DGX or the VM before OIT registration.

```bash
cd security-and-qa-for-ai-models
uv sync --group dev
cp .env.example .env          # keep AUTH_ENABLED=0 for now
```

Apply auth DDL and backfill existing runs:

```bash
./scripts/apply-schemas.sh
# Dry-run backfill (prints counts, no writes):
uv run python db/migrate_auth_columns.py
# Commit backfill:
uv run python db/migrate_auth_columns.py --apply
```

Verify locally:

```bash
uv run python -m unittest discover -s unit_tests -q
uv run ruff check auth db dbutils/run_fingerprint.py dbutils/run_access.py
uv run python main.py --host &
sleep 2
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool
curl -s http://127.0.0.1:5000/auth/me | python3 -m json.tool
kill %1 2>/dev/null || true
```

Deploy to the VM with `AUTH_ENABLED=0`. Public UI should behave as before; header shows Public/Private toggle (Private prompts login once auth is on).

---

## Phase 2 — Register Duke OAuth client

You must complete this before setting `AUTH_ENABLED=1`. Duke requires a **Group Manager support group** before you can self-register an OAuth client ([OAuth FAQ](https://authentication.oit.duke.edu/manager/oauth/faq)).

**Timeline:** Support group approval can take several business days. Start Phase 2 as soon as Phase 1 is deployed — do not wait until you need login on production.

---

### Step 1: Create a Group Manager support group

A support group identifies who owns and maintains the OAuth client (rotate secrets, add redirect URIs, request MFA). OIT Identity Management must approve promotion from an ad hoc group to a **Support Group** ([Group Manager guide](https://iam.duke.edu/services/working-grouper-and-group-manager/)).

#### 1a. Check for an existing group

Ask your faculty lead or OIT sponsor whether Code+ / OIT already has a support group you can reuse (e.g. a broader “OIT Code+ applications” group). If yes, confirm you are listed as an **owner** or **member** — only members can register OAuth clients under that group.

#### 1b. Create the ad hoc group

1. Sign in to [Group Manager](https://groups.duke.edu) with your Duke NetID.
2. **Create group** → choose **Ad hoc** (name + description only).
3. Use these values (edit netIDs in the membership step):

| Field | Value |
|-------|--------|
| **Group display name** | `Code+ AI Model Security & QA — model-advisor` |
| **Description** | `Support group for the Code+ 2026 OIT project "Security & QA Tools for Duke's AI Models". Owns OAuth client registration and administration for the model-advisor nutrition-label web application at http://model-advisor.colab.duke.edu:5000 (scanning, safety, efficacy, and benchmark runs for Duke AI Gateway models). Faculty/staff co-owners: project faculty lead and student developers who will rotate credentials and update redirect URIs.` |

4. **Owners** — add at minimum:
   - Faculty lead / OIT sponsor (staff NetID)
   - One student developer who will register the OAuth client
   - Optional: second student co-owner for backup

5. **Members** — add everyone who may need to view or edit the OAuth client in [Authentication Manager](https://authentication.oit.duke.edu/manager/). Duke contacts should be **owners and members**; sponsored guests only as **members** ([third-party service support](https://iam.duke.edu/third-party-service-support/)).

6. Save the group and note the **Group ID** (Grouper stem/name shown in Group Manager — you will select this group when registering the OAuth client).

#### 1c. Request Support Group promotion

1. Open the group you just created in Group Manager.
2. Click **Request Support Group Promotion** (or equivalent promotion action on the group page).
3. In the promotion form, use text like:

   **Business purpose:**  
   `Register and maintain a Duke OAuth/OIDC client for the model-advisor web app (AI model security scanning, safety red-teaming, and efficacy evaluation UI). Authentication is used for private-mode access and custom run configuration; public catalog browsing does not require login.`

   **Application URL:**  
   `http://model-advisor.colab.duke.edu:5000`

   **Department / sponsor:**  
   `Duke Office of Information Technology — Code+ 2026`

4. Submit and wait for Identity Management approval (ServiceNow ticket may be created automatically). You cannot complete Step 2 until the group shows as a **Support Group**.

#### 1d. If promotion is blocked — open a ServiceNow ticket

Assignment group: **Identity Management-OIT** (or use [Authentication Manager help request](https://authentication.oit.duke.edu/manager/register)).

**Short description:** `Support group for Code+ model-advisor OAuth client`

**Description (paste and edit netIDs):**

```text
Please approve a Group Manager Support Group for OAuth client registration.

Project: Code+ 2026 — Security & QA Tools for Duke's AI Models
Application: model-advisor nutrition-label UI
Production URL: http://model-advisor.colab.duke.edu:5000
OAuth redirect URI (planned): http://model-advisor.colab.duke.edu:5000/auth/callback

Requested group display name:
  Code+ AI Model Security & QA — model-advisor

Purpose:
  Own OAuth client for Duke NetID login (OIDC authorization_code).
  Private mode for allowlisted developers; public mode remains open.

Requested owners (NetIDs):
  <faculty_netid>, <student1_netid>, <student2_netid>

We have created ad hoc group <group_id_if_known> and requested promotion, or need help creating the support group.
```

---

### Step 2: Register the OAuth client

After the support group is active:

1. Open [Authentication Manager — Register OAuth Client](https://authentication.oit.duke.edu/manager/oauth/faq) (link at top of the OAuth FAQ page).
2. Sign in with your Duke NetID. Select the **support group** from Step 1 when prompted.
3. Fill in the client registration form:

| Field | Value |
|-------|--------|
| **Client name** (display) | `Model Advisor — AI Security & QA` |
| **Description** | `Flask web UI and JSON API for security scanning, inference safety testing, and efficacy evaluation of Duke AI Gateway models. Code+ 2026 / OIT internal tool. OIDC login required only for private view and custom run configs; public nutrition-label catalog does not require authentication.` |
| **Grant type** | `authorization_code` |
| **Redirect URI** | `http://model-advisor.colab.duke.edu:5000/auth/callback` |

   The redirect URI must match **exactly** (scheme, host, port, path). If the VM later moves to HTTPS or drops `:5000`, register a **new** redirect URI in Authentication Manager and update `DUKE_OIDC_REDIRECT_URI` in `.env`.

4. **Scopes:** enable **`openid`**, **`profile`**, **`email`**  
   - `openid` → `dukeNetID`, `dukeUniqueID`, `sub`  
   - `profile` → name, `dukePrimaryAffiliation`  
   - `email` → institutional email  

   Do **not** request `groups` scope unless you later move allowlisting to Grouper (out of scope today; app uses `AUTH_ALLOWED_NETIDS` in `.env`).

5. Review the [OAuth overview](https://authentication.oit.duke.edu/manager/documentation/oauth/overview.md) and [mobile development standard](https://authentication.oit.duke.edu/manager/oauth/faq) if OIT flags the client type.

6. Submit registration. Copy the **client ID** and **client secret** immediately — store only in the VM `.env`, never in git.

| Endpoint | URL |
|----------|-----|
| Discovery | `https://oauth.oit.duke.edu/oidc/.well-known/openid-configuration` |
| Authorize | `https://oauth.oit.duke.edu/oidc/authorize` |
| Token | `https://oauth.oit.duke.edu/oidc/token` |
| Userinfo | `https://oauth.oit.duke.edu/oidc/userinfo` |

---

### Step 3: Configure VM `.env`

On `model-advisor.colab.duke.edu`, edit `/home/vcm/security-and-qa-for-ai-models/.env`:

```bash
AUTH_ENABLED=1
SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_hex(32))">
DUKE_OIDC_CLIENT_ID=<from Authentication Manager>
DUKE_OIDC_CLIENT_SECRET=<from Authentication Manager>
DUKE_OIDC_REDIRECT_URI=http://model-advisor.colab.duke.edu:5000/auth/callback
AUTH_ALLOWED_NETIDS=yournetid,teammate1,teammate2
```

Restart the web container:

```bash
cd /home/vcm/security-and-qa-for-ai-models
./docker/run.sh up -d --build
```

---

## Phase 3 — Smoke test (production)

Run these in order after restart.

```bash
BASE=http://model-advisor.colab.duke.edu:5000

# 1. Health
curl -s "$BASE/api/health" | python3 -m json.tool

# 2. Public browse (no cookie)
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/scans"
# Expect: 200

# 3. Session (unauthenticated)
curl -s "$BASE/auth/me" | python3 -m json.tool
# Expect: authenticated false, view_mode public

# 4. Browser — manual
#    - Open $BASE/ — header shows Public | Private and Sign in
#    - Public: /scans, /safety, /eval-run list loads without login
#    - Click Private → Sign in → Duke login popup → returns signed in as <netID>
#    - /eval-run/new → custom questions form works in Private mode
#    - Start same public-default scan twice → second should reuse (no new subprocess)
```

If login fails with **redirect_uri mismatch**, the registered URI and `DUKE_OIDC_REDIRECT_URI` differ by even one character.

If login succeeds but private mode says **not authorized**, add your netID to `AUTH_ALLOWED_NETIDS` and restart the web container.

---

## Local development (no OIDC)

```bash
# .env
AUTH_ENABLED=0
AUTH_DEV_NETID=yournetid
AUTH_ALLOWED_NETIDS=yournetid
SECRET_KEY=dev-local-only
```

`AUTH_DEV_NETID` simulates a logged-in user for private-mode testing without Duke OAuth.

---

## Schema reference

Applied by `./scripts/apply-schemas.sh` (includes `db/auth_schema.sql`):

| Object | Purpose |
|--------|---------|
| `users` | netID rows upserted at login |
| `user_run_links` | Links users to canonical runs (owner / reused) |
| `*.visibility`, `*.config_fingerprint`, `*.owner_user_id` | On all four pillar run tables |

Migration: `uv run python db/migrate_auth_columns.py --apply`

When multiple historical runs share the same config, only the **newest** row per fingerprint gets `config_fingerprint` set (partial unique index). Older duplicates keep `config_json` but a null fingerprint — reuse still works via the canonical row.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Cannot register OAuth client | Support group approved in Group Manager? You are owner/member of that group? |
| `OIDC not configured` on login | `DUKE_OIDC_CLIENT_ID` set; restart web after `.env` change |
| Redirect loop / invalid state | Clock skew; clear cookies; retry |
| Private runs visible to others | Row `visibility` should be `private`; user must not share slug URLs for private runs |
| Dedup not working | Postgres reachable; `config_fingerprint` populated (`migrate_auth_columns.py --apply`) |
| `db_available: false` | `POSTGRES_DSN` + `./scripts/apply-schemas.sh` — unrelated to OIDC but required for reuse |

---

## Later (out of scope)

- Grouper / `groups` OAuth scope for colab-wide allowlist
- HTTPS reverse proxy (update redirect URI)
- Require login for all job POSTs (abuse hardening)
