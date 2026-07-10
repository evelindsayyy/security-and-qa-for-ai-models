"""Tests for frontend.run_launch.build_launch_plan's visibility gating."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("AUTH_ENABLED", "0")

from frontend import create_app
from frontend.run_launch import build_launch_plan


class BuildLaunchPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        patcher = mock.patch("frontend.run_launch.try_lookup_reusable", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _plan(self, *, view_mode: str, user: dict | None, **kwargs):
        with self.app.test_request_context("/"):
            from flask import session

            session["view_mode"] = view_mode
            if user is not None:
                session["user"] = user
            return build_launch_plan("scan", hf_repo="gpt2", **kwargs)

    def test_private_mode_default_config_resolves_private_for_logged_in_user(self) -> None:
        plan = self._plan(view_mode="private", user={"id": "u1", "netid": "u1"})
        self.assertEqual(plan.visibility, "private")
        self.assertEqual(plan.owner_user_id, "u1")

    def test_public_mode_default_config_resolves_public(self) -> None:
        plan = self._plan(view_mode="public", user={"id": "u1", "netid": "u1"})
        self.assertEqual(plan.visibility, "public")
        self.assertIsNone(plan.owner_user_id)

    def test_public_mode_nondefault_config_downgrades_to_private(self) -> None:
        plan = self._plan(
            view_mode="public", user={"id": "u1", "netid": "u1"}, skip_modelscan=True
        )
        self.assertEqual(plan.visibility, "private")
        self.assertEqual(plan.owner_user_id, "u1")

    def test_private_mode_with_no_signed_in_user_falls_back_to_public(self) -> None:
        # A stale "private" toggle with no session user must never write an
        # ownerless (and therefore permanently invisible) private artifact.
        plan = self._plan(view_mode="private", user=None)
        self.assertEqual(plan.visibility, "public")
        self.assertIsNone(plan.owner_user_id)

    def test_launch_plan_has_no_is_public_default_field(self) -> None:
        plan = self._plan(view_mode="public", user=None)
        self.assertFalse(hasattr(plan, "is_public_default"))


if __name__ == "__main__":
    unittest.main()
