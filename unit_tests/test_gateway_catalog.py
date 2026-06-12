"""Gateway catalog — annotations and categorization (no live API in default tests)."""

from __future__ import annotations

import unittest

from gateway import catalog


class GatewayNotesTest(unittest.TestCase):
    def test_known_models_have_explicit_annotations(self) -> None:
        """Every id we expect on the gateway today should have a curated note."""
        expected = {
            "GPT 4.1",
            "GPT 4.1 Mini",
            "GPT 4.1 Nano",
            "gpt-5-chat",
            "gpt-5-mini",
            "Llama 4 Maverick",
            "gpt-5-codex",
            "o4 Mini",
            "whisper-1",
            "text-embedding-3-small",
        }
        for mid in expected:
            self.assertIn(mid, catalog.ANNOTATIONS, mid)
            self.assertTrue(catalog.ANNOTATIONS[mid].strip(), mid)

    def test_all_live_models_have_notes(self) -> None:
        gw = catalog.get_gateway_catalog(force_refresh=True)
        if gw["error"]:
            self.skipTest(gw["error"])
        for m in gw["models"]:
            self.assertTrue(m["notes"].strip(), m["id"])

    def test_fallback_note_for_unknown_id(self) -> None:
        note = catalog._notes_for("brand-new-model-xyz", "general_chat")
        self.assertTrue(note.strip())


class GatewayCategorizeTest(unittest.TestCase):
    def test_categorize_samples(self) -> None:
        self.assertEqual(catalog._categorize("gpt-5-codex"), "codex")
        self.assertEqual(catalog._categorize("whisper-1"), "audio")
        self.assertEqual(catalog._categorize("text-embedding-3-small"), "embeddings")
        self.assertEqual(catalog._categorize("o4 Mini"), "research")
        self.assertEqual(catalog._categorize("GPT 4.1 Mini"), "general_chat")


if __name__ == "__main__":
    unittest.main()
