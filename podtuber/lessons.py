"""A series of recorded lessons, as the yeshivot's sites publish them, made into a podcast."""
import html
import re
from dataclasses import dataclass
from datetime import datetime

from podgen import Person, Media
from pyluach.dates import HebrewDate

from podtuber.audio_info import audio_info, is_missing, media_details
from podtuber.utils import monotonic_dates


@dataclass
class Lesson:
    id: str  # unique among all the sources, e.g. 'bneidavid-387822'
    date: datetime  # UTC
    title: str
    link: str
    audio_url: str
    order: int = 0  # breaks ties between lessons of the same date, e.g. the site's own id


# words that say nothing about a lesson: 'שיעור מספר 1', 'שיעור שני', 'פרק ד – המשך'
GENERIC_WORD = re.compile(r"(שיעור|מספר|חלק|פסקה|פסקאות|פרק|המשך|ראשון|שני|שלישי|רביעי|חמישי|ו|[א-ת]['’]?|\d+|[-–,.:()'’\"״]+)")


def is_dull(title):
    return all(GENERIC_WORD.fullmatch(word) for word in title.split())


def clean_text(text):
    # some sites write gershayim as two apostrophes: תשע''ז
    return ' '.join(html.unescape(text).replace("''", '"').split())


def strip_rav_name(text, rav_name):
    """'כוזרי [תשע"ז] - הרב קלנר' -> 'כוזרי [תשע"ז]', where the rav's full name is given separately anyway"""
    if not rav_name:
        return text
    last_name = rav_name.split()[-1]
    text = re.sub(rf'\s*[-|–]?\s*הרב\s+(?:\S+\s+)?{re.escape(last_name)}\b(?:\s+(?:שליט"א|זצ"ל))?', '', text)
    return text.strip(' -|–')


def sort_lessons(lessons, number_pattern=None):
    """
    By date; but the sites' dates sometimes swap neighbouring lessons, so when the series is (nearly all) numbered,
    by number: an unnumbered lesson stays after the one before it, and a typo'd repeated number keeps the date
    order. Many repeated numbers, though, mean the numbering restarts within the series, and then only the dates
    make sense.
    """
    by_date = sorted(lessons, key=lambda lesson: (lesson.date, lesson.order))
    if not number_pattern:
        return by_date
    numbers = [int(match.group(1)) if (match := re.search(number_pattern, lesson.title)) else None
               for lesson in by_date]
    numbered = [number for number in numbers if number is not None]
    if len(numbered) < 0.9 * len(numbers) or len(numbered) - len(set(numbered)) > 0.1 * len(numbers):
        return by_date
    keys, previous = [], 0
    for number in numbers:
        previous = number if number is not None else previous
        keys.append(previous)
    return [lesson for _, _, lesson in sorted(zip(keys, range(len(by_date)), by_date))]


class LessonParser:
    def __init__(self, lesson, rav_name, publication_date, series_name):
        self.lesson = lesson
        self.rav_name = rav_name
        self.publication_date = publication_date
        self.series_name = series_name

    def check_availability(self):
        if is_missing(self.lesson.audio_url):
            raise ValueError('its audio file is missing')

    def get_title(self):
        if is_dull(self.lesson.title):  # a title such as 'שיעור מספר 1' is named after its series (or date)
            return f'{self.series_name} - {self.lesson.title or self.get_summary()}'
        return self.lesson.title

    def get_summary(self):
        return HebrewDate.from_pydate(self.lesson.date.date()).hebrew_date_string()

    def get_publication_date(self):
        return self.publication_date

    def get_explicit(self):
        return False

    def get_media(self, base_url, series_title):
        return Media(url=self.lesson.audio_url, type='audio/mpeg', **media_details(self.lesson.audio_url))

    def get_id(self):
        return self.lesson.id

    def get_link(self):
        return self.lesson.link

    def get_authors(self):
        return [Person(self.rav_name)]


class SeriesParser:
    """a series of lessons by one rav on one site, as a podcast"""

    def __init__(self, *, feed_id, name, rav_name, source_name, description, website, image, lessons,
                 number_pattern=None):
        self.feed_id = feed_id
        self.name = name
        self.rav_name = rav_name
        self.source_name = source_name
        self.description = description
        self.website = website
        self.image = image
        self.lessons = sort_lessons(lessons, number_pattern)

    def get_name(self):
        return f'{self.name} - {self.rav_name}'

    def get_feed_id(self):
        return self.feed_id

    def get_source_name(self):
        return self.source_name

    def get_recordings(self):
        return [(lesson.date.date(), (audio_info(lesson.audio_url) or {}).get('duration'),
                 (audio_info(lesson.audio_url) or {}).get('size'))
                for lesson in self.lessons]

    def get_description(self):
        return self.description

    def get_website(self):
        return self.website

    def get_image(self):
        return self.image

    def get_authors(self):
        return [Person(self.rav_name)]

    def get_owner_name(self):
        return self.rav_name

    def get_episodes(self):
        dates = monotonic_dates([lesson.date.replace(microsecond=0) for lesson in self.lessons])
        for lesson, publication_date in zip(self.lessons, dates):
            yield LessonParser(lesson, self.rav_name, publication_date, self.name)
