"""
Track A — Hugging Face artifact scanning (security pillar, pre-deploy).

This package downloads model repos from the Hub, runs defense-in-depth static
scanners (ModelScan, Fickling, ModelAudit), merges results in ``risk_scorer``,
and writes Postgres-ready JSON (``ScanResult``) under ``scanner/output/``.

Entry point: ``python -m scanner scan <HF_REPO_ID>`` (see ``__main__.py``).

Pipeline overview and calibration tables: ``scanner/README.md``.
Data shapes and future DB mapping: ``docs/data-model.md``.
"""

__version__ = "0.4.0"
