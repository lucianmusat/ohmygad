import os


GAD_BASE_URL = "https://inzamelkalender.gad.nl"
ZIP_CODE = os.environ.get("ZIP_CODE")
GAD_BAG_ID = os.environ.get("GAD_BAG_ID")
HOUSE_NUMBER = os.environ.get("HOUSE_NUMBER")

BRIDGE_IP_ADDRESS = os.environ.get("BRIDGE_IP")
LIGHT_NAMES = ["Livingroom spot 1", "Livingroom spot 2"]

LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b-instruct")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama.default.svc.cluster.local:11434")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "3"))


def require_env(name: str, value: str):
    assert value, f"Please set the {name} environment variable"
    return value


def require_gad_address():
    return (
        require_env("ZIP_CODE", ZIP_CODE),
        require_env("GAD_BAG_ID", GAD_BAG_ID),
        require_env("HOUSE_NUMBER", HOUSE_NUMBER),
    )
