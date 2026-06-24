import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from model_client import (  # noqa: E402
    _fatal_error_hint,
    detect_provider,
    extract_choice_letter,
    normalize_model,
    strip_reasoning,
)


class TestModelClient(unittest.TestCase):
    def test_detect_huggingface_inference_host(self) -> None:
        self.assertEqual(
            detect_provider("https://api-inference.huggingface.co/v1"),
            "huggingface",
        )

    def test_normalize_huggingface_repo_id(self) -> None:
        self.assertEqual(
            normalize_model(
                "meta-llama/Llama-3.2-1B",
                "https://api-inference.huggingface.co/v1",
            ),
            "huggingface/meta-llama/Llama-3.2-1B",
        )

    def test_detect_hf_router_is_openai_compatible(self) -> None:
        # The Inference Providers router is OpenAI-compatible, not the HF TGI path.
        self.assertEqual(
            detect_provider("https://router.huggingface.co/v1"),
            "openai_compatible",
        )

    def test_normalize_hf_router_repo_id(self) -> None:
        self.assertEqual(
            normalize_model(
                "microsoft/Phi-4-mini-instruct",
                "https://router.huggingface.co/v1",
            ),
            "openai/microsoft/Phi-4-mini-instruct",
        )

    def test_normalize_local_vllm_repo_id(self) -> None:
        self.assertEqual(
            normalize_model(
                "Qwen/Qwen2.5-7B-Instruct",
                "http://127.0.0.1:8000/v1",
            ),
            "openai/Qwen/Qwen2.5-7B-Instruct",
        )

    def test_normalize_duke_display_name(self) -> None:
        self.assertEqual(
            normalize_model("GPT 4.1 Mini", "https://litellm.oit.duke.edu/v1"),
            "openai/GPT 4.1 Mini",
        )

    def test_preserve_existing_provider_prefix(self) -> None:
        model = "huggingface/gpt2"
        self.assertEqual(
            normalize_model(model, "https://api-inference.huggingface.co/v1"),
            model,
        )


class TestStripReasoning(unittest.TestCase):
    def test_removes_think_block(self) -> None:
        self.assertEqual(
            strip_reasoning("<think>let me reason about this</think>B"),
            "B",
        )

    def test_removes_unterminated_think(self) -> None:
        # Reasoning model truncated mid-thought, answer still trailing.
        self.assertEqual(
            strip_reasoning("<think>hmm the answer C").strip(),
            "hmm the answer C",
        )

    def test_passes_through_plain_text(self) -> None:
        self.assertEqual(strip_reasoning("The answer is D"), "The answer is D")

    def test_empty(self) -> None:
        self.assertEqual(strip_reasoning(""), "")


class TestExtractChoiceLetter(unittest.TestCase):
    def test_bare_letter(self) -> None:
        self.assertEqual(extract_choice_letter("B"), "B")

    def test_bare_letter_with_punctuation(self) -> None:
        self.assertEqual(extract_choice_letter("C."), "C")

    def test_answer_phrase(self) -> None:
        self.assertEqual(extract_choice_letter("The answer is D."), "D")

    def test_option_punctuation(self) -> None:
        self.assertEqual(extract_choice_letter("(A) seems correct"), "A")

    def test_ignores_letter_inside_word(self) -> None:
        # Old substring bug: "A" appears in "watermelon" but is not the answer.
        self.assertEqual(extract_choice_letter("You grow a watermelon"), "")

    def test_ignores_article_a(self) -> None:
        # Old uppercase bug: the article "a" became "A".
        self.assertEqual(extract_choice_letter("This is a tricky one"), "")

    def test_strips_reasoning_before_extracting(self) -> None:
        self.assertEqual(
            extract_choice_letter("<think>maybe A, maybe B</think>The answer is B"),
            "B",
        )

    def test_lowercase_single_letter(self) -> None:
        self.assertEqual(extract_choice_letter("b"), "B")

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(extract_choice_letter(""), "")


class TestFatalErrorHint(unittest.TestCase):
    def test_provider_unavailable(self) -> None:
        exc = Exception(
            "OpenAIException - The requested model 'x' is not supported by "
            "any provider you have enabled."
        )
        hint = _fatal_error_hint(exc)
        self.assertIsNotNone(hint)
        self.assertIn("org/model:provider", hint)

    def test_credits_depleted(self) -> None:
        exc = Exception(
            "Error code: 402 - {'error': 'You have depleted your monthly "
            "included credits.'}"
        )
        hint = _fatal_error_hint(exc)
        self.assertIsNotNone(hint)
        self.assertIn("credits", hint.lower())

    def test_transient_error_is_not_fatal(self) -> None:
        # A normal timeout should still go through the retry path.
        self.assertIsNone(_fatal_error_hint(Exception("Connection timed out")))


if __name__ == "__main__":
    unittest.main()
