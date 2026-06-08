import datetime
import locale
import logging
from typing import Dict, Optional

from bins import Bin
from gad import get_next_bins
from hue import set_light


FORMAT = '%(asctime)s %(levelname)s %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)
try:
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
except locale.Error:
    logging.warning('locale error!')


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


def main():
    next_bins = get_next_bins()
    logging.info(f"Next bins: {next_bins}")
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
