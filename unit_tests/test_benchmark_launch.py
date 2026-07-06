import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend.benchmark_launch import (  # noqa: E402
    HF_INFERENCE_BASE_URL,
    HOSTED_SAMPLE_MAX,
    RESULTS_DIR,
    _custom_env,
    _run_lock_path,
    validate_base_url,
    validate_custom_api_model,
    validate_custom_model,
    validate_hosted_model,
    validate_run_options,
)


class DeleteRouteLoginGateTest(unittest.TestCase):
    def setUp(self) -> None:
        env_patch = mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = create_app({"TESTING": True}).test_client()

    def test_delete_requires_login(self) -> None:
        r = self.client.get("/benchmarks/nonexistent-slug/delete")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/auth/login", r.headers["Location"])

    def test_private_detail_requires_login(self) -> None:
        r = self.client.get("/benchmarks/nonexistent-slug/private")
        self.assertIn(r.status_code, (302, 401, 403))

    def test_cancel_requires_login(self) -> None:
        r = self.client.post("/benchmarks/nonexistent-slug/cancel")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/auth/login", r.headers["Location"])


class TestRunLockPath(unittest.TestCase):
    def test_lock_is_flat_file_under_results(self) -> None:
        stem = "20260625T120000_truthfulqa_gpt-5-chat"
        path = _run_lock_path(stem)
        self.assertEqual(path, RESULTS_DIR / f"{stem}.run.lock")
        self.assertEqual(path.name, f"{stem}.run.lock")
        self.assertEqual(path.parent, RESULTS_DIR)


class TestValidateHostedModel(unittest.TestCase):
    def test_accepts_org_model(self) -> None:
        self.assertIsNone(validate_hosted_model("Qwen/Qwen3-0.6B"))

    def test_accepts_provider_pin(self) -> None:
        self.assertIsNone(validate_hosted_model("WeiboAI/VibeThinker-3B:novita"))

    def test_rejects_double_provider_pin(self) -> None:
        self.assertIsNotNone(validate_hosted_model("org/model:a:b"))


class TestValidateCustomApiModel(unittest.TestCase):
    def test_accepts_hf_style_id(self) -> None:
        self.assertIsNone(validate_custom_api_model("Qwen/Qwen3-0.6B"))

    def test_accepts_arbitrary_name(self) -> None:
        self.assertIsNone(validate_custom_api_model("my-finetune-v2"))
        self.assertIsNone(validate_custom_api_model("team-chat-v2"))

    def test_rejects_provider_pin(self) -> None:
        # ``:provider`` pins are for HF hosted routing, not custom APIs.
        self.assertIsNotNone(validate_custom_api_model("org/model:novita"))

    def test_rejects_empty(self) -> None:
        self.assertIsNotNone(validate_custom_api_model(""))

    def test_rejects_path_traversal(self) -> None:
        self.assertIsNotNone(validate_custom_api_model("../etc/passwd"))

    def test_alias_matches_custom_api(self) -> None:
        self.assertIsNone(validate_custom_model("gpt-4"))


class TestValidateBaseUrl(unittest.TestCase):
    def test_accepts_localhost(self) -> None:
        self.assertIsNone(validate_base_url("http://127.0.0.1:8000/v1"))

    def test_accepts_localhost_name(self) -> None:
        self.assertIsNone(validate_base_url("http://localhost:8000/v1"))

    def test_accepts_private_ip(self) -> None:
        self.assertIsNone(validate_base_url("http://10.183.23.44:8000/v1"))

    def test_accepts_bare_internal_hostname(self) -> None:
        self.assertIsNone(validate_base_url("http://dcc-plusds-gpu-02:8000/v1"))

    def test_accepts_duke_domain(self) -> None:
        self.assertIsNone(validate_base_url("https://node.oit.duke.edu:8000/v1"))

    def test_rejects_public_ip(self) -> None:
        self.assertIsNotNone(validate_base_url("http://8.8.8.8:8000/v1"))

    def test_rejects_public_domain(self) -> None:
        self.assertIsNotNone(validate_base_url("https://api.openai.com/v1"))

    def test_rejects_cloud_metadata_link_local(self) -> None:
        self.assertIsNotNone(validate_base_url("http://169.254.169.254/latest"))

    def test_rejects_non_http_scheme(self) -> None:
        self.assertIsNotNone(validate_base_url("ftp://10.0.0.1/v1"))

    def test_rejects_empty(self) -> None:
        self.assertIsNotNone(validate_base_url(""))


class TestHostedProvider(unittest.TestCase):
    def test_accepts_hf_router(self) -> None:
        self.assertIsNone(validate_base_url(HF_INFERENCE_BASE_URL))

    def test_accepts_hf_router_host(self) -> None:
        self.assertIsNone(validate_base_url("https://router.huggingface.co/v1"))

    def test_rejects_hf_router_over_http(self) -> None:
        self.assertIsNotNone(validate_base_url("http://router.huggingface.co/v1"))

    def test_still_rejects_other_huggingface_hosts(self) -> None:
        self.assertIsNotNone(validate_base_url("https://huggingface.co/v1"))


class TestValidateRunOptions(unittest.TestCase):
    def test_accepts_default_range(self) -> None:
        self.assertIsNone(validate_run_options("mmlu", 50, 42))

    def test_rejects_hosted_over_cap(self) -> None:
        err = validate_run_options("mmlu", HOSTED_SAMPLE_MAX + 1, None, hosted=True)
        self.assertIsNotNone(err)

    def test_rejects_seed_when_unsupported(self) -> None:
        self.assertIsNotNone(validate_run_options("tomi", 5, 42))


class TestCustomEnv(unittest.TestCase):
    def test_sets_all_base_url_aliases(self) -> None:
        env = _custom_env("http://10.0.0.1:8000/v1", "key123")
        self.assertEqual(env["TQA_BASE_URL"], "http://10.0.0.1:8000/v1")
        self.assertEqual(env["LITELLM_BASE_URL"], "http://10.0.0.1:8000/v1")
        self.assertEqual(env["OPENAI_BASE_URL"], "http://10.0.0.1:8000/v1")
        self.assertEqual(env["OPENAI_API_KEY"], "key123")
        self.assertEqual(env["LITELLM_API_KEY"], "key123")
        self.assertEqual(env["TQA_API_KEY"], "key123")

    def test_defaults_api_key(self) -> None:
        env = _custom_env("http://localhost:8000/v1", None)
        self.assertEqual(env["OPENAI_API_KEY"], "local-vllm")


if __name__ == "__main__":
    unittest.main()