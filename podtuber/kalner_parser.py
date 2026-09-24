import hashlib
import logging
import re
import time
import warnings
from datetime import datetime, timedelta
from functools import cache
from urllib.parse import urlparse, parse_qs, quote_plus

from curl_cffi import requests
from podgen import Person, Media

logger = logging.getLogger(__name__)

SITE_URL = 'https://www.haravyosefkalner.com'
RAV_NAME = 'הרב יוסף קלנר'
LOGO_URL = 'https://static.wixstatic.com/media/413a82_75d0cb10c9e64693a764d1b6a372e49a~mv2.png'

# the site's lessons live in a public Wix Data collection, queried the same way the site's own pages do
WIX_CODE_APP_ID = '675bbcef-18d8-41f5-800e-131ec9e08762'
COLLECTION = 'dropbox_audio_files_db'
PAGE_SIZE = 1000


@cache
def fetch_all_items():
    # Wix answers 429 to Python's own TLS stack, so impersonate a browser
    session = requests.Session(impersonate='chrome')
    tokens = session.get(f'{SITE_URL}/_api/v1/access-tokens').json()
    instance = tokens['apps'][WIX_CODE_APP_ID]['instance']

    items = []
    while True:
        response = session.post(f'{SITE_URL}/_api/cloud-data/v2/items/query',
                                headers={'Authorization': instance},
                                json={'dataCollectionId': COLLECTION,
                                      'query': {'paging': {'limit': PAGE_SIZE, 'offset': len(items)}}})
        response.raise_for_status()
        page = [data_item['data'] for data_item in response.json()['dataItems']]
        items += page
        if len(page) < PAGE_SIZE:
            break
        time.sleep(2)  # be gentle, Wix rate-limits
    logger.info(f'Fetched {len(items)} lessons from {SITE_URL}')
    return items


def get_series_parsers(url):
    """A URL with ?sidra=... is a single series; the site's root (or /shiurim) means all of them."""
    items = fetch_all_items()
    wanted = parse_qs(urlparse(url).query).get('sidra')
    subjects = sorted({item['subject'] for item in items})
    if wanted:
        if wanted[0] not in subjects:
            raise ValueError(f"Unknown series '{wanted[0]}' in {url}")
        subjects = wanted
    return [KalnerSeriesParser(subject, [item for item in items if item['subject'] == subject])
            for subject in subjects]


class LessonParser:
    def __init__(self, item, publication_date):
        self.item = item
        self.publication_date = publication_date

    def check_availability(self):
        if not self.item.get('audiosource'):
            raise ValueError('missing audio source')

    def get_title(self):
        return clean_title(self.item)

    def get_summary(self):
        keywords = self.item.get('keywords') or ''
        if isinstance(keywords, list):
            keywords = ', '.join(keywords)
        return '\n'.join(part for part in (self.item.get('date'), keywords) if part)

    def get_publication_date(self):
        return self.publication_date

    def get_explicit(self):
        return False

    def get_media(self, base_url, series_title):
        # raw=1 makes Dropbox serve audio/mpeg inline, rather than a dl=1 attachment download
        url = re.sub(r'\bdl=1\b', 'raw=1', self.item['audiosource'])
        with warnings.catch_warnings():
            # the size is optional for podcast apps, and not worth a request per lesson on every run
            warnings.filterwarnings('ignore', message='Size is set to 0')
            return Media(url=url, type='audio/mpeg')

    def get_id(self):
        return self.item['_id']

    def get_link(self):
        return f'{SITE_URL}/specific-shiur/?id={self.item["_id"]}'

    def get_authors(self):
        return [Person(RAV_NAME)]


class KalnerSeriesParser:
    def __init__(self, subject, items):
        self.subject = subject
        self.items = sort_lessons(items)

    def get_name(self):
        return f'{self.subject} - הרב קלנר'

    def get_feed_id(self):
        # the rss filename must never change once subscribed, and Hebrew titles make awkward URLs
        return 'kalner-' + hashlib.sha1(self.subject.encode()).hexdigest()[:8]

    def get_description(self):
        return f'שיעורי {RAV_NAME} בסדרה "{self.subject}", מתוך {SITE_URL}'

    def get_website(self):
        return f'{SITE_URL}/shiurim?sidra={quote_plus(self.subject)}'

    def get_image(self):
        return LOGO_URL

    def get_authors(self):
        return [Person(RAV_NAME)]

    def get_owner_name(self):
        return RAV_NAME

    def get_episodes(self):
        for item, publication_date in zip(self.items, monotonic_dates(self.items)):
            yield LessonParser(item, publication_date)


def clean_title(item):
    """
    Filenames look like 'אגרת עא (בני דוד התשפב)__033__התשפג_שבט_ל' (series, lesson number, reversed date),
    or are free text such as 'הרב קלנר – מה עניינן של ארבע האמהות – כג חשוון התשפו'.
    """
    filename = item['filename']
    if '__' not in filename:
        return filename.replace('_', ' ').strip()
    prefix, *rest = filename.split('__')
    number = rest.pop(0) if len(rest) > 1 and rest[0].isdigit() else None
    if not number and (match := re.search(r'\s(\d+)$', prefix)):  # e.g. 'אורות ארץ ישראל 3__...'
        number = match.group(1)
    label = clean_date(item.get('date') or '__'.join(rest))
    return f'{int(number)}. {label}' if number else label


def clean_date(date):
    # dates inside filenames (and sometimes in the date field) are reversed: 'התשפב_טבת_טו'
    return ' '.join(reversed(date.split('_'))).strip() if '_' in date else date


LESSON_NUMBER_PATTERNS = [
    r'__(\d+)__',            # 'אגרת עא (בני דוד התשפב)__033__...'
    r'\[(?:שיעור )?(\d+)\]',  # 'עבודת אלוקים [10]', 'נחמת ישראל [שיעור 01]'
    r'^(\d+)\b',             # '56 נס - הופעת המציאות'
    r'\s(\d+)(?:__|\b)',      # 'מוסר אביך 01 -מעין הקדמה', 'אורות ארץ ישראל 3__...'
]


def lesson_number(item):
    for pattern in LESSON_NUMBER_PATTERNS:
        if match := re.search(pattern, item['filename']):
            return int(match.group(1))
    return None


def upload_date(item):
    # whole seconds, as that's all an RSS date can express
    return datetime.fromisoformat(item['_createdDate']['$date'].replace('Z', '+00:00')).replace(microsecond=0)


def monotonic_dates(items):
    """
    Podcast apps order episodes by date, not by their order in the feed. Keep the upload dates, but push each one
    just past its predecessor's, so lessons reordered by number keep that order.
    """
    dates = []
    for item in items:
        date = upload_date(item)
        if dates and date <= dates[-1]:
            date = dates[-1] + timedelta(minutes=1)
        dates.append(date)
    return dates


def sort_lessons(items):
    """
    Upload time follows the series order for lessons uploaded one by one, but series that were uploaded in bulk
    went up in string order ('[1]', '[10]', '[11]', '[2]'...). So when every lesson is numbered, trust the numbers.
    """
    by_upload = sorted(items, key=lambda item: item['_createdDate']['$date'])  # ISO strings, full precision
    numbers = [lesson_number(item) for item in by_upload]
    if None in numbers:
        return by_upload
    return sorted(by_upload, key=lesson_number)  # stable, so equal numbers keep their upload order
