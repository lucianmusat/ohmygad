import os
import re
import time
import locale
import logging
import datetime
import schedule
import colorsys
from enum import Enum
from phue import Bridge
from typing import Dict
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver import FirefoxOptions


FORMAT = '%(asctime)s %(levelname)s %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)
locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')

ADDRESS = os.environ.get("ZIP_CODE")
assert ADDRESS, "Please set the ZIP_CODE environment variable"
BRIDGE_IP_ADDRESS = os.environ.get("BRIDGE_IP")
assert BRIDGE_IP_ADDRESS, "Please set the BRIDGE_IP environment variable"
LIGHT_NAME = "Glass Cabinet"
PURPLE_HUE = int(65535 * colorsys.rgb_to_hsv(0.5, 0, 0.5)[0])
CHECK_TIME = "18:30"


class Bin(Enum):
    PLASTIC = "plastic"
    PAPER = "papier"
    PLANTS = "groenten"
    REST = "restafval"


color_map = {
    Bin.PLASTIC: 0,  # red
    Bin.PAPER: 46920,  # blue
    Bin.PLANTS: 25500,  # green
    Bin.REST: PURPLE_HUE,  # no color gray for hue lights, so let's pick purple
}


def get_next_bins_headless() -> Dict[datetime.datetime, Bin]:
    """
    Get the next bins to be picked up. Queries the gad.nl website for the next pickup dates
    using my address. Then parses the html to find the next dates and bin types.
    :return: A dictionary with the next dates as keys and the bin types as values
    """
    next_bins = {}
    assert ADDRESS, "Please set the ZIP_CODE environment variable"
    url = f"https://inzamelkalender.gad.nl/adres/{ADDRESS}"

    opts = FirefoxOptions()
    opts.add_argument("--headless")
    # Not using `with webdriver.Firefox()` because it does not work well on my Raspberry Pi
    driver = webdriver.Firefox(options=opts)
    try:
        # Another weird thing they did, they don't use the url argument anymore for the address,
        # they use local storage every time. So I need to set the local storage data before
        # navigating to the URL.
        driver.get("https://inzamelkalender.gad.nl")
        local_storage_data = {
            "bagid": "0402200001536008",
            "postcode": ADDRESS,
            "huisnummer": 4,
            "huisletter": "",
            "toevoeging": "",
            # "description": "",
            # "straat": "",
            # "woonplaats": "",
            "woonplaatsId": 1036,
            "gemeenteId": 402,
            "latitude": 52.232241,
            "longitude": 5.188504
        }
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
            date_obj = (datetime.datetime.strptime(date_str, '%a %d %b')
                        .replace(year=datetime.datetime.now().year))
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
    }
    pattern = re.compile('|'.join(map(re.escape, invalid_date_keywords.keys())), re.IGNORECASE)
    return pattern.sub(lambda x: invalid_date_keywords[x.group().lower()], date_str)


def get_bin_from_title(title: str) -> Bin:
    """
    Get the bin type from the title string.
    :param title: String containing the bin type parsed from the website
    :return: Bin object type
    """
    bin_obj = None
    for bin_type in Bin:
        if bin_type.value in title.lower():
            bin_obj = bin_type
    return bin_obj


def connect_to_bridge() -> Bridge:
    """
    Connect to the bridge. If the phue.conf file does not exist, the bridge needs to do a handshake.
    :return: The bridge object
    """
    # Need to press the button on the bridge to connect for the first time
    if not os.path.exists(os.path.expanduser('~/.python_hue')):
        logging.info("Press the button on the bridge to connect (30s)...")
        time.sleep(30)
        bridge = Bridge(BRIDGE_IP_ADDRESS)
        bridge.connect()
    else:
        bridge = Bridge(BRIDGE_IP_ADDRESS)
    return bridge


def set_light(bin_type: Bin) -> None:
    """
    Set the light to the color of the bin type.
    :param bin_type: The type of bin to be picked up so
    that the color of the light matches the color of the bin.
    """
    bridge = connect_to_bridge()
    light_id = int(bridge.get_light_id_by_name(LIGHT_NAME))
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
    next_bins = get_next_bins_headless()
    tomorrow = datetime.datetime.now().date() + datetime.timedelta(days=1)
    if not any(bin_type.date() == tomorrow for bin_type in next_bins):
        logging.info("No bins to be picked up tomorrow")
    else:
        for trash_bin in next_bins:
            if trash_bin.date() == tomorrow:
                logging.info(f"Tomorrow they are picking up the {next_bins[trash_bin]} bin")
                set_light(next_bins[trash_bin])


if __name__ == "__main__":
    logging.info("Starting ohMygGAD!")
    schedule.every().day.at(CHECK_TIME, "Europe/Amsterdam").do(main)
    while True:
        schedule.run_pending()
        time.sleep(60)
