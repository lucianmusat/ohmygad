import os
import re
import time
import locale
import logging
import datetime
import colorsys
import json
from enum import IntEnum
from phue import Bridge
from typing import Dict, Optional
from bs4 import BeautifulSoup
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support import expected_conditions
from selenium.webdriver import FirefoxOptions


FORMAT = '%(asctime)s %(levelname)s %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)
try:
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
except locale.Error:
    logging.warning('locale error!')

ADDRESS = os.environ.get("ZIP_CODE")
assert ADDRESS, "Please set the ZIP_CODE environment variable"
BRIDGE_IP_ADDRESS = os.environ.get("BRIDGE_IP")
GAD_BASE_URL = "https://inzamelkalender.gad.nl"
GAD_BAG_ID = os.environ.get("GAD_BAG_ID")
assert GAD_BAG_ID, "Please set the GAD_BAG_ID environment variable"
HOUSE_NUMBER = os.environ.get("HOUSE_NUMBER")
assert HOUSE_NUMBER, "Please set the HOUSE_NUMBER environment variable"
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b-instruct")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama.default.svc.cluster.local:11434")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "3"))


def discover_bridge_ip() -> str:
    """Discover Hue Bridge IP using the official meethue discovery endpoint.
    Returns the first bridge IP found.
    """
    r = requests.get("https://discovery.meethue.com/", timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise RuntimeError("No Hue bridges returned by discovery")
    ip = data[0].get("internalipaddress")
    if not ip:
        raise RuntimeError("Discovery response missing internalipaddress")
    return ip

if not BRIDGE_IP_ADDRESS:
    logging.info("BRIDGE_IP not set, attempting Hue bridge discovery...")
    try:
        BRIDGE_IP_ADDRESS = discover_bridge_ip()
        logging.info(f"Discovered Hue bridge at {BRIDGE_IP_ADDRESS}")
    except Exception as e:
        raise AssertionError(f"Please set BRIDGE_IP or ensure discovery works: {e}")

LIGHT_NAMES = ["Livingroom spot 1", "Livingroom spot 2"]
PURPLE_HUE = int(65535 * colorsys.rgb_to_hsv(0.5, 0, 0.5)[0])
ORANGE_HUE = int(65535 * colorsys.rgb_to_hsv(1, 0.45, 0)[0])
CHECK_TIME = "16:30"


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


color_map = {
    Bin.PLASTIC: 0,  # red
    Bin.PAPER: 46920,  # blue
    Bin.PLANTS: 25500,  # green
    Bin.REST: PURPLE_HUE,  # no color gray for hue lights, so let's pick purple
    Bin.REST_PMD: PURPLE_HUE,
}

DUTCH_MONTHS = {
    'jan': 1, 'feb': 2, 'mrt': 3, 'apr': 4, 'mei': 5, 'jun': 6, 'juni': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12
}


def parse_dutch_date(date_str):
    parts = date_str.strip().lower().split()
    if len(parts) != 3:
        raise ValueError(f"Unexpected date format: {date_str}")
    _, day_str, month_str = parts
    day = int(day_str)
    month = DUTCH_MONTHS.get(month_str)
    if not month:
        raise ValueError(f"Unknown month abbreviation: {month_str}")
    year = datetime.datetime.now().year
    return datetime.datetime(year, month, day)


def get_next_bins() -> Dict[datetime.datetime, Bin]:
    next_bins = get_next_bins_api()
    if next_bins:
        return next_bins
    logging.warning("Falling back to the headless browser flow")
    return get_next_bins_headless()


def get_bins_for_date(next_bins: Dict[datetime.datetime, Bin], pickup_date: datetime.date):
    return [
        bin_type
        for pickup_datetime, bin_type in next_bins.items()
        if pickup_datetime.date() == pickup_date
    ]


def get_tomorrow_bins(
    next_bins: Dict[datetime.datetime, Bin],
    today: Optional[datetime.date] = None,
):
    today = today or datetime.datetime.now().date()
    tomorrow = today + datetime.timedelta(days=1)
    return get_bins_for_date(next_bins, tomorrow)


def get_next_bins_api() -> Dict[datetime.datetime, Bin]:
    """
    Get upcoming pickup dates from GAD's JSON endpoints. Prefer API IDs because
    GAD changes display labels more often than collection stream IDs.
    """
    next_bins = {}
    try:
        stream_titles = get_gad_stream_titles()
        response = requests.get(
            f"{GAD_BASE_URL}/rest/adressen/{GAD_BAG_ID}/ophaaldata",
            timeout=10,
        )
        response.raise_for_status()
        pickup_dates = response.json()
    except (requests.RequestException, ValueError) as e:
        logging.error(f"Could not load GAD pickup API: {e}")
        return next_bins

    for pickup in pickup_dates:
        try:
            date_obj = datetime.datetime.strptime(pickup["ophaaldatum"], "%Y-%m-%d")
        except (KeyError, ValueError):
            logging.error(f"Could not parse GAD pickup date from {pickup}")
            continue

        api_id = pickup.get("afvalstroom_id")
        title = stream_titles.get(api_id)
        bin_obj = get_bin_from_api_id(api_id)
        if not bin_obj and title:
            bin_obj = get_bin_from_title(title)
        if not bin_obj:
            bin_obj = reconcile_bin_with_llm(title=title, api_id=api_id)

        if bin_obj:
            next_bins[date_obj] = bin_obj
        else:
            logging.error(f"Could not match GAD stream id={api_id}, title={title!r}")
    return next_bins


def get_gad_stream_titles() -> Dict[int, str]:
    try:
        response = requests.get(
            f"{GAD_BASE_URL}/rest/adressen/{GAD_BAG_ID}/afvalstromen",
            timeout=10,
        )
        response.raise_for_status()
        streams = response.json()
    except (requests.RequestException, ValueError) as e:
        logging.warning(f"Could not load GAD stream titles: {e}")
        return {}

    titles = {}
    for stream in streams:
        api_id = stream.get("id")
        title = stream.get("title") or stream.get("menu_title")
        if api_id is not None and title:
            titles[int(api_id)] = title
    return titles


def optional_int_env(name: str) -> Optional[int]:
    value = os.environ.get(name)
    return int(value) if value else None


def optional_float_env(name: str) -> Optional[float]:
    value = os.environ.get(name)
    return float(value) if value else None


def build_gad_local_storage_data() -> Dict[str, object]:
    local_storage_data = {
        "bagid": GAD_BAG_ID,
        "postcode": ADDRESS,
        "huisnummer": int(HOUSE_NUMBER),
        "huisletter": os.environ.get("HOUSE_LETTER", ""),
        "toevoeging": os.environ.get("HOUSE_SUFFIX", ""),
    }
    optional_fields = {
        "woonplaatsId": optional_int_env("GAD_WOONPLAATS_ID"),
        "gemeenteId": optional_int_env("GAD_GEMEENTE_ID"),
        "latitude": optional_float_env("GAD_LATITUDE"),
        "longitude": optional_float_env("GAD_LONGITUDE"),
    }
    local_storage_data.update(
        {key: value for key, value in optional_fields.items() if value is not None}
    )
    return local_storage_data


def get_next_bins_headless() -> Dict[datetime.datetime, Bin]:
    """
    Get the next bins to be picked up. Queries the gad.nl website for the next pickup dates
    using my address. Then parses the html to find the next dates and bin types.
    :return: A dictionary with the next dates as keys and the bin types as values
    """
    next_bins = {}
    assert ADDRESS, "Please set the ZIP_CODE environment variable"
    url = f"{GAD_BASE_URL}/adres/{ADDRESS}"

    opts = FirefoxOptions()
    opts.add_argument("--headless")
    # Not using `with webdriver.Firefox()` because it does not work well on my Raspberry Pi
    driver = webdriver.Firefox(options=opts)
    try:
        # Another weird thing they did, they don't use the url argument anymore for the address,
        # they use local storage every time. So I need to set the local storage data before
        # navigating to the URL.
        driver.get(GAD_BASE_URL)
        local_storage_data = build_gad_local_storage_data()
        local_storage_script = f"""
                localStorage.setItem('zcalendarAdresWidget-data', JSON.stringify({local_storage_data}));
                """
        driver.execute_script(local_storage_script)

        driver.get(url)
        wait_to_load(driver)
        soup = BeautifulSoup(driver.page_source, features="html.parser")
        next_dates_div = soup.find('div', class_='list-group list-group-flush')
        if next_dates_div:
            next_bins = get_next_dates(next_dates_div)
        else:
            logging.error(f"Could not find next dates in {url}")
    except WebDriverException as e:
        logging.error(f"Could not load GAD website: {e}")
    finally:
        driver.quit()
    return next_bins


def get_next_dates(next_dates_div):
    next_bins = {}
    for a_tag in next_dates_div.find_all('a', class_='list-group-item'):
        title_str, date_str = extract_title_and_date(a_tag)
        if not title_str or not date_str:
            continue
        try:
            date_obj = parse_dutch_date(date_str)
        except ValueError:
            logging.error(f"Could not parse date '{date_str}'")
            continue
        bin_obj = get_bin_from_title(title_str)
        if bin_obj:
            next_bins[date_obj] = bin_obj
    return next_bins


def wait_to_load(driver):
    wait = WebDriverWait(driver, timeout=10)
    wait.until(expected_conditions.presence_of_element_located((By.CLASS_NAME, "list-group-flush")))


def extract_title_and_date(a_tag: BeautifulSoup) -> (str, str):
    title = a_tag.find('span', class_='z-title')
    date = a_tag.find('time', attrs={'datetime': 'afvalstroom.ophaaldatum'})
    if not title or not date:
        return None, None
    date_str = date.text.strip()
    title_str = title.text.strip()
    date_str = sanitize_date(date_str)
    logging.debug(f"Date '{date_str}' - Title '{title_str}'")
    return title_str, date_str


def sanitize_date(date_str: str) -> str:
    """
    Another trick from GAD to make the date string unparseable, they write the date
    in a non-standard Dutch way. This function should mitigate that.
    :param date_str: Parsed date string from the website
    :return: Sanitized date string that can be parsed by strptime
    """
    invalid_date_keywords = {
        "vandaag": datetime.datetime.now().strftime('%a %d %b'),
        "morgen": (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%a %d %b'),
        "maart": "mrt",
        "juli": "jul",
        "sept": "sep",
        "febr": "feb",
    }
    pattern = re.compile('|'.join(map(re.escape, invalid_date_keywords.keys())), re.IGNORECASE)
    return pattern.sub(lambda x: invalid_date_keywords[x.group().lower()], date_str)


def get_bin_from_api_id(api_id) -> Optional[Bin]:
    return Bin.from_api_id(api_id)


def get_bin_from_title(title: str) -> Optional[Bin]:
    """
    Get the bin type from the title string.
    :param title: String containing the bin type parsed from the website
    :return: Bin object type
    """
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


def connect_to_bridge() -> Optional[Bridge]:
    """
    Connect to the bridge. If the phue.conf file does not exist, the bridge needs to do a handshake.
    :return: The bridge object
    """
    # Need to press the button on the bridge to connect for the first time
    try:
        if not os.path.exists(os.path.expanduser('~/.python_hue')):
            logging.info("Press the button on the bridge to connect (30s)...")
            time.sleep(30)
            bridge = Bridge(BRIDGE_IP_ADDRESS)
            bridge.connect()
        else:
            bridge = Bridge(BRIDGE_IP_ADDRESS)
        return bridge
    except Exception as e:
        logging.error(f"Could not connect to bridge: {e}")
        return None


def set_light(bin_type: Bin):
    """
    Set the light to the color of the bin type.
    :param bin_type: The type of bin to be picked up so
    that the color of the light matches the color of the bin.
    """
    bridge = connect_to_bridge()
    if not bridge:
        return
    light_ids = [int(bridge.get_light_id_by_name(light_id)) for light_id in LIGHT_NAMES]
    for light_id in light_ids:
        light = bridge.get_light(light_id)
        if 'error' in str(light):
            logging.error(f"Light {light_id} is not found")
            return
        if not light['state']['reachable']:
            logging.error(f"Light {light_id} is not reachable or responsive")
        else:
            bridge.set_light(light_id, 'on', True)
            bridge.set_light(light_id, 'bri', 76)  # 30% of 255
            bridge.set_light(light_id, 'hue', color_map[bin_type])
            bridge.set_light(light_id, 'sat', 254)  # Maximum saturation


def main():
    next_bins = get_next_bins()
    tomorrow_bins = get_tomorrow_bins(next_bins)
    if not tomorrow_bins:
        logging.info("No bins to be picked up tomorrow")
    else:
        for trash_bin in tomorrow_bins:
            logging.info(f"Tomorrow they are picking up the {trash_bin} bin")
            set_light(trash_bin)


if __name__ == "__main__":
    logging.info("Starting ohMygGAD! (run-once)")
    main()
