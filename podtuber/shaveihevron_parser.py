import collections
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote, quote

from podtuber.audio_info import prefetch
from podtuber.cache import cache
from podtuber.lessons import Lesson, SeriesParser, clean_text
from podtuber.wordpress import WordPressSite

SITE = WordPressSite('https://shaveihevron.org')
SOURCE_NAME = 'שבי חברון'
LOGO_URL = f'{SITE.url}/wp-content/uploads/2022/05/mini-logo-2.png'
CACHE_SECTION = 'shaveihevron:audio'
LESSON_FIELDS = 'id,date_gmt,link,title,topics,rabbi'
OTHER_LESSONS = 'שיעורים נוספים'  # the rav's lessons in topics shared with others, such as 'ראש השנה [כללי]'

# the api doesn't give a lesson's audio, only its page does: its player, before the links to the previous and
# next lessons (the players after them are of the site's latest lessons)
PLAYER_URL = re.compile(r'<audio class="jet-audio-player"[^>]*src="([^"]+)"')
PAGE_END = 'elementor-post-navigation'


def get_series_parsers(url, rav_name=None):
    """
    https://shaveihevron.org/rabbi/<rav>/ is a podcast per series ('topic', in the site's words) of that rav, and one
    of his lessons in topics mostly of others; https://shaveihevron.org/topics/<topic>/ is that topic alone.
    rav_name, when given, is how the rav is named, rather than as the site names him (often by surname first).
    """
    kind, slug = unquote(urlparse(url).path).strip('/').split('/')[:2]
    if kind not in ('rabbi', 'topics'):
        raise ValueError(f'Expected a /rabbi/... or /topics/... page of {SITE.url}, not {url}')
    term = SITE.get_term(kind, slug)
    lessons = SITE.get_all('lessons', {kind: term['id'], '_fields': LESSON_FIELDS})
    topics = {t['id']: t for t in SITE.get_terms('topics', {t for lesson in lessons for t in lesson['topics']})}
    ravs = {r['id']: r for r in SITE.get_terms('rabbi', {r for lesson in lessons for r in lesson['rabbi']})}
    by_series = collections.defaultdict(list)
    for lesson in lessons:
        # a lesson in a topic and in its sub-topic ('אורות הקודש', 'אורות הקודש א') is in the sub-topic only
        parents = {topics[t]['parent'] for t in lesson['topics']}
        for topic_id in [t for t in lesson['topics'] if t not in parents] or [None]:
            by_series[topic_id].append(lesson)
    if kind == 'rabbi':
        rav_name = rav_name or term['name']
        for topic_id in [t for t in by_series if t is not None]:
            if len(by_series[topic_id]) * 2 <= topics[topic_id]['count']:  # a topic of others' lessons, mostly
                by_series[None] += by_series.pop(topic_id)
    else:
        by_series = {term['id']: by_series[term['id']]}
        rav_name = rav_name or next(iter(ravs.values()), {}).get('name', '')

    all_lessons = list({lesson['id']: lesson for series in by_series.values() for lesson in series}.values())
    SITE.find_audio(CACHE_SECTION, all_lessons, audio_in_page)
    prefetch([lesson_audio_url(lesson) for lesson in all_lessons if lesson_audio_url(lesson)])

    parsers = []
    for series_id, series_lessons in by_series.items():
        with_audio = [lesson for lesson in series_lessons if lesson_audio_url(lesson)]
        if not with_audio:
            continue
        name = OTHER_LESSONS if series_id is None else series_name(topics[series_id]['name'], rav_name)
        parsers.append(SeriesParser(
            feed_id=f'shaveihevron-{series_id}' if series_id else f'shaveihevron-rav-{term["id"]}-other',
            name=name,
            rav_name=rav_name,
            source_name=SOURCE_NAME,
            description=f'שיעורי {rav_name} בסדרה "{name}", מתוך {SITE.url}',
            website=(topics[series_id] if series_id else term)['link'],
            image=LOGO_URL,
            lessons=[Lesson(id=f'shaveihevron-{lesson["id"]}',
                            date=datetime.fromisoformat(lesson['date_gmt']).replace(tzinfo=timezone.utc),
                            title=clean_text(lesson['title']['rendered']),  # 'המשך פס ל | אורות התחיה [30]'
                            link=lesson['link'],
                            audio_url=lesson_audio_url(lesson),
                            order=lesson['id'])
                     for lesson in with_audio],
            number_pattern=r'\[(\d+)\]',
            missing=len(series_lessons) - len(with_audio),
        ))
    return parsers


def series_name(topic_name, rav_name):
    """topics are named 'אורות התחיה | הרב קשתיאל', or 'במדבר [פ"ש] | הרב קשתיאל [תשפ'ג]': without the rav"""
    surname = rav_name.split()[-1] if rav_name else None
    name = clean_text(topic_name)
    if surname:
        name = re.sub(rf'\s*\|\s*הרב\s+{re.escape(surname)}(?![א-ת])', '', name)
    return name.strip()


def audio_in_page(page):
    end = page.find(PAGE_END)
    match = PLAYER_URL.search(page[:end] if end >= 0 else '')
    return match.group(1) if match else None


def lesson_audio_url(lesson):
    url = cache.section(CACHE_SECTION).get(str(lesson['id']))
    return url and quote(url, safe=':/?&=%#')  # their paths are in raw Hebrew
