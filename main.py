import requests
import datetime
import locale
from bs4 import BeautifulSoup

locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')

ADDRESS = "1221CC:4"
bin_types = [
    "plastic",
    "papier",
    "groenten",
    "restafval",
]


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
            for bin_type in bin_types:
                if bin_type in next_dates_list[index + 1].lower():
                    next_bins[next_date] = bin_type
        except ValueError:
            continue
    return next_bins


def main():
    next_bins = get_next_bins()
    for trash_bin in next_bins:
        if trash_bin.date() == datetime.datetime.now().date():
            print(f"Today they are picking up the {next_bins[trash_bin]} bin")


if __name__ == "__main__":
    main()
