"""
Freeze guard — the Week-7 Day-4 FREEZE enforcement.

Every artifact in evaluator/frozen_contract.yaml is pinned to a SHA-256. After the
freeze, editing a frozen suite / rubric / prompt / schema changes its hash and
fails here — which forces new content into a NEW versioned file instead of an
in-place edit, preserving score comparability across runs.

Legitimately evolving the contract = add a new versioned file, then add it to the
manifest in a follow-up freeze (the existing entries stay pinned).

Run from repo root:
  uv run python -m unittest unit_tests.test_contract_freeze -v
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

import yaml

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
MANIFEST = _EVALUATOR / "frozen_contract.yaml"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ContractFreezeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        self.artifacts = self.manifest["artifacts"]

    def test_manifest_present_and_counted(self) -> None:
        self.assertTrue(self.artifacts, "no frozen artifacts in manifest")
        self.assertEqual(len(self.artifacts), self.manifest["artifact_count"])

    def test_every_frozen_artifact_unchanged(self) -> None:
        for rel, locked in self.artifacts.items():
            with self.subTest(artifact=rel):
                p = _EVALUATOR / rel
                self.assertTrue(p.is_file(), f"frozen artifact missing: {rel}")
                self.assertEqual(
                    _sha(p), locked,
                    f"\nFROZEN CONTRACT VIOLATION: {rel} changed since the W7 freeze.\n"
                    f"Do NOT edit frozen files — add a new versioned file instead.")

    def test_schema_version_matches_manifest(self) -> None:
        txt = (_EVALUATOR / "schemas.py").read_text(encoding="utf-8")
        m = re.search(r'SCHEMA_VERSION\s*=\s*"([^"]+)"', txt)
        self.assertIsNotNone(m, "SCHEMA_VERSION not found in schemas.py")
        self.assertEqual(m.group(1), self.manifest["schema_version"])


if __name__ == "__main__":
    unittest.main()
