import os
import time
import locale
import logging
import requests
import datetime
import schedule
import colorsys
from enum import Enum
from phue import Bridge
from typing import Dict
from bs4 import BeautifulSoup

FORMAT = '%(asctime)s %(levelname)s %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)
locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')

ADDRESS = "1221CC:4"
BRIDGE_IP_ADDRESS = "192.168.50.11"
LIGHT_NAME = "Glass cabinet light"
PURPLE_HUE = int(65535 * colorsys.rgb_to_hsv(0.5, 0, 0.5)[0])


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


def get_next_bins() -> Dict[datetime.datetime, Bin]:
    """
    Get the next bins to be picked up. Queries the gad.nl website for the next pickup dates
    using my address. Then parses the html to find the next dates and bin types.
    :return: A dictionary with the next dates as keys and the bin types as values
    """
    next_bins = {}
    url = f"https://inzamelkalender.gad.nl/adres/{ADDRESS}"
    try:
        response = requests.get(url)
    except Exception as e:
        logging.error(f"Error while getting data from {url}: {e}")
        return next_bins
    data = BeautifulSoup(response.text, features="html.parser")
    next_dates = data.body.find('ul', attrs={'class': 'line', 'id': 'ophaaldata'})
    if not next_dates:
        logging.error(f"Could not find next dates in {url}")
        return next_bins
    next_dates = next_dates.text.strip()
    next_dates_list = [s for s in next_dates.splitlines(True) if s.strip("\r\n")]
    for index, line in enumerate(next_dates_list):
        try:
            next_date = datetime.datetime.strptime(line.strip(), '%a %d %b')
            next_date = next_date.replace(year=datetime.datetime.now().year)
            for bin_type in Bin:
                if str(bin_type.value) in next_dates_list[index + 1].lower():
                    next_bins[next_date] = bin_type
        except ValueError:
            continue
    return next_bins


def set_light(bin_type: Bin) -> None:
    """
    Set the light to the color of the bin type.
    :param bin_type: The type of bin to be picked up so
    that the color of the light matches the color of the bin.
    """
    bridge = Bridge(BRIDGE_IP_ADDRESS)
    # Need to press the button on the bridge to connect for the first time
    if not os.path.exists('phue.conf'):
        bridge.connect()
    light_id = int(bridge.get_light_id_by_name(LIGHT_NAME))
    light = bridge.get_light(light_id)
    if not light['state']['reachable']:
        logging.error(f"Light {light_id} is not reachable or responsive")
    else:
        bridge.set_light(light_id, 'on', True)
        bridge.set_light(light_id, 'bri', 76)  # 30% of 255
        bridge.set_light(light_id, 'hue', color_map[bin_type])
        bridge.set_light(light_id, 'sat', 254)  # Maximum saturation


def main():
    next_bins = get_next_bins()
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
    schedule.every().day.at("08:00").do(main)
    while True:
        schedule.run_pending()
        time.sleep(60)
