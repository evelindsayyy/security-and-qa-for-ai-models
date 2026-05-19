# Architecture

## Backend

FastAPI on the RAPID VM. Endpoints:

- `POST /scan` — submits a SLURM job, returns `scan_id`
- `GET /scan/{id}` — status + results
- `GET /models` — all scanned models
- `GET /models/{id}` — detailed report

Postgres for persistence. SLURM jobs write results to shared storage; a small worker polls and updates Postgres.

## Frontend

Next.js + Tailwind. Three pages:

- Model list with risk scores and filtering
- Model detail with findings breakdown
- "Submit new scan" form taking an HF URL

Use Duke Shibboleth via VM config, or skip auth for the prototype and document it as future work.
