from datetime import timedelta
from urllib.parse import urlparse


def clean_jpg_url(url):
    return urlparse(url)._replace(query='').geturl()


def monotonic_dates(dates):
    """
    Podcast apps order episodes by date, not by their order in the feed. Keep the dates, but push each one just
    past its predecessor's, so episodes keep the order they're given in.
    """
    result = []
    for date in dates:
        if result and date <= result[-1]:
            date = result[-1] + timedelta(minutes=1)
        result.append(date)
    return result
