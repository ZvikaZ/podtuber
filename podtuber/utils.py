from urllib.parse import urlparse


def clean_jpg_url(url):
    return urlparse(url)._replace(query='').geturl()
