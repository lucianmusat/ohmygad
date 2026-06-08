import datetime

def main():
    from gad import get_next_bins

    next_bins = get_next_bins()
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
