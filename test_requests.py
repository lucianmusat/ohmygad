from main import Bin, get_next_bins_headless
import pytest

# TODO: Add unittests
# This one I use to test that the webdriver works correctly inside the docker container


def main():
    next_bins = get_next_bins_headless()
    print(f"Next bins: {next_bins}")


if __name__ == '__main__':
    main()
