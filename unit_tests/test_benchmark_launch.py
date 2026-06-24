import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frontend.benchmark_launch import (  # noqa: E402
    HF_INFERENCE_BASE_URL,
    _custom_env,
    validate_base_url,
    validate_custom_model,
)


class TestValidateCustomModel(unittest.TestCase):
    def test_accepts_org_model(self) -> None:
        self.assertIsNone(validate_custom_model("Qwen/Qwen3-0.6B"))

    def test_accepts_single_name(self) -> None:
        self.assertIsNone(validate_custom_model("gpt2"))

    def test_rejects_empty(self) -> None:
        self.assertIsNotNone(validate_custom_model(""))

    def test_rejects_path_traversal(self) -> None:
        self.assertIsNotNone(validate_custom_model("../etc/passwd"))

    def test_rejects_leading_slash(self) -> None:
        self.assertIsNotNone(validate_custom_model("/Qwen/Qwen3-0.6B"))

    def test_rejects_too_long(self) -> None:
        self.assertIsNotNone(validate_custom_model("a/" + "b" * 300))


class TestValidateBaseUrl(unittest.TestCase):
    def test_accepts_localhost(self) -> None:
        self.assertIsNone(validate_base_url("http://127.0.0.1:8000/v1"))

    def test_accepts_localhost_name(self) -> None:
        self.assertIsNone(validate_base_url("http://localhost:8000/v1"))

    def test_accepts_private_ip(self) -> None:
        # DCC compute nodes live on the 10.0.0.0/8 private range.
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
        # 169.254.169.254 is the classic SSRF metadata target.
        self.assertIsNotNone(validate_base_url("http://169.254.169.254/latest"))

    def test_rejects_non_http_scheme(self) -> None:
        self.assertIsNotNone(validate_base_url("ftp://10.0.0.1/v1"))

    def test_rejects_empty(self) -> None:
        self.assertIsNotNone(validate_base_url(""))


class TestHostedProvider(unittest.TestCase):
    def test_accepts_hf_router(self) -> None:
        # The hosted "no-setup" path forces this exact URL.
        self.assertIsNone(validate_base_url(HF_INFERENCE_BASE_URL))

    def test_accepts_hf_router_host(self) -> None:
        self.assertIsNone(validate_base_url("https://router.huggingface.co/v1"))

    def test_rejects_hf_router_over_http(self) -> None:
        # Allowlisted host must still use https.
        self.assertIsNotNone(validate_base_url("http://router.huggingface.co/v1"))

    def test_still_rejects_other_huggingface_hosts(self) -> None:
        # Only the exact router host is allowlisted, not the whole domain.
        self.assertIsNotNone(validate_base_url("https://huggingface.co/v1"))


class TestCustomEnv(unittest.TestCase):
    def test_sets_all_base_url_aliases(self) -> None:
        env = _custom_env("http://10.0.0.1:8000/v1", "key123")
        # TruthfulQA reads TQA_BASE_URL first, so it must be set too.
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
