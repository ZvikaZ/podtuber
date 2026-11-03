import hashlib
import re
import urllib.parse
from datetime import datetime, timezone

from curl_cffi import requests

from podtuber.audio_info import prefetch
from podtuber.hebrew_dates import gematria
from podtuber.lessons import Lesson, SeriesParser

SITE_URL = 'https://nachyomi.netlify.app'
SOURCE_NAME = 'הנ"ך היומי'
LOGO_URL = 'https://nachyomi.app/logo.png'
AUDIO_URL = 'https://nachyomiapp.s3.eu-north-1.amazonaws.com/lessons/{}.mp4'  # mp3s, despite their name
# the files' dates are of their (mostly bulk) upload, so a book's chapters are ordered by number alone
UPLOADED = datetime(2024, 11, 10, tzinfo=timezone.utc)

# the app's script holds its daily schedule: [[{book:"יהושע",chapter:"א"},{book:"יהושע",chapter:"ב"}],...]
SCHEDULE = re.compile(r'=(\[\[\{book:.*?\}\]\])')
CHAPTER = re.compile(r'\{book:"([^"]*)",chapter:"([^"]*)"')


def get_series_parsers(url, rav_name):
    """the site's lessons, a chapter each, as a podcast per book of the Nach: https://nachyomi.netlify.app/lessons"""
    books = {}
    for book, chapter in schedule_chapters(read_script()):
        books.setdefault(book, [])
        if chapter not in books[book]:
            books[book].append(chapter)
    prefetch([audio_url(book, chapter) for book, chapters in books.items() for chapter in chapters])
    return [SeriesParser(
        feed_id=f'nachyomi-{hashlib.sha1(book.encode()).hexdigest()[:8]}',
        name=book,
        rav_name=rav_name,
        source_name=SOURCE_NAME,
        description=f'שיעורי {rav_name} על ספר {book}, פרק אחר פרק, מתוך {SOURCE_NAME}',
        website=url,
        image=LOGO_URL,
        lessons=[Lesson(id=f'nachyomi-{book}-{chapter}', date=UPLOADED, title=f'{book} פרק {chapter}', link=url,
                        audio_url=audio_url(book, chapter), order=gematria(chapter))
                 for chapter in chapters],
        dated=False,
    ) for book, chapters in books.items()]


def read_script():
    session = requests.Session(impersonate='chrome')
    page = session.get(f'{SITE_URL}/lessons', timeout=60)
    page.raise_for_status()
    script = re.search(r'src=["\']?(/assets/index\.[^"\' >]+\.js)', page.text).group(1)
    response = session.get(SITE_URL + script, timeout=60)
    response.raise_for_status()
    return response.text


def schedule_chapters(script):
    """the (book, chapter) pairs of the schedule (of a regular year; a leap year's spreads the same chapters)"""
    schedule = SCHEDULE.search(script)
    if not schedule:
        raise ValueError("Couldn't find the schedule in the site's script")
    text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda match: chr(int(match.group(1), 16)), schedule.group(1))
    return CHAPTER.findall(text)


def audio_url(book, chapter):
    return AUDIO_URL.format(urllib.parse.quote(f'{book}+פרק+{chapter}', safe='+'))
