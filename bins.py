import colorsys
import json
import logging
from enum import IntEnum
from typing import Optional

import requests

from config import LLM_MODEL, OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL


class Bin(IntEnum):
    REST = 1
    PLANTS = 2
    PAPER = 3
    PLASTIC = 4
    REST_PMD = 27

    @classmethod
    def from_api_id(cls, api_id) -> Optional["Bin"]:
        try:
            return cls(int(api_id))
        except (TypeError, ValueError):
            return None

    def __str__(self) -> str:
        return self.name.lower()


BIN_TITLE_ALIASES = (
    # More specific combined streams must be checked before generic PMD/rest labels.
    (Bin.REST_PMD, ("rest+pmd", "rest pmd", "rest-pmd", "rest en pmd")),
    (Bin.PLANTS, ("gfe+t", "gft", "groente", "groenten", "tuinafval", "etensresten", "groenafval")),
    (Bin.PAPER, ("papier", "karton")),
    (Bin.PLASTIC, ("verpakking van plastic", "plastic", "pmd", "blik", "drinkpakken")),
    (Bin.REST, ("restafval", "rest afval", "rest")),
)

PURPLE_HUE = int(65535 * colorsys.rgb_to_hsv(0.5, 0, 0.5)[0])

color_map = {
    Bin.PLASTIC: 0,  # red
    Bin.PAPER: 46920,  # blue
    Bin.PLANTS: 25500,  # green
    Bin.REST: PURPLE_HUE,  # no color gray for hue lights, so let's pick purple
    Bin.REST_PMD: PURPLE_HUE,
}


def get_bin_from_api_id(api_id) -> Optional[Bin]:
    return Bin.from_api_id(api_id)


def get_bin_from_title(title: str) -> Optional[Bin]:
    normalized_title = title.lower()
    for bin_type, aliases in BIN_TITLE_ALIASES:
        if any(alias in normalized_title for alias in aliases):
            return bin_type
    return None


def reconcile_bin_with_llm(title: Optional[str], api_id=None) -> Optional[Bin]:
    """
    Last-resort reconciliation through a local Ollama service. This is only used
    when GAD returns a stream that does not match known API IDs or aliases.
    """
    if not title and api_id is None:
        return None

    aliases = {
        bin_type.name: list(values)
        for bin_type, values in BIN_TITLE_ALIASES
    }
    prompt = f"""
Map a GAD Dutch waste stream to one of these enum names:
{json.dumps({bin_type.name: bin_type.value for bin_type in Bin}, indent=2)}

Known title aliases:
{json.dumps(aliases, indent=2, ensure_ascii=False)}

GAD returned:
api_id={api_id}
title={title!r}

Return only JSON in this exact shape:
{{"bin": "REST|PLANTS|PAPER|PLASTIC|REST_PMD|null"}}
"""
    try:
        response = requests.post(
            f"{OLLAMA_URL.rstrip('/')}/api/generate",
            json={
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        ollama_data = response.json()
        parsed = json.loads(ollama_data.get("response", "{}"))
    except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
        logging.warning(f"LLM reconciliation unavailable for {title!r}: {e}")
        return None

    bin_name = parsed.get("bin")
    if bin_name in Bin.__members__:
        logging.info(f"LLM reconciled GAD stream {title!r} to {bin_name}")
        return Bin[bin_name]
    return None
