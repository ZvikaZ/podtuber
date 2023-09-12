# TODO currently it issues a warning because of file extension mismatch,
# it works under Pocket Casts, might prove problematic for other apps

# TODO podcastindex.org doesn't play, or download
# TODO Mac's podcast takes 30 minutes to start playing (Daniel's report in Discord)
# TODO Pocket Casts assumes next episode release time - why? how can we control this?


from urllib.parse import urlparse
from datetime import timedelta
import pytz
import argparse

from podgen import Podcast, Media, Person, htmlencode
from pytube import Playlist
from pathvalidate import sanitize_filename


def clean_jpg_url(url):
    return urlparse(url)._replace(query='').geturl()


def create_rss_from_youtube_playlist(url):
    playlist = Playlist(url)
    print(playlist.title)
    assert playlist.videos

    podcast = Podcast(
        name=playlist.title,
        description=playlist.description,
        website=playlist.playlist_url,
        explicit=any([v.age_restricted for v in playlist.videos]),
        image=clean_jpg_url(playlist.videos[0].thumbnail_url),  # TODO make sure it's square, at least 1400x1400
        authors=[Person(playlist.owner)],
        # TODO maybe set language from ytcfg fields - few have 'en'. needs investigation
        language='en-US',

        # TODO support these?
        # owner=Person(playlist.owner), # needs mail
        # feed_url=...,
        # category=...,
    )

    for video in playlist.videos:
        try:
            video.check_availability()
        except Exception as err:
            print(f"Skipping '{url}' because of: {err}")
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
            stream = video.streams.get_audio_only()  # returns best mp4 audio stream
            episode.media = Media(stream.url,
                                  type='audio/x-m4a',
                                  size=stream.filesize,
                                  duration=timedelta(seconds=video.length))
            episode.id = video.watch_url
            episode.link = video.watch_url
            episode.authors = [Person(video.author)]

    filename = f'{sanitize_filename(playlist.title)}.rss'.replace(' ', '_')
    podcast.rss_file(filename)
    return filename


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Creates a podcast .rss file from YouTube playlist")
    parser.add_argument('url', help="YouTube playlist's URL")
    args = parser.parse_args()

    rssfile = create_rss_from_youtube_playlist(args.url)
    print(f"Created '{rssfile}'")
