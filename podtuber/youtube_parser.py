from pathlib import Path
from urllib.parse import quote
import pytz

from pytube import Playlist
from podgen import Person, Media

from utils import clean_jpg_url


class VideoParser:
    def __init__(self, video):
        self.video = video

    def check_availability(self):
        self.video.check_availability()

        # make sure info is parsed (otherwise description might be None)
        # taken from https://github.com/pytube/pytube/issues/1674
        self.video.bypass_age_gate()

    def get_title(self):
        return self.video.title

    def get_summary(self):
        return self.video.description

    def get_publication_date(self):
        return pytz.utc.localize(self.video.publish_date)  # TODO is it really UTC? always?

    def get_explicit(self):
        return self.video.age_restricted

    def get_media(self, base_url, series_title):
        stream = self.video.streams.get_audio_only()  # returns best mp4 audio stream
        return get_media_from_youtube(base_url, series_title, stream)

    def get_id(self):
        return self.video.watch_url

    def get_link(self):
        return self.video.watch_url

    def get_authors(self):
        return [Person(self.video.author)]


class YoutubeParser:
    def __init__(self, playlist_url):
        self.playlist = Playlist(playlist_url)
        assert self.playlist.videos

    def get_name(self):
        return self.playlist.title

    def get_description(self):
        try:
            return self.playlist.description
        except KeyError:
            return self.get_name()

    def get_website(self):
        return self.playlist.playlist_url

    def get_image(self):
        # TODO make sure it's square, at least 1400x1400
        return clean_jpg_url(self.playlist.videos[0].thumbnail_url)

    def get_authors(self):
        return [Person(self.playlist.owner)]

    def get_owner_name(self):
        return self.playlist.owner

    def get_episodes(self):
        for video in self.playlist.videos:
            yield VideoParser(video)


def get_media_from_youtube(base_url, series_title, stream):
    path = Path('files') / series_title
    path.mkdir(parents=True, exist_ok=True)
    stream.subtype = 'm4a'
    file = Path(stream.download(output_path=path))
    media = Media(
        url=f'{base_url}/{quote((path / file.name).as_posix())}',
        size=stream.filesize,
    )
    media.populate_duration_from(file)
    return media
