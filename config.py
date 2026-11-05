import os


GAD_BASE_URL = "https://inzamelkalender.gad.nl"
ZIP_CODE = os.environ.get("ZIP_CODE")
GAD_BAG_ID = os.environ.get("GAD_BAG_ID")
HOUSE_NUMBER = os.environ.get("HOUSE_NUMBER")

BRIDGE_IP_ADDRESS = os.environ.get("BRIDGE_IP")
LIGHT_NAMES = ["Livingroom spot 1", "Livingroom spot 2"]

# The Kottos Ollama keeps one chat model loaded for OpenClaw and informatica.
# Asking for the same model with the same load options (context size, shift)
# reuses it; anything else makes Ollama evict it and load another model.
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5:9b-q4_K_M")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama.default.svc.cluster.local:11434")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
# "-1m" = never unload; a bare "-1" is rejected by Ollama 0.40.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "-1m")
# Generous: if the model is not loaded, the first request waits for a cold load.
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))


def require_env(name: str, value: str):
    assert value, f"Please set the {name} environment variable"
    return value


def require_gad_address():
    return (
        require_env("ZIP_CODE", ZIP_CODE),
        require_env("GAD_BAG_ID", GAD_BAG_ID),
        require_env("HOUSE_NUMBER", HOUSE_NUMBER),
    )
