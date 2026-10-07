import html
import logging
import time

from curl_cffi import requests

from podtuber.cache import cache

logger = logging.getLogger(__name__)


class WordPressSite:
    """A WordPress site's public api (/wp-json/wp/v2/), as the sites of several yeshivot are"""

    def __init__(self, url):
        self.url = url.rstrip('/')
        # some sites' firewalls (Cloudflare, say) turn away what doesn't look like a browser
        self.session = requests.Session(impersonate='chrome')

    def api(self, path, params):
        response = self.session.get(f'{self.url}/wp-json/wp/v2/{path}', params=params, timeout=60)
        response.raise_for_status()
        return response.json(), int(response.headers.get('X-WP-TotalPages', 1))

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
                response = self.session.get(lesson['link'], timeout=60)
                response.raise_for_status()
                page = html.unescape(response.text)
            except Exception as err:
                logger.warning(f"Couldn't read {lesson['link']} (will retry next time): {err}")
                continue
            audio[str(lesson['id'])] = extract(page)
            if n % 50 == 0:
                logger.info(f'  {n} of {len(todo)}')
                cache.save()
            time.sleep(1)  # be gentle
