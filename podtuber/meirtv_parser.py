import collections
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlparse

from podtuber.audio_info import prefetch
from podtuber.cache import cache
from podtuber.lessons import (
    Lesson,
    SeriesParser,
    Topic,
    clean_text,
    strip_rav_name,
    topic_of,
)
from podtuber.wordpress import WordPressSite

# its firewall refuses GitHub's servers, so runs there use what a run elsewhere saved (see refresh-snapshots.sh)
SITE = WordPressSite('https://meirtv.com', snapshot='meirtv.json.gz', media_host='mp3.meirtv.co.il')
SOURCE_NAME = 'ערוץ מאיר'
LOGO_URL = f'{SITE.url}/wp-content/uploads/2021/02/cropped-logo2-270x270.png'
CACHE_SECTION = 'meirtv:audio'
LESSON_FIELDS = 'id,date_gmt,link,title,shiurim-series,rabbis'
OTHER_LESSONS = 'שיעורים נוספים'  # the rav's lessons that aren't in a series of his
STUDY_DAYS = 'ימי עיון'  # his talks in study days and conventions, each of many rabbis
STUDY_DAY_SERIES = re.compile(r'עיון|כנס')  # 'יום עיון לפורים - התשעה', 'כנס תשובה מאהבה - התשסט'
# since 2023, the site's slogan starts every title: 'ערוץ מאיר - מכון מאיר | מיטב התוכן מתעדכן יומי: נתיבות עולם...'
SLOGAN = re.compile(r'^ערוץ מאיר\s*-\s*מכון מאיר\s*\|\s*מיטב התוכן מתעדכן יומי:\s*')

# the api doesn't give a lesson's audio, only its page does
MP3_URL = re.compile(r'https?://mp3\.meirtv\.co\.il/[^"\'<>]+?\.mp3', re.IGNORECASE)


def get_series_parsers(url, rav_name=None, topics=(), splits=()):
    """
    https://meirtv.com/rabbis/<rabbi>/ is a podcast per series of that rav, and his talks in study days (series of
    talks by many rabbis) and his other lessons as two more; https://meirtv.com/shiurim-series/<series>/ is that
    series alone. rav_name, when given, is how the rav is named, rather than as the site names him; and topics, of
    his other lessons, are podcasts of their own, of the lessons whose titles name them (the first one named).
    splits are series too big for one podcast: {'series': its name, 'parts': [{'name': ..., 'words': [...]}, ...]},
    a podcast per part, of the lessons whose titles name one of its words (the first part named); a part with no
    words is the rest.
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
        own_series_lessons = {
            lesson['id']
            for series_id, series_lessons in by_series.items()
            if series_id is not None and len(series_lessons) * 2 > series[series_id]['count']
            for lesson in series_lessons
        }
        for series_id, series_lessons in list(by_series.items()):
            if series_id is not None and len(series_lessons) * 2 <= series[series_id]['count']:
                del by_series[series_id]
                series_lessons = [lesson for lesson in series_lessons if lesson['id'] not in own_series_lessons]
                name = clean_text(series[series_id]['name']).strip(' -')
                if SLOGAN.match(name + ':'):  # a 'series' named by the site's slogan, of lessons of all ravs: none
                    by_series[None] += series_lessons
                    continue
                group = STUDY_DAYS if STUDY_DAY_SERIES.search(name) else None
                by_series[group] += series_lessons
                title_prefix.update({lesson['id']: name for lesson in series_lessons})
        for lesson in by_series.pop(None, []):  # his other lessons, by the topic their title names, if any
            by_series[topic_of(lesson_title(lesson), topics)] += [lesson]
    for configured in splits:
        split(by_series, series, configured)

    SITE.find_audio(CACHE_SECTION, [lesson for series_lessons in by_series.values() for lesson in series_lessons],
                    audio_in_page)
    prefetch([lesson_audio_url(lesson) for series_lessons in by_series.values() for lesson in series_lessons
              if lesson_audio_url(lesson)])

    parsers = []
    for series_id, series_lessons in by_series.items():
        rav = ravs[collections.Counter(r for lesson in series_lessons for r in lesson['rabbis']).most_common(1)[0][0]]
        if rav_name:
            rav = {**rav, 'name': rav_name}
        with_audio = [lesson for lesson in series_lessons if lesson_audio_url(lesson)]
        if not with_audio:
            continue
        if series_id is None:
            name, feed_id, website = OTHER_LESSONS, f'meirtv-rabbi-{term["id"]}-other', term['link']
        elif isinstance(series_id, Topic):
            topic_id = hashlib.sha1(series_id.name.encode()).hexdigest()[:8]
            name, feed_id, website = series_id.name, f'meirtv-rabbi-{term["id"]}-topic-{topic_id}', term['link']
        elif series_id == STUDY_DAYS:
            name, feed_id, website = STUDY_DAYS, f'meirtv-rabbi-{term["id"]}-study-days', term['link']
        elif isinstance(series_id, tuple):  # a part of a series too big for one podcast
            series_id, part = series_id
            part_id = hashlib.sha1(part.encode()).hexdigest()[:8]
            name = f'{strip_rav_name(clean_text(series[series_id]["name"]), rav["name"]).strip(" -")} - {part}'
            feed_id, website = f'meirtv-{series_id}-part-{part_id}', series[series_id]['link']
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
                            title=prefixed(title_prefix.get(lesson['id']), strip_rav_name(lesson_title(lesson), rav['name'])),
                            link=lesson['link'],
                            audio_url=lesson_audio_url(lesson),
                            order=lesson['id'])
                     for lesson in with_audio],
            missing=len(series_lessons) - len(with_audio),
        ))
    return parsers


def split(by_series, series, configured):
    """moves the lessons of the series named configured['series'] to a podcast per part, as its titles name them"""
    for series_id in [s for s in by_series if s in series and series_name(series[s]) == configured['series']]:
        for lesson in by_series.pop(series_id):
            part = next((part['name'] for part in configured['parts']
                         if 'words' not in part or topic_of(lesson_title(lesson), [part['words']])), None)
            by_series[(series_id, part) if part else series_id].append(lesson)


def series_name(term):
    return clean_text(term['name']).strip(' -')


def lesson_title(lesson):
    return SLOGAN.sub('', clean_text(lesson['title']['rendered']))


def prefixed(prefix, title):
    return f'{prefix}: {title}' if prefix else title


def audio_in_page(page):
    match = MP3_URL.search(page)
    return match.group(0) if match else None


def lesson_audio_url(lesson):
    url = cache.section(CACHE_SECTION).get(str(lesson['id']))
    # older files' paths have spaces and the like: 'Kalner/0637/Idx 74114.mp3'
    return url and quote(url, safe=':/?&=%#')
