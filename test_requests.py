from main import Bin, get_next_bins_headless
import datetime
import pytest

# TODO: Add unittests
# This one I use to test that the webdriver works correctly inside the docker container


def main():
    next_bins = get_next_bins_headless()
    print(f"Next bins: {next_bins}")
    tomorrow = datetime.datetime.now().date() + datetime.timedelta(days=1)
    if not any(bin_type.date() == tomorrow for bin_type in next_bins):
        print("No bins to be picked up tomorrow")
    else:
        for trash_bin in next_bins:
            if trash_bin.date() == tomorrow:
                print(f"Tomorrow they are picking up the {next_bins[trash_bin]} bin")


if __name__ == '__main__':
    main()
