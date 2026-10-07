import html
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from curl_cffi import requests

from podtuber.cache import cache

logger = logging.getLogger(__name__)

SNAPSHOTTED_SITES = []


class WordPressSite:
    """
    A WordPress site's public api (/wp-json/wp/v2/), as the sites of several yeshivot are.

    A site that refuses some servers (GitHub's, say) can be given a snapshot file: a run that can read the site,
    with --snapshot, saves what it returned there (and what was found about its audio), and a run that can't read
    the site uses the snapshot instead.
    """

    def __init__(self, url, snapshot=None, media_host=None):
        self.url = url.rstrip('/')
        # some sites' firewalls (Cloudflare, say) turn away what doesn't look like a browser
        self.session = requests.Session(impersonate='chrome')
        self.snapshot = Path(snapshot) if snapshot else None
        self.media_host = media_host  # where the site's audio is, whose durations go into the snapshot
        self.recorded, self.replayed, self.cache_sections = {}, None, set()
        if self.snapshot:
            SNAPSHOTTED_SITES.append(self)

    def api(self, path, params):
        key = f'{path}?{urlencode(sorted(params.items()))}'
        if self.replayed is None:
            try:
                response = self.session.get(f'{self.url}/wp-json/wp/v2/{path}', params=params, timeout=60)
                response.raise_for_status()
                self.recorded[key] = response.json(), int(response.headers.get('X-WP-TotalPages', 1))
                return self.recorded[key]
            except Exception as err:
                if not (self.snapshot and self.snapshot.exists()):
                    raise
                self.use_snapshot(err)
        if key not in self.replayed:
            raise KeyError(f'{key} is not in {self.snapshot}')
        return self.replayed[key]

    def use_snapshot(self, err):
        snapshot = json.loads(self.snapshot.read_text(encoding='utf8'))
        logger.warning(f"Couldn't read {self.url} ({err}); using {self.snapshot}, saved {snapshot['saved']}")
        self.replayed = {key: tuple(value) for key, value in snapshot['api'].items()}
        cache.merge(snapshot['cache'])

    def save_snapshot(self):
        if self.replayed is not None or not self.recorded:
            logger.warning(f"Not saving {self.snapshot}, as {self.url} couldn't be read")
            return
        saved = {section: cache.section(section) for section in self.cache_sections}
        saved['audio'] = {url: info for url, info in cache.section('audio').items()
                          if self.media_host and self.media_host in url and 'error' not in info}
        self.snapshot.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot.write_text(json.dumps({
            'saved': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'api': self.recorded,
            'cache': saved,
        }, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
        logger.info(f'Saved {self.snapshot}')

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
        self.cache_sections.add(cache_section)
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


def save_snapshots():
    for site in SNAPSHOTTED_SITES:
        site.save_snapshot()
