# HF weights (gitignored)

Populated by `python -m scanner scan <repo_id>`. Large files stay on DGX — not pushed to git.

Example: `scanner/models/gpt2/pytorch_model.bin`

**Supply-chain calibration (local, not on Hub):** `scan-test--supply-chain-demo/` — gpt2 weights + `requirements.txt` (pillow/urllib3 pins) + `credentials.env` (TruffleHog test patterns). Rescan: `python -m scanner scan scan-test/supply-chain-demo --no-download`.

Not repo-root [`models/`](../../models/) (gateway catalog).
