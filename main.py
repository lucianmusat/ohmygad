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
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')

ADDRESS = "1221CC:4"
BRIDGE_IP_ADDRESS = "192.168.50.11"
LIGHT_NAME = "Glass cabinet light"
brown_rgb = (128, 128, 128)
brown_hsv = colorsys.rgb_to_hsv(*brown_rgb)
brown_hue = int(brown_hsv[0] * 65535)


class Bin(Enum):
    PLASTIC = "plastic",
    PAPER = "papier",
    PLANTS = "groenten",
    REST = "restafval"


color_map = {
    Bin.PLASTIC: 0,  # red
    Bin.PAPER: 46920,  # blue
    Bin.PLANTS: 25500,  # green
    Bin.REST: brown_hue,  # brown
}


def get_next_bins():
    next_bins = {}
    url = f"https://inzamelkalender.gad.nl/adres/{ADDRESS}"
    response = requests.get(url)
    data = BeautifulSoup(response.text, features="html.parser")
    next_dates = data.body.find('ul', attrs={'class': 'line', 'id': 'ophaaldata'}).text.strip()
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


def set_light(bin_type: Bin):
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
    today = datetime.datetime.now().date()
    if not any(bin_type.date() == today for bin_type in next_bins):
        logging.info("No bins to be picked up today")
    else:
        for trash_bin in next_bins:
            print(f"Bin date: {trash_bin.date()}, today: {today}")
            if trash_bin.date() == today:
                logging.info(f"Today they are picking up the {next_bins[trash_bin]} bin")
                set_light(next_bins[trash_bin])


if __name__ == "__main__":
    logging.info("Starting ohMygGAD!")
    schedule.every().day.at("08:00").do(main)
    while True:
        schedule.run_pending()
        time.sleep(60)