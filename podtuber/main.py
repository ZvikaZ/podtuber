# TODO Google Podcast Index (maybe) needs owner (i.e., mail) in order to index
# TODO Pocket Casts assumes next episode release time - why? how can we control this?

# I'm not sure that those are still relevant, they're from before I started downloading from youtube:
# TODO podcastindex.org doesn't play, or download
# TODO Mac's podcast takes 30 minutes to start playing (Daniel's report in Discord)

from urllib.parse import urlparse, quote
from pathlib import Path
import pytz
import argparse

from podgen import Podcast, Media, Person, htmlencode
from pytube import Playlist
from pathvalidate import sanitize_filename


def clean_jpg_url(url):
    return urlparse(url)._replace(query='').geturl()


def get_media_from_youtube(podcast_url_base, series_title, stream):
    path = Path('files') / series_title
    path.mkdir(parents=True, exist_ok=True)
    stream.subtype = 'm4a'
    file = Path(stream.download(output_path=path))
    media = Media(
        url=f'{podcast_url_base}/{quote((path / file.name).as_posix())}',
        size=stream.filesize,
    )
    media.populate_duration_from(file)
    return media


def create_rss_from_youtube_playlist(playlist_url, podcast_url_base):
    playlist = Playlist(playlist_url)
    print(playlist.title)
    assert playlist.videos

    podcast = Podcast()
    podcast.name = playlist.title
    try:
        podcast.description = playlist.description
    except KeyError:
        podcast.description = playlist.title
    podcast.website = playlist.playlist_url
    podcast.explicit = playlist.videos[0].age_restricted
    podcast.image = clean_jpg_url(playlist.videos[0].thumbnail_url)  # TODO make sure it's square, at least 1400x1400
    podcast.authors = [Person(playlist.owner)]

    # TODO set automatically (e.g., https://github.com/pytube/pytube/issues/1742) or manually from argparse
    podcast.language = 'en-US'

    sanitized_title = sanitize_filename(playlist.title).replace(' ', '_')

    # TODO support these?
    # podcast.owner=Person(playlist.owner)   # podcast.owner needs also mail (while playlist.owner is only name)
    # podcast.feed_url=...      # using podcast_url_base + sanitized_title + .rss
    # podcast.category=...

    for video in playlist.videos:
        try:
            video.check_availability()
        except Exception as err:
            print(f"Skipping '{playlist_url}' because of: {err}")
        else:
            # make sure info is parsed (otherwise description might be None)
            # taken from https://github.com/pytube/pytube/issues/1674
            video.bypass_age_gate()

            episode = podcast.add_episode()
            # print(clean_jpg_url(v.thumbnail_url))    #TODO use this for episodes as well?
            episode.title = htmlencode(video.title)
            episode.summary = htmlencode(video.description)
            episode.publication_date = pytz.utc.localize(video.publish_date)  # TODO is it really UTC? always?
            episode.explicit = video.age_restricted
            if episode.explicit:
                podcast.explicit = True
            stream = video.streams.get_audio_only()  # returns best mp4 audio stream
            episode.media = get_media_from_youtube(podcast_url_base, sanitized_title, stream)
            episode.id = video.watch_url
            episode.link = video.watch_url
            episode.authors = [Person(video.author)]

    filename = f'{sanitized_title}.rss'
    podcast.rss_file(filename)
    return filename


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Creates a podcast .rss file from YouTube playlist")
    parser.add_argument('url', help="YouTube playlist's URL")
    args = parser.parse_args()

    podcast_url_base = 'http://18.159.236.82/zvika/podcast/'  # TODO
    rssfile = create_rss_from_youtube_playlist(args.url, podcast_url_base)
    print(f"Created '{rssfile}'")
