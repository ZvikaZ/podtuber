import collections
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

from podtuber.audio_info import prefetch
from podtuber.lessons import Lesson, SeriesParser, clean_text, strip_rav_name
from podtuber.wordpress import WordPressSite

SITE = WordPressSite('https://www.hakotel.org.il')
SOURCE_NAME = 'ישיבת הכותל'
LOGO_URL = f'{SITE.url}/wp-content/uploads/2021/12/%D7%AA%D7%9E%D7%95%D7%A0%D7%941-300x300.png'
LESSON_FIELDS = 'id,date_gmt,link,title,categories,content'
SERIES_CATEGORY = 'סדרות'  # the category whose sub-categories are the series
OTHER_LESSONS = 'שיעורים נוספים'  # the rav's lessons that aren't in any series

# unlike other sites, the api gives each lesson's audio, in its content
MP3_URL = re.compile(r'https?://files\.hakotel\.org\.il/[^"\'\s<>?]+\.mp3', re.IGNORECASE)


def get_series_parsers(url):
    """
    A rav's category page, such as https://www.hakotel.org.il/category/.../רבנים/הרב-קלנר-יוסף/, is a podcast per
    series of that rav (and his lessons in no series as a podcast of their own); a series' category page is that
    series alone.
    """
    term = SITE.get_term('categories', unquote(urlparse(url).path).strip('/').split('/')[-1])
    series_root = SITE.get_term('categories', SERIES_CATEGORY)['id']
    is_series = term['parent'] == series_root
    lessons = SITE.get_all('posts', {'categories': term['id'], '_fields': LESSON_FIELDS})
    categories = {c['id']: c for c in SITE.get_terms('categories', {c for lesson in lessons for c in lesson['categories']})}

    by_series = collections.defaultdict(list)
    for lesson in lessons:
        series_ids = [c for c in lesson['categories'] if categories[c]['parent'] == series_root]
        for series_id in series_ids or ([] if is_series else [None]):
            by_series[series_id].append(lesson)
    if is_series:
        by_series = {term['id']: by_series[term['id']]}
    rav_name = rav_display_name(term['name']) if not is_series else None

    prefetch([audio_url(lesson) for series_lessons in by_series.values() for lesson in series_lessons
              if audio_url(lesson)])
    parsers = []
    for series_id, series_lessons in by_series.items():
        name = OTHER_LESSONS if series_id is None else clean_text(categories[series_id]['name'])
        rav = rav_name or rav_from_series_name(name)
        with_audio = [lesson for lesson in series_lessons if audio_url(lesson)]
        if not with_audio:
            continue
        parsers.append(SeriesParser(
            feed_id=f'hakotel-{series_id}' if series_id else f'hakotel-rav-{term["id"]}-other',
            name=strip_rav_name(name, rav),
            rav_name=rav,
            source_name=SOURCE_NAME,
            description=f'שיעורי {rav} בסדרה "{strip_rav_name(name, rav)}", מתוך {SITE.url}',
            website=(categories[series_id] if series_id else term)['link'],
            image=LOGO_URL,
            lessons=[Lesson(id=f'hakotel-{lesson["id"]}',
                            date=datetime.fromisoformat(lesson['date_gmt']).replace(tzinfo=timezone.utc),
                            # 'כוזרי שיעור מספר 42 – הרב יוסף קלנר שליט"א'
                            title=strip_rav_name(clean_text(lesson['title']['rendered']), rav),
                            link=lesson['link'],
                            audio_url=audio_url(lesson),
                            order=lesson['id'])
                     for lesson in with_audio],
            number_pattern=r'שיעור\s+(?:מספר\s+)?(\d+)',
        ))
    return parsers


def audio_url(lesson):
    match = MP3_URL.search(lesson['content']['rendered'])
    return match.group(0) if match else None


def rav_display_name(category_name):
    """the site names its rabbis' categories by surname first: 'הרב קלנר יוסף' -> 'הרב יוסף קלנר'"""
    title, surname, *first_names = category_name.split()
    return ' '.join([title, *first_names, surname]) if first_names else category_name


def rav_from_series_name(series_name):
    """series are named 'הכוזרי - הרב יוסף קלנר'"""
    return series_name.rsplit(' - ', 1)[-1] if ' - ' in series_name else ''
