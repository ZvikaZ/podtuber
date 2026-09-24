# TODO add to pip, update instructions

# TODO Pocket Casts assumes next episode release time - why? how can we control this?

# I'm not sure that those are still relevant, they're from before I started downloading from youtube:
# TODO podcastindex.org doesn't play, or download
# TODO Mac's podcast takes 30 minutes to start playing (Daniel's report in Discord)

import logging
import sys
import tomli
from pathlib import Path
from urllib.parse import urlparse

from podgen import Podcast, Person, Category, htmlencode
from pathvalidate import sanitize_filename

from podtuber.youtube_parser import YoutubePlaylistParser, YoutubeSingleParser
from podtuber import kalner_parser
from podtuber.index_page import write_index

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('podtuber')

example_config_toml_url = 'https://github.com/ZvikaZ/podtuber/blob/master/config.toml'


def get_parsers(url):
    netloc = urlparse(url).netloc
    if netloc == 'www.youtube.com':
        if urlparse(url).path == '/playlist':
            return [YoutubePlaylistParser(url)]
        else:
            return [YoutubeSingleParser(url)]
    elif netloc in ('www.haravyosefkalner.com', 'haravyosefkalner.com'):
        return kalner_parser.get_series_parsers(url)
    else:
        logger.error(f'Unsupported playlist: {url}\n'
                     'Currently only YouTube and haravyosefkalner.com are supported. You can open an issue, maybe '
                     'your parser will be added.')
        sys.exit()


def create_rss(parser, podcast_config, config, output_dir):
    logger.info(f'Handling playlist {parser.get_name()}')

    sanitized_title = sanitize_filename(parser.get_name()).replace(' ', '_')
    # parsers whose titles make poor URLs provide their own stable feed id
    feed_id = parser.get_feed_id() if hasattr(parser, 'get_feed_id') else sanitized_title
    rss_filename = f'{feed_id}.rss'

    podcast = Podcast()
    podcast.name = parser.get_name()
    podcast.description = parser.get_description()
    podcast.website = parser.get_website()
    podcast.explicit = False  # will be updated if one of the episodes is True
    podcast.image = podcast_config.get('image') or parser.get_image()
    podcast.authors = parser.get_authors()

    try:
        podcast.category = Category(podcast_config['category'], podcast_config.get('subcategory'))
    except KeyError:
        pass
    podcast.feed_url = f'{config["general"]["base_url"].strip("/")}/{rss_filename}'
    if podcast_config.get('owner_mail'):
        podcast.owner = Person(parser.get_owner_name(), podcast_config.get('owner_mail'))

    # TODO set automatically (e.g., https://github.com/pytube/pytube/issues/1742)
    podcast.language = podcast_config.get('language')

    for parsed_episode in parser.get_episodes():
        try:
            parsed_episode.check_availability()
        except Exception as err:
            logger.warning(f"Skipping '{parsed_episode.get_title()}' ({parsed_episode.get_link()}) because of: {err}")
        else:
            episode = podcast.add_episode()
            # print(clean_jpg_url(v.thumbnail_url))    #TODO use this for episodes as well?
            episode.title = htmlencode(parsed_episode.get_title())
            episode.summary = htmlencode(parsed_episode.get_summary())
            episode.publication_date = parsed_episode.get_publication_date()
            episode.explicit = parsed_episode.get_explicit()
            if episode.explicit:
                podcast.explicit = True
            episode.media = parsed_episode.get_media(base_url=config["general"]["base_url"],
                                                     series_title=sanitized_title)
            episode.id = parsed_episode.get_id()
            episode.link = parsed_episode.get_link()
            episode.authors = parsed_episode.get_authors()

    podcast.rss_file(str(output_dir / rss_filename))
    logger.info(f"Created '{output_dir / rss_filename}'\n")
    return podcast


def main():
    try:
        with open("config.toml", mode="rb") as fp:
            config = tomli.load(fp)
    except FileNotFoundError:
        logger.error('Missing config.toml file in current directory. You can use '
                     f'{example_config_toml_url} as a reference.')
        sys.exit()
    except Exception as err:
        logger.error(err)
        logger.error(f'Illegal config.toml file. You can use {example_config_toml_url} as a reference.')
        sys.exit()
    output_dir = Path(config['general'].get('output_dir', '.'))
    output_dir.mkdir(parents=True, exist_ok=True)
    podcasts = []
    for podcast_config in config.get('podcasts'):
        for parser in get_parsers(podcast_config['url']):
            podcasts.append(create_rss(parser, podcast_config, config, output_dir))
    write_index(podcasts, output_dir / 'index.html', title=config['general'].get('title', 'Podcasts'),
                lang=config['general'].get('language', 'en'))
    logger.info(f"Created '{output_dir / 'index.html'}'")


if __name__ == '__main__':
    main()
