import datetime
import logging
from typing import Dict

import requests

from bins import Bin, get_bin_from_api_id, get_bin_from_title, reconcile_bin_with_llm
from config import GAD_BASE_URL, require_gad_address


def get_next_bins() -> Dict[datetime.datetime, Bin]:
    return get_next_bins_api()


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
