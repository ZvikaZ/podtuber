import html
import json
import logging
import time
import urllib.request
from urllib.parse import urlencode

from podtuber.cache import cache

logger = logging.getLogger(__name__)

USER_AGENT = 'Mozilla/5.0 (compatible; podtuber)'


class WordPressSite:
    """A WordPress site's public api (/wp-json/wp/v2/), as the sites of several yeshivot are"""

    def __init__(self, url):
        self.url = url.rstrip('/')

    def api(self, path, params):
        request = urllib.request.Request(f'{self.url}/wp-json/wp/v2/{path}?{urlencode(params)}',
                                         headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response), int(response.headers.get('X-WP-TotalPages', 1))

    def get_all(self, path, params):
        items, page, pages = [], 1, 1
        while page <= pages:
            data, pages = self.api(path, {**params, 'per_page': 100, 'page': page})
            items += data
            page += 1
        return items

    def get_term(self, kind, slug):
        found, _ = self.api(kind, {'slug': slug})
        if not found:
            raise ValueError(f"No {kind} '{slug}' on {self.url}")
        return found[0]

    def get_terms(self, kind, ids):
        ids = sorted(ids)
        return [term for i in range(0, len(ids), 100)
                for term in self.get_all(kind, {'include': ','.join(map(str, ids[i:i + 100]))})]

    def find_audio(self, cache_section, lessons, extract):
        """
        The audio url of each lesson (an api item with 'id' and 'link') that isn't in the cache yet, read from its
        page by extract(page html) (None when it has none). Pages are read once, gently.
        """
        audio = cache.section(cache_section)
        todo = [lesson for lesson in lessons if str(lesson['id']) not in audio]
        if todo:
            logger.info(f'Reading {len(todo)} lesson pages of {self.url}')
        for n, lesson in enumerate(todo, 1):
            try:
                request = urllib.request.Request(lesson['link'], headers={'User-Agent': USER_AGENT})
                with urllib.request.urlopen(request, timeout=60) as response:
                    page = html.unescape(response.read().decode('utf8'))
            except Exception as err:
                logger.warning(f"Couldn't read {lesson['link']} (will retry next time): {err}")
                continue
            audio[str(lesson['id'])] = extract(page)
            if n % 50 == 0:
                logger.info(f'  {n} of {len(todo)}')
                cache.save()
            time.sleep(1)  # be gentle
