import collections
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote, quote

from podtuber.audio_info import prefetch
from podtuber.cache import cache
from podtuber.hebrew_dates import year_name
from podtuber.lessons import Lesson, SeriesParser, Topic, clean_text, strip_rav_name, topic_of
from podtuber.wordpress import WordPressSite

SITE = WordPressSite('https://bneidavid.org')
SOURCE_NAME = 'בני דוד'
# (not the site's 'logo.png': that's the logo of JewTech, who built the site)
LOGO_URL = f"{SITE.url}/wp-content/uploads/2020/02/{quote('לוגו-מוסדות-בני-דוד.png')}"
CACHE_SECTION = 'bneidavid:audio'
LESSON_FIELDS = 'id,date_gmt,link,title,series,rav'
GENERAL_SERIES = re.compile(r'^כללי\b')  # a rav's general series: 'כללי - הרב גיורא'
HOLIDAY_SERIES = re.compile(r'^חגים\b')  # and his holidays' one: 'חגים - הרב אלי'
# a series within the general one, which only its lessons' titles name: 'מי מתפלל? | מפגשים עם אלוקים [12]', or
# 'מנהיגות [3]'
SUB_SERIES = [re.compile(r'\|\s*([^|\[\]]+?)\s*\[(?:\d+|חלק\s*[א-ת]\'?)\]'), re.compile(r'^([^|\[\]]+?)\s*\[\d+\]\s*$')]
NOT_A_SERIES = re.compile(r'^(שיעור\s+)?כללי')  # '... | כללי [2]'
HOLIDAYS = [  # each a podcast of a rav's holiday lessons; a list is a holiday's names, the first naming it
    'ראש השנה', ['יום כיפור', 'יום הכיפורים', 'כיפור', 'הכיפורים'],
    ['סוכות', 'שמחת תורה', 'הושענא רבה', 'ארבעת המינים'], 'חנוכה', ['ט"ו בשבט', 'טו בשבט'],
    ['פורים', 'מגילת אסתר'], ['פסח', 'ליל הסדר', 'הגדה', 'יציאת מצרים'], ['ל"ג בעומר', 'לג בעומר'],
    ['ספירת העומר', 'העומר'], 'יום השואה', 'יום העצמאות', 'יום הזיכרון', 'יום ירושלים', ['שבועות', 'מתן תורה'],
    ['תשעה באב', "ט' באב", 'בין המצרים', 'י"ז בתמוז', 'שבעה עשר בתמוז', 'חורבן'], 'עשרה בטבת', 'אלול', 'שובבים',
]

# the api doesn't give a lesson's audio, only its page does: either on the site's old media server,
# or a Google Drive file streamed through the site
MEDIA_LINE_URL = re.compile(r'https?://[\w.-]*media-line\.co\.il/[^"\'\s<>]+\.mp3', re.IGNORECASE)  # also .MP3
DRIVE_FILE_ID = re.compile(r'action=stream_audio&file_id=([\w-]+)')
STREAM_URL = f'{SITE.url}/wp-admin/admin-ajax.php?action=stream_audio&file_id={{}}'


def get_series_parsers(url, topics=(), split_by_year=False):
    """
    https://bneidavid.org/rav/<rav>/ is a podcast per series of that rav (leaving out his guest lessons in others'
    series); https://bneidavid.org/series/<series>/ is that series alone.
    His general series ('כללי - ...') is split: topics, the lessons whose titles name one of them (the first one
    named), are podcasts of their own (and per teaching year, with split_by_year: a course he taught again over the
    years), as are the series within it that only its lessons' titles name. His holidays' series is split by holiday.
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

    for series_id in list(by_series):
        name = clean_text(series[series_id]['name'])
        if GENERAL_SERIES.match(name):
            split(by_series, series_id, lambda lesson: general_topic(lesson, topics, split_by_year))
        elif HOLIDAY_SERIES.match(name):
            split(by_series, series_id, lambda lesson: topic_of(clean_text(lesson['title']['rendered']), HOLIDAYS))

    SITE.find_audio(CACHE_SECTION, [lesson for series_lessons in by_series.values() for lesson in series_lessons],
                    audio_in_page)
    prefetch([lesson_audio_url(lesson) for series_lessons in by_series.values() for lesson in series_lessons
              if lesson_audio_url(lesson)])

    parsers = []
    for series_id, series_lessons in sorted(by_series.items(), key=lambda item: series_sort_key(item[0], series)):
        rav = ravs[collections.Counter(r for lesson in series_lessons for r in lesson['rav']).most_common(1)[0][0]]
        with_audio = [lesson for lesson in series_lessons if lesson_audio_url(lesson)]
        if isinstance(series_id, tuple):  # a topic of a general series, in one year
            series_id, topic = series_id
            topic_id = hashlib.sha1(topic.encode()).hexdigest()[:8]
            name, feed_id = topic.name, f'bneidavid-{series_id}-topic-{topic_id}'
        else:
            name, feed_id = strip_rav_name(clean_text(series[series_id]['name']), rav['name']), f'bneidavid-{series_id}'
        if with_audio:
            parsers.append(SeriesParser(
                feed_id=feed_id,
                name=name,
                rav_name=rav['name'],
                source_name=SOURCE_NAME,
                description=f'שיעורי {rav["name"]} בסדרה "{name}", מתוך {SITE.url}',
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
                missing=len(series_lessons) - len(with_audio),
            ))
    return parsers


def split(by_series, series_id, topic):
    """moves the series' lessons with a topic (a Topic, or None) to a podcast per topic, unless it has one lesson"""
    by_topic = collections.defaultdict(list)
    for lesson in by_series[series_id]:
        by_topic[topic(lesson)].append(lesson)
    for name, topic_lessons in by_topic.items():
        if name and len(topic_lessons) > 1:  # a single lesson stays where it was
            by_series[(series_id, name)] = topic_lessons
            by_series[series_id] = [lesson for lesson in by_series[series_id] if lesson not in topic_lessons]


def general_topic(lesson, topics, split_by_year):
    """the topic of a lesson of a general series: one of the topics its title names, else the series it names"""
    title = clean_text(lesson['title']['rendered'])
    if topic := topic_of(title, topics):
        if split_by_year:
            return Topic(f'{topic} - {year_name(datetime.fromisoformat(lesson["date_gmt"]).date())}')
        return topic
    for pattern in SUB_SERIES:
        if (match := pattern.search(title)) and not NOT_A_SERIES.match(match.group(1)):
            return Topic(match.group(1).strip(' -–'))
    return None


def series_sort_key(series_id, series):
    """by name; a general series' topics after it, by their names"""
    if isinstance(series_id, tuple):
        return series[series_id[0]]['name'], series_id[1]
    return series[series_id]['name'], ''


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
