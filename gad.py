import datetime
import logging
import re
from typing import Dict

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver import FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from bins import Bin, get_bin_from_api_id, get_bin_from_title, reconcile_bin_with_llm
from config import (
    GAD_BASE_URL,
    HOUSE_LETTER,
    HOUSE_SUFFIX,
    optional_float_env,
    optional_int_env,
    require_gad_address,
)


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


def get_next_bins_api() -> Dict[datetime.datetime, Bin]:
    """
    Get upcoming pickup dates from GAD's JSON endpoints. Prefer API IDs because
    GAD changes display labels more often than collection stream IDs.
    """
    _, bag_id, _ = require_gad_address()
    next_bins = {}
    try:
        stream_titles = get_gad_stream_titles()
        response = requests.get(
            f"{GAD_BASE_URL}/rest/adressen/{bag_id}/ophaaldata",
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
        title = get_stream_title(stream_titles, api_id)
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
    _, bag_id, _ = require_gad_address()
    try:
        response = requests.get(
            f"{GAD_BASE_URL}/rest/adressen/{bag_id}/afvalstromen",
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


def get_stream_title(stream_titles: Dict[int, str], api_id):
    try:
        return stream_titles.get(int(api_id))
    except (TypeError, ValueError):
        return None


def build_gad_local_storage_data() -> Dict[str, object]:
    zip_code, bag_id, house_number = require_gad_address()
    local_storage_data = {
        "bagid": bag_id,
        "postcode": zip_code,
        "huisnummer": int(house_number),
        "huisletter": HOUSE_LETTER,
        "toevoeging": HOUSE_SUFFIX,
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
    zip_code, _, _ = require_gad_address()
    next_bins = {}
    url = f"{GAD_BASE_URL}/adres/{zip_code}"

    opts = FirefoxOptions()
    opts.add_argument("--headless")
    # Not using `with webdriver.Firefox()` because it does not work well on my Raspberry Pi
    driver = webdriver.Firefox(options=opts)
    try:
        # GAD reads address data from local storage, so seed it before opening the route.
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
