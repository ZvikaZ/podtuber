import io
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from curl_cffi import requests
from tinytag import TinyTag

from podtuber.cache import cache

logger = logging.getLogger(__name__)

HEAD_SIZE = 128 * 1024  # enough for the mp3's tags and first frames, from which its duration follows
# each thread's session, which keeps its connections open: hosts such as Bnei David's media server stop answering
# a client that opens new connections too often
_local = threading.local()


def audio_info(url):
    """{'size': bytes, 'duration': seconds (when it could be worked out)} of a remote mp3, or None if unreadable"""
    info = cache.section('audio').get(url)
    if info is None:
        prefetch([url])
        info = cache.section('audio').get(url)
    return info if info and 'error' not in info else None


def is_missing(url):
    """
    Whether the mp3 is certainly gone (its server says so). Other failures say nothing about the file: hosts such as
    Dropbox answer bursts of requests from a data center with an error page, while the file plays fine for listeners.
    """
    error = cache.section('audio').get(url, {}).get('error', '')
    return error.startswith(('HTTP Error 404', 'HTTP Error 410'))


def media_details(url):
    """keyword arguments for podgen's Media: the size and duration, when known"""
    info = audio_info(url) or {}
    details = {'size': info['size']} if 'size' in info else {}
    if 'duration' in info:
        details['duration'] = timedelta(seconds=info['duration'])
    return details


def prefetch(urls, workers=6):
    """read the mp3s that aren't in the cache yet, and retry those that failed (which may have been temporary)"""
    known = cache.section('audio')
    todo = [url for url in dict.fromkeys(urls) if url not in known or 'error' in known[url]]
    if not todo:
        return
    logger.info(f'Reading the durations of {len(todo)} mp3s')
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(_probe, url): url for url in todo}
        for n, future in enumerate(as_completed(futures), 1):
            known[futures[future]] = future.result()
            if n % 100 == 0:
                logger.info(f'  {n} of {len(todo)}')
                cache.save()


def _session():
    if not hasattr(_local, 'session'):
        _local.session = requests.Session(impersonate='chrome')
    return _local.session


def _probe(url):
    for attempt in range(3):
        try:
            response = _session().get(url, headers={'Range': f'bytes=0-{HEAD_SIZE - 1}'}, timeout=30, stream=True)
            try:
                error = f'HTTP Error {response.status_code}: {response.reason}'  # (as is_missing expects)
                if 400 <= response.status_code < 500:  # a missing file won't appear by retrying now
                    return {'error': error}
                if response.status_code >= 500:
                    raise IOError(error)
                if not response.headers.get('Content-Range'):
                    return {'error': f"not an audio file ({response.headers.get('Content-Type')})"}
                head = b''
                for chunk in response.iter_content():
                    head += chunk
                    if len(head) >= HEAD_SIZE:
                        break
                size = int(response.headers['Content-Range'].split('/')[1])
            finally:
                response.close()
            tag = TinyTag.get(file_obj=io.BufferedReader(_PartialFile(head[:HEAD_SIZE], size)), filename='audio.mp3')
            return {'size': size} if tag.duration is None else {'size': size, 'duration': round(tag.duration, 1)}
        except Exception as err:
            error = err
            time.sleep(5)
    logger.warning(f"Couldn't read {url}: {error}")
    return {'error': str(error)}


class _PartialFile(io.RawIOBase):
    """The first bytes of a remote file, posing as the whole file (the rest reads as zeros)."""

    def __init__(self, head, size):
        self.head, self.size, self.pos = head, size, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, offset, whence=io.SEEK_SET):
        self.pos = {io.SEEK_SET: offset, io.SEEK_CUR: self.pos + offset, io.SEEK_END: self.size + offset}[whence]
        return self.pos

    def tell(self):
        return self.pos

    def readinto(self, buffer):
        n = max(0, min(len(buffer), self.size - self.pos))
        data = self.head[self.pos:self.pos + n]
        buffer[:n] = data + bytes(n - len(data))
        self.pos += n
        return n
