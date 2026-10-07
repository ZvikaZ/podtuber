import collections
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote, quote

from podtuber.audio_info import prefetch
from podtuber.cache import cache
from podtuber.lessons import Lesson, SeriesParser, clean_text, strip_rav_name
from podtuber.wordpress import WordPressSite

SITE = WordPressSite('https://meirtv.com')
SOURCE_NAME = 'ערוץ מאיר'
LOGO_URL = f'{SITE.url}/wp-content/uploads/2021/02/cropped-logo2-270x270.png'
CACHE_SECTION = 'meirtv:audio'
LESSON_FIELDS = 'id,date_gmt,link,title,shiurim-series,rabbis'
OTHER_LESSONS = 'שיעורים נוספים'  # the rav's lessons that aren't in a series of his
STUDY_DAYS = 'ימי עיון'  # his talks in study days and conventions, each of many rabbis
STUDY_DAY_SERIES = re.compile(r'עיון|כנס')  # 'יום עיון לפורים - התשעה', 'כנס תשובה מאהבה - התשסט'

# the api doesn't give a lesson's audio, only its page does
MP3_URL = re.compile(r'https?://mp3\.meirtv\.co\.il/[^"\'<>]+?\.mp3', re.IGNORECASE)


def get_series_parsers(url):
    """
    https://meirtv.com/rabbis/<rabbi>/ is a podcast per series of that rav, and his talks in study days (series of
    talks by many rabbis) and his other lessons as two more; https://meirtv.com/shiurim-series/<series>/ is that
    series alone.
    """
    kind, slug = unquote(urlparse(url).path).strip('/').split('/')[:2]
    if kind not in ('rabbis', 'shiurim-series'):
        raise ValueError(f'Expected a /rabbis/... or /shiurim-series/... page of {SITE.url}, not {url}')
    term = SITE.get_term(kind, slug)
    lessons = SITE.get_all('shiurim', {kind: term['id'], '_fields': LESSON_FIELDS})
    by_series = collections.defaultdict(list)
    for lesson in lessons:
        for series_id in lesson['shiurim-series'] or ([None] if kind == 'rabbis' else []):
            by_series[series_id].append(lesson)
    series = {s['id']: s for s in SITE.get_terms('shiurim-series', [s for s in by_series if s is not None])}
    ravs = {r['id']: r for r in SITE.get_terms('rabbis', {rav for lesson in lessons for rav in lesson['rabbis']})}
    # where the series is mostly others', the lesson's title says which series it's from
    title_prefix = {}
    if kind == 'rabbis':
        for series_id, series_lessons in list(by_series.items()):
            if series_id is not None and len(series_lessons) * 2 <= series[series_id]['count']:
                del by_series[series_id]
                name = clean_text(series[series_id]['name']).strip(' -')
                group = STUDY_DAYS if STUDY_DAY_SERIES.search(name) else None
                by_series[group] += series_lessons
                title_prefix.update({lesson['id']: name for lesson in series_lessons})

    SITE.find_audio(CACHE_SECTION, [lesson for series_lessons in by_series.values() for lesson in series_lessons],
                    audio_in_page)
    prefetch([lesson_audio_url(lesson) for series_lessons in by_series.values() for lesson in series_lessons
              if lesson_audio_url(lesson)])

    parsers = []
    for series_id, series_lessons in by_series.items():
        rav = ravs[collections.Counter(r for lesson in series_lessons for r in lesson['rabbis']).most_common(1)[0][0]]
        with_audio = [lesson for lesson in series_lessons if lesson_audio_url(lesson)]
        if not with_audio:
            continue
        if series_id is None:
            name, feed_id, website = OTHER_LESSONS, f'meirtv-rabbi-{term["id"]}-other', term['link']
        elif series_id == STUDY_DAYS:
            name, feed_id, website = STUDY_DAYS, f'meirtv-rabbi-{term["id"]}-study-days', term['link']
        else:
            name = strip_rav_name(clean_text(series[series_id]['name']), rav['name'])
            feed_id, website = f'meirtv-{series_id}', series[series_id]['link']
        parsers.append(SeriesParser(
            feed_id=feed_id,
            name=name.strip(' -'),  # the site's names often end with a dash: 'סוגיות בעין אי"ה -'
            rav_name=rav['name'],
            source_name=SOURCE_NAME,
            description=f'שיעורי {rav["name"]} בסדרה "{name.strip(" -")}", מתוך {SITE.url}',
            website=website,
            image=LOGO_URL,
            lessons=[Lesson(id=f'meirtv-{lesson["id"]}',
                            date=datetime.fromisoformat(lesson['date_gmt']).replace(tzinfo=timezone.utc),
                            # titles end with the rav's name: 'שלושה שאכלו כאחד | עין איה ברכות ג, א | הרב יוסף קלנר'
                            title=prefixed(title_prefix.get(lesson['id']),
                                           strip_rav_name(clean_text(lesson['title']['rendered']), rav['name'])),
                            link=lesson['link'],
                            audio_url=lesson_audio_url(lesson),
                            order=lesson['id'])
                     for lesson in with_audio],
        ))
    return parsers


def prefixed(prefix, title):
    return f'{prefix}: {title}' if prefix else title


def audio_in_page(page):
    match = MP3_URL.search(page)
    return match.group(0) if match else None


def lesson_audio_url(lesson):
    url = cache.section(CACHE_SECTION).get(str(lesson['id']))
    # older files' paths have spaces and the like: 'Kalner/0637/Idx 74114.mp3'
    return url and quote(url, safe=':/?&=%#')
