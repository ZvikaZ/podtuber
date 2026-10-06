import json
import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

FILENAME = 'cache.json'
# a cache file to merge in, if present, such as one built elsewhere, to spare hosts that rate-limit data centers
SEED_FILENAME = 'cache-seed.json'


class Cache:
    """
    Facts that don't change once found, such as a lesson's audio url or an mp3's duration, kept between runs so each
    run only fetches what's new. It's written next to the feeds, so the published copy seeds the next run.
    """

    def __init__(self):
        self.data = {}
        self.path = None

    def load(self, output_dir, base_url):
        self.path = output_dir / FILENAME
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding='utf8'))
        else:
            try:
                with urllib.request.urlopen(f'{base_url.rstrip("/")}/{FILENAME}', timeout=60) as response:
                    self.data = json.load(response)
                logger.info(f'Loaded {FILENAME} from {base_url}')
            except Exception as err:
                logger.info(f'Starting without a cache ({err})')
        seed = Path(SEED_FILENAME)
        if seed.exists():
            self.merge(json.loads(seed.read_text(encoding='utf8')))
            logger.info(f'Merged {SEED_FILENAME}')

    def merge(self, other):
        """add the other cache's entries, where this one has none, or only an error"""
        for name, entries in other.items():
            section = self.section(name)
            for key, value in entries.items():
                current = section.get(key)
                if current is None or (isinstance(current, dict) and 'error' in current):
                    section[key] = value

    def section(self, name):
        return self.data.setdefault(name, {})

    def save(self):
        if self.path:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf8')


cache = Cache()
