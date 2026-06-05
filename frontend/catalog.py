"""
canonical model ids for the draft frontend — keep in sync with docs/gateway-models.md.

gateway rows = duke litellm strings (safety + efficacy).
hf rows = hugging face repo ids (artifact scanning on dgx only).

week 5+: this list comes from postgres models table via api/, not a python list.
"""

# --- gateway (inference via duke ai gateway) ---

GATEWAY_MODELS = [
    {
        "id": "gpt-5-chat",
        "alias": "",
        "notes": "candidate in latest it_support eval run",
    },
    {
        "id": "gpt-5-mini",
        "alias": "",
        "notes": "good pilot tier — low cost",
    },
    {
        "id": "gpt-5-nano",
        "alias": "",
        "notes": "cheapest openai chat — smoke tier",
    },
    {
        "id": "GPT 4.1 Mini",
        "alias": "",
        "notes": "default smoke test (testing/test_gateway.py); confirm exact string with oit",
    },
    {
        "id": "Llama 3.3",
        "alias": "duke-llama33",
        "notes": "",
    },
    {
        "id": "Llama 4 Maverick",
        "alias": "",
        "notes": "judge model in latest it_support eval run",
    },
    {
        "id": "Llama 4 Scout",
        "alias": "",
        "notes": "low-cost llama pilot",
    },
    {
        "id": "GPT-OSS 120B",
        "alias": "",
        "notes": "open-weight style via cloud",
    },
    {
        "id": "gpt-5.4",
        "alias": "duke-gpt54",
        "notes": "truthfulqa pilot; confirm id with oit",
    },
]

# --- hugging face (artifact scanning — not gateway) ---

HF_SCAN_MODELS = [
    {
        "id": "gpt2",
        "slug": "gpt2",
        "notes": "calibration baseline — low/18 with benign fickling",
    },
    {
        "id": "distilbert-base-uncased",
        "slug": "distilbert-base-uncased",
        "notes": "default scanner regression",
    },
    {
        "id": "BAAI/bge-small-en-v1.5",
        "slug": "BAAI--bge-small-en-v1.5",
        "notes": "safetensors + pickle paths",
    },
    {
        "id": "google/flan-t5-small",
        "slug": "google--flan-t5-small",
        "notes": "org/model path layout",
    },
    {
        "id": "neimasilk/modelscan-extension-mismatch-poc",
        "slug": "neimasilk--modelscan-extension-mismatch-poc",
        "notes": "malicious poc — critical/95; modelaudit catches extensionless payload",
    },
]
