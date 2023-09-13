# TODO Google Podcast Index (maybe) needs owner (i.e., mail) in order to index
# TODO Pocket Casts assumes next episode release time - why? how can we control this?

# I'm not sure that those are still relevant, they're from before I started downloading from youtube:
# TODO podcastindex.org doesn't play, or download
# TODO Mac's podcast takes 30 minutes to start playing (Daniel's report in Discord)

from urllib.parse import urlparse, quote
from pathlib import Path
import pytz
import sys

from podgen import Podcast, Media, Person, Category, htmlencode
from pytube import Playlist
from pathvalidate import sanitize_filename
import tomli


def clean_jpg_url(url):
    return urlparse(url)._replace(query='').geturl()


def get_media_from_youtube(config, series_title, stream):
    path = Path('files') / series_title
    path.mkdir(parents=True, exist_ok=True)
    stream.subtype = 'm4a'
    file = Path(stream.download(output_path=path))
    media = Media(
        url=f'{config["general"]["base_url"]}/{quote((path / file.name).as_posix())}',
        size=stream.filesize,
    )
    media.populate_duration_from(file)
    return media


def create_rss_from_youtube_playlist(podcast_config, config):
    playlist = Playlist(podcast_config['url'])
    print(playlist.title)
    assert playlist.videos

    sanitized_title = sanitize_filename(playlist.title).replace(' ', '_')
    rss_filename = f'{sanitized_title}.rss'

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
    podcast.category = Category(podcast_config.get('category'), podcast_config.get('subcategory'))
    podcast.feed_url = f'{config["general"]["base_url"].strip("/")}/{rss_filename}'
    if podcast_config.get('owner_mail'):
        podcast.owner = Person(playlist.owner, podcast_config.get('owner_mail'))

    # TODO set automatically (e.g., https://github.com/pytube/pytube/issues/1742)
    podcast.language = podcast_config.get('language')

    for video in playlist.videos:
        try:
            video.check_availability()
        except Exception as err:
            print(f"Skipping '{playlist.playlist_url}' because of: {err}")
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
            episode.media = get_media_from_youtube(config, sanitized_title, stream)
            episode.id = video.watch_url
            episode.link = video.watch_url
            episode.authors = [Person(video.author)]

    podcast.rss_file(rss_filename)
    return rss_filename


if __name__ == '__main__':
    try:
        with open("config.toml", mode="rb") as fp:
            config = tomli.load(fp)
    except FileNotFoundError:
        sys.exit(
            'Missing config.toml file in current directory. You can use https://github.com/zvikaZ/podtuber/config.toml as a reference.')
    except Exception as err:
        print(err)
        sys.exit(
            f'Illegal config.toml file. You can use https://github.com/zvikaZ/podtuber/config.toml as a reference.')

    for podcast_config in config.get('podcasts'):
        rssfile = create_rss_from_youtube_playlist(podcast_config, config)
        print(f"Created '{rssfile}'\n")
