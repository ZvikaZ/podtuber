"""
Podcasts that already exist: listed and searched on the index page, and taking part in finding duplicates, but
subscribed to at their source, so no copy of them is published.
"""
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime

from podgen import Media, Person

ITUNES = '{http://www.itunes.com/dtds/podcast-1.0.dtd}'
USER_AGENT = 'Mozilla/5.0 (compatible; podtuber)'


def get_parsers(url, rav_name, source_name):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        channel = ET.fromstring(response.read()).find('channel')
    return [LinkedPodcastParser(url, channel, rav_name, source_name)]


def parse_duration(text):
    """'1:02:03', '62:03' or '3723' -> seconds"""
    try:
        seconds = 0
        for part in (text or '').strip().split(':'):
            seconds = seconds * 60 + int(part)
        return seconds or None
    except ValueError:
        return None


class EpisodeParser:
    def __init__(self, item, rav_name):
        self.item = item
        self.rav_name = rav_name
        self.enclosure = item.find('enclosure')

    def check_availability(self):
        if self.enclosure is None or not self.enclosure.get('url'):
            raise ValueError('it has no audio')

    def get_title(self):
        return (self.item.findtext('title') or '').strip()

    def get_summary(self):
        return self.item.findtext('description') or ''

    def get_publication_date(self):
        return parsedate_to_datetime(self.item.findtext('pubDate'))

    def get_explicit(self):
        return False

    def get_media(self, base_url, series_title):
        duration = parse_duration(self.item.findtext(f'{ITUNES}duration'))
        return Media(url=self.enclosure.get('url'), size=int(self.enclosure.get('length') or 0),
                     type=self.enclosure.get('type') or 'audio/mpeg',
                     duration=timedelta(seconds=duration) if duration else None)

    def get_size(self):
        return int(self.enclosure.get('length') or 0) or None

    def get_id(self):
        return self.item.findtext('guid') or self.enclosure.get('url')

    def get_link(self):
        return self.item.findtext('link')

    def get_authors(self):
        return [Person(self.rav_name)]


class LinkedPodcastParser:
    def __init__(self, url, channel, rav_name, source_name):
        self.url = url
        self.channel = channel
        self.rav_name = rav_name
        self.source_name = source_name
        self.episodes = [EpisodeParser(item, rav_name) for item in channel.findall('item')]

    def get_linked_feed_url(self):
        """the podcast's own feed, which subscribing uses"""
        return self.url

    def get_name(self):
        return (self.channel.findtext('title') or self.url).strip()

    def get_feed_id(self):
        return 'linked-' + hashlib.sha1(self.url.encode()).hexdigest()[:8]

    def get_source_name(self):
        return self.source_name

    def get_recordings(self):
        return [(episode.get_publication_date().date(),
                 parse_duration(episode.item.findtext(f'{ITUNES}duration')), episode.get_size())
                for episode in self.episodes]

    def get_description(self):
        return self.channel.findtext('description') or self.get_name()

    def get_website(self):
        return self.channel.findtext('link')

    def get_image(self):
        image = self.channel.find(f'{ITUNES}image')
        return image.get('href') if image is not None else None

    def get_authors(self):
        return [Person(self.rav_name)]

    def get_owner_name(self):
        return self.rav_name

    def get_episodes(self):
        return self.episodes
