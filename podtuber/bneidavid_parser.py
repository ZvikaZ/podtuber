import collections
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote, quote

from podtuber.audio_info import prefetch
from podtuber.cache import cache
from podtuber.lessons import Lesson, SeriesParser, clean_text, strip_rav_name
from podtuber.wordpress import WordPressSite

SITE = WordPressSite('https://bneidavid.org')
SOURCE_NAME = 'בני דוד'
LOGO_URL = f'{SITE.url}/wp-content/uploads/2020/01/logo.png'
CACHE_SECTION = 'bneidavid:audio'
LESSON_FIELDS = 'id,date_gmt,link,title,series,rav'

# the api doesn't give a lesson's audio, only its page does: either on the site's old media server,
# or a Google Drive file streamed through the site
MEDIA_LINE_URL = re.compile(r'https?://[\w.-]*media-line\.co\.il/[^"\'\s<>]+\.mp3', re.IGNORECASE)  # also .MP3
DRIVE_FILE_ID = re.compile(r'action=stream_audio&file_id=([\w-]+)')
STREAM_URL = f'{SITE.url}/wp-admin/admin-ajax.php?action=stream_audio&file_id={{}}'


def get_series_parsers(url):
    """
    https://bneidavid.org/rav/<rav>/ is a podcast per series of that rav (leaving out his guest lessons in others'
    series); https://bneidavid.org/series/<series>/ is that series alone.
    """
    kind, slug = unquote(urlparse(url).path).strip('/').split('/')[:2]
    if kind not in ('rav', 'series'):
        raise ValueError(f'Expected a /rav/... or /series/... page of {SITE.url}, not {url}')
    term = SITE.get_term(kind, slug)
    lessons = SITE.get_all('lessons', {kind: term['id'], '_fields': LESSON_FIELDS})
    by_series = collections.defaultdict(list)
    for lesson in lessons:
        for series_id in lesson['series']:
            by_series[series_id].append(lesson)
    series = {s['id']: s for s in SITE.get_terms('series', by_series)}
    ravs = {r['id']: r for r in SITE.get_terms('rav', {rav for lesson in lessons for rav in lesson['rav']})}
    if kind == 'rav':
        by_series = {series_id: series_lessons for series_id, series_lessons in by_series.items()
                     if len(series_lessons) * 2 > series[series_id]['count']}

    SITE.find_audio(CACHE_SECTION, [lesson for series_lessons in by_series.values() for lesson in series_lessons],
                    audio_in_page)
    prefetch([lesson_audio_url(lesson) for series_lessons in by_series.values() for lesson in series_lessons
              if lesson_audio_url(lesson)])

    parsers = []
    for series_id, series_lessons in sorted(by_series.items(), key=lambda item: series[item[0]]['name']):
        rav = ravs[collections.Counter(r for lesson in series_lessons for r in lesson['rav']).most_common(1)[0][0]]
        with_audio = [lesson for lesson in series_lessons if lesson_audio_url(lesson)]
        if with_audio:
            parsers.append(SeriesParser(
                feed_id=f'bneidavid-{series_id}',
                name=strip_rav_name(clean_text(series[series_id]['name']), rav['name']),
                rav_name=rav['name'],
                source_name=SOURCE_NAME,
                description=f'שיעורי {rav["name"]} בסדרה "{clean_text(series[series_id]["name"])}", מתוך {SITE.url}',
                website=series[series_id]['link'],
                image=LOGO_URL,
                lessons=[Lesson(id=f'bneidavid-{lesson["id"]}',
                                date=datetime.fromisoformat(lesson['date_gmt']).replace(tzinfo=timezone.utc),
                                title=clean_text(lesson['title']['rendered']),
                                link=lesson['link'],
                                audio_url=lesson_audio_url(lesson),
                                order=lesson['id'])
                         for lesson in with_audio],
                number_pattern=r'[\[{](\d+)\]',  # 'מאמר הדור [3]', or the odd typo, 'כוזרי {60]'
            ))
    return parsers


def audio_in_page(page):
    if match := DRIVE_FILE_ID.search(page):
        return STREAM_URL.format(match.group(1))
    if urls := MEDIA_LINE_URL.findall(page):
        # the same file is linked on an http host and on an https one
        return next((url for url in urls if url.startswith('https://')), urls[0])
    return None


def lesson_audio_url(lesson):
    url = cache.section(CACHE_SECTION).get(str(lesson['id']))
    # links on the old media server can have raw Hebrew (and direction marks) in their path
    return url and quote(url, safe=':/?&=%#')
