import logging
import os
import time
from typing import Optional

import requests
from phue import Bridge

from bins import Bin, color_map
from config import BRIDGE_IP_ADDRESS, LIGHT_NAMES


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


def get_bridge_ip_address() -> str:
    if BRIDGE_IP_ADDRESS:
        return BRIDGE_IP_ADDRESS

    logging.info("BRIDGE_IP not set, attempting Hue bridge discovery...")
    try:
        ip_address = discover_bridge_ip()
        logging.info(f"Discovered Hue bridge at {ip_address}")
        return ip_address
    except Exception as e:
        raise AssertionError(f"Please set BRIDGE_IP or ensure discovery works: {e}")


def connect_to_bridge() -> Optional[Bridge]:
    """
    Connect to the bridge. If the phue.conf file does not exist, the bridge needs to do a handshake.
    :return: The bridge object
    """
    # Need to press the button on the bridge to connect for the first time
    try:
        bridge_ip_address = get_bridge_ip_address()
        if not os.path.exists(os.path.expanduser('~/.python_hue')):
            logging.info("Press the button on the bridge to connect (30s)...")
            time.sleep(30)
            bridge = Bridge(bridge_ip_address)
            bridge.connect()
        else:
            bridge = Bridge(bridge_ip_address)
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
