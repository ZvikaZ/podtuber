import collections
import html
import json
import logging
import re
import time
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote, urlencode, quote

from podgen import Person, Media
from pyluach.dates import HebrewDate

from podtuber.audio_info import audio_info, is_missing, media_details, prefetch
from podtuber.cache import cache
from podtuber.utils import monotonic_dates

logger = logging.getLogger(__name__)

SITE_URL = 'https://bneidavid.org'
API_URL = f'{SITE_URL}/wp-json/wp/v2'
SOURCE_NAME = 'בני דוד'
LOGO_URL = f'{SITE_URL}/wp-content/uploads/2020/01/logo.png'
USER_AGENT = 'Mozilla/5.0 (compatible; podtuber)'
LESSON_FIELDS = 'id,date_gmt,link,title,series,rav'

# the api doesn't give a lesson's audio, only its page does: either on the site's old media server,
# or a Google Drive file streamed through the site
MEDIA_LINE_URL = re.compile(r'https?://[\w.-]*media-line\.co\.il/[^"\'\s<>]+\.mp3', re.IGNORECASE)  # also .MP3
DRIVE_FILE_ID = re.compile(r'action=stream_audio&file_id=([\w-]+)')
STREAM_URL = f'{SITE_URL}/wp-admin/admin-ajax.php?action=stream_audio&file_id={{}}'


def get_series_parsers(url):
    """
    https://bneidavid.org/rav/<rav>/ is a podcast per series of that rav (leaving out his guest lessons in others'
    series); https://bneidavid.org/series/<series>/ is that series alone.
    """
    kind, slug = unquote(urlparse(url).path).strip('/').split('/')[:2]
    if kind not in ('rav', 'series'):
        raise ValueError(f'Expected a /rav/... or /series/... page of {SITE_URL}, not {url}')
    term = get_term(kind, slug)
    lessons = get_all('lessons', {kind: term['id'], '_fields': LESSON_FIELDS})
    by_series = collections.defaultdict(list)
    for lesson in lessons:
        for series_id in lesson['series']:
            by_series[series_id].append(lesson)
    series = {s['id']: s for s in get_terms('series', by_series)}
    ravs = {r['id']: r for r in get_terms('rav', {rav for lesson in lessons for rav in lesson['rav']})}
    if kind == 'rav':
        by_series = {series_id: series_lessons for series_id, series_lessons in by_series.items()
                     if len(series_lessons) * 2 > series[series_id]['count']}

    find_audio([lesson for series_lessons in by_series.values() for lesson in series_lessons])
    prefetch([lesson_audio_url(lesson) for series_lessons in by_series.values() for lesson in series_lessons
              if lesson_audio_url(lesson)])

    parsers = []
    for series_id, series_lessons in sorted(by_series.items(), key=lambda item: series[item[0]]['name']):
        rav = ravs[collections.Counter(r for lesson in series_lessons for r in lesson['rav']).most_common(1)[0][0]]
        with_audio = [lesson for lesson in series_lessons if lesson_audio_url(lesson)]
        if with_audio:
            parsers.append(BneiDavidSeriesParser(series[series_id], rav['name'], with_audio))
    return parsers


def api(path, params):
    request = urllib.request.Request(f'{API_URL}/{path}?{urlencode(params)}', headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response), int(response.headers.get('X-WP-TotalPages', 1))


def get_all(path, params):
    items, page, pages = [], 1, 1
    while page <= pages:
        data, pages = api(path, {**params, 'per_page': 100, 'page': page})
        items += data
        page += 1
    return items


def get_term(kind, slug):
    found, _ = api(kind, {'slug': slug})
    if not found:
        raise ValueError(f"No {kind} '{slug}' on {SITE_URL}")
    return found[0]


def get_terms(kind, ids):
    ids = sorted(ids)
    return [term for i in range(0, len(ids), 100)
            for term in get_all(kind, {'include': ','.join(map(str, ids[i:i + 100]))})]


def find_audio(lessons):
    """the audio url of each lesson not yet in the cache (None when it has none), read from its page"""
    audio = cache.section('bneidavid:audio')
    todo = [lesson for lesson in lessons if str(lesson['id']) not in audio]
    if todo:
        logger.info(f'Reading {len(todo)} lesson pages of {SITE_URL}')
    for n, lesson in enumerate(todo, 1):
        try:
            request = urllib.request.Request(lesson['link'], headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                page = html.unescape(response.read().decode('utf8'))
        except Exception as err:
            logger.warning(f"Couldn't read {lesson['link']} (will retry next time): {err}")
            continue
        if match := DRIVE_FILE_ID.search(page):
            audio[str(lesson['id'])] = STREAM_URL.format(match.group(1))
        elif urls := MEDIA_LINE_URL.findall(page):
            # the same file is linked on an http host and on an https one
            audio[str(lesson['id'])] = next((url for url in urls if url.startswith('https://')), urls[0])
        else:
            audio[str(lesson['id'])] = None
        if n % 50 == 0:
            logger.info(f'  {n} of {len(todo)}')
            cache.save()
        time.sleep(1)  # be gentle


def lesson_audio_url(lesson):
    url = cache.section('bneidavid:audio').get(str(lesson['id']))
    # links on the old media server can have raw Hebrew (and direction marks) in their path
    return url and quote(url, safe=':/?&=%#')


def lesson_date(lesson):
    return datetime.fromisoformat(lesson['date_gmt']).replace(tzinfo=timezone.utc)


def clean_text(text):
    # the site writes gershayim as two apostrophes: תשע''ז
    return ' '.join(html.unescape(text).replace("''", '"').split())


def lesson_number(lesson):
    """the lesson's number in its series, from titles like 'מאמר הדור [3]' (or the odd typo, 'כוזרי {60]')"""
    match = re.search(r'[\[{](\d+)\]', lesson['title']['rendered'])
    return int(match.group(1)) if match else None


def sort_lessons(lessons):
    """
    The site's dates sometimes swap neighbouring lessons, so when the series is (nearly all) numbered, sort by
    number: an unnumbered lesson stays after the one before it, and a typo'd repeated number keeps the date order.
    But many repeated numbers mean the numbering restarts within the series, and then only the dates make sense.
    """
    by_date = sorted(lessons, key=lambda lesson: (lesson['date_gmt'], lesson['id']))
    numbers = [lesson_number(lesson) for lesson in by_date]
    numbered = [number for number in numbers if number is not None]
    if len(numbered) < 0.9 * len(numbers) or len(numbered) - len(set(numbered)) > 0.1 * len(numbers):
        return by_date
    keys, previous = [], 0
    for number in numbers:
        previous = number if number is not None else previous
        keys.append(previous)
    return [lesson for _, _, lesson in sorted(zip(keys, range(len(by_date)), by_date))]


def clean_series_name(name, rav_name):
    """'כוזרי [תשע''ז] - הרב קלנר' -> 'כוזרי [תשע"ז]', as the rav's full name is added anyway"""
    last_name = rav_name.split()[-1]
    name = re.sub(rf'\s*[-|–]?\s*הרב\s+(?:\S+\s+)?{re.escape(last_name)}\b', '', clean_text(name))
    return name.strip(' -|–')


class LessonParser:
    def __init__(self, lesson, rav_name, publication_date):
        self.lesson = lesson
        self.rav_name = rav_name
        self.publication_date = publication_date

    def check_availability(self):
        if is_missing(lesson_audio_url(self.lesson)):
            raise ValueError('its audio file is missing')

    def get_title(self):
        return clean_text(self.lesson['title']['rendered'])

    def get_summary(self):
        return HebrewDate.from_pydate(lesson_date(self.lesson).date()).hebrew_date_string()

    def get_publication_date(self):
        return self.publication_date

    def get_explicit(self):
        return False

    def get_media(self, base_url, series_title):
        url = lesson_audio_url(self.lesson)
        return Media(url=url, type='audio/mpeg', **media_details(url))

    def get_id(self):
        return f'bneidavid-{self.lesson["id"]}'

    def get_link(self):
        return self.lesson['link']

    def get_authors(self):
        return [Person(self.rav_name)]


class BneiDavidSeriesParser:
    def __init__(self, series, rav_name, lessons):
        self.series = series
        self.rav_name = rav_name
        self.lessons = sort_lessons(lessons)

    def get_name(self):
        return f'{clean_series_name(self.series["name"], self.rav_name)} - {self.rav_name}'

    def get_feed_id(self):
        return f'bneidavid-{self.series["id"]}'

    def get_source_name(self):
        return SOURCE_NAME

    def get_recordings(self):
        return [(lesson_date(lesson).date(), (audio_info(lesson_audio_url(lesson)) or {}).get('duration'),
                 (audio_info(lesson_audio_url(lesson)) or {}).get('size'))
                for lesson in self.lessons]

    def get_description(self):
        return f'שיעורי {self.rav_name} בסדרה "{clean_text(self.series["name"])}", מתוך {SITE_URL}'

    def get_website(self):
        return self.series['link']

    def get_image(self):
        return LOGO_URL

    def get_authors(self):
        return [Person(self.rav_name)]

    def get_owner_name(self):
        return self.rav_name

    def get_episodes(self):
        dates = monotonic_dates([lesson_date(lesson).replace(microsecond=0) for lesson in self.lessons])
        for lesson, publication_date in zip(self.lessons, dates):
            yield LessonParser(lesson, self.rav_name, publication_date)
