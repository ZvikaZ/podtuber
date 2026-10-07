# TODO add to pip, update instructions

# TODO Pocket Casts assumes next episode release time - why? how can we control this?

# I'm not sure that those are still relevant, they're from before I started downloading from youtube:
# TODO podcastindex.org doesn't play, or download
# TODO Mac's podcast takes 30 minutes to start playing (Daniel's report in Discord)

import argparse
import json
import logging
import sys
import tomli
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from podgen import Podcast, Person, Category, htmlencode
from pathvalidate import sanitize_filename

from podtuber.youtube_parser import YoutubePlaylistParser, YoutubeSingleParser
from podtuber import kalner_parser, bneidavid_parser, meirtv_parser, hakotel_parser
from podtuber.cache import cache
from podtuber.dedup import deduplicate
from podtuber.index_page import write_index
from podtuber.wordpress import remember_answers, save_snapshots, stale_sites

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
    elif netloc in ('www.bneidavid.org', 'bneidavid.org'):
        return bneidavid_parser.get_series_parsers(url)
    elif netloc in ('www.meirtv.com', 'meirtv.com'):
        return meirtv_parser.get_series_parsers(url)
    elif netloc in ('www.hakotel.org.il', 'hakotel.org.il'):
        return hakotel_parser.get_series_parsers(url)
    else:
        logger.error(f'Unsupported playlist: {url}\n'
                     'Currently only YouTube, haravyosefkalner.com, bneidavid.org, meirtv.com and hakotel.org.il are '
                     'supported. You can open an issue, maybe your parser will be added.')
        sys.exit()


def feed_id(parser):
    # parsers whose titles make poor URLs provide their own stable feed id
    if hasattr(parser, 'get_feed_id'):
        return parser.get_feed_id()
    return sanitize_filename(parser.get_name()).replace(' ', '_')


def read_sources(config, output_dir):
    """
    The parsers of all the podcasts. A source that fails (say, a site that's down, or that refuses this server)
    doesn't stop the others; its feeds from the previous run are published again, so subscriptions keep working.
    """
    published = cache.section('feeds')  # each source's feed ids, as last published
    parsers, failures = [], {}
    for podcast_config in config.get('podcasts'):
        url = podcast_config['url']
        try:
            found = get_parsers(url)
        except Exception as err:
            logger.exception(f"Couldn't read {url}")
            failures[url] = f'{type(err).__name__}: {err}'
            keep_published_feeds(published.get(url, []), config['general']['base_url'], output_dir)
            continue
        published[url] = [feed_id(parser) for parser in found]
        parsers += [(parser, podcast_config) for parser in found]
    return parsers, failures


def keep_published_feeds(feed_ids, base_url, output_dir):
    for feed in feed_ids:
        try:
            with urllib.request.urlopen(f'{base_url.rstrip("/")}/{feed}.rss', timeout=60) as response:
                (output_dir / f'{feed}.rss').write_bytes(response.read())
        except Exception as err:
            logger.warning(f"Couldn't keep {feed}.rss: {err}")


def create_rss(parser, podcast_config, config, output_dir):
    logger.info(f'Handling playlist {parser.get_name()}')

    sanitized_title = sanitize_filename(parser.get_name()).replace(' ', '_')
    rss_filename = f'{feed_id(parser)}.rss'

    podcast = Podcast()
    podcast.name = parser.get_name() + getattr(parser, 'name_suffix', '')  # set when told apart from a duplicate
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
            episode.title = parsed_episode.get_title()
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
    arguments = argparse.ArgumentParser(description='Create podcast .rss files, as config.toml says')
    arguments.add_argument('--snapshot', action='store_true',
                           help="also save snapshots of the sites that some servers can't read (see config.toml)")
    snapshot = arguments.parse_args().snapshot
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
    cache.load(output_dir, config['general']['base_url'])
    parsers, failures = read_sources(config, output_dir)
    remember_answers()
    cache.save()
    if snapshot:
        save_snapshots()
    # duplicates are only left out of the index: their feeds are still written, so that a subscription never
    # goes stale when the other copy of a series becomes the more complete one
    listed = deduplicate([parser for parser, _ in parsers])
    podcasts = [(parser, create_rss(parser, podcast_config, config, output_dir))
                for parser, podcast_config in parsers]
    cache.save()
    # the index names each podcast's source itself, so it uses the names without the told-apart suffix
    write_index([(podcast, parser.get_name(), getattr(parser, 'get_source_name', lambda: '')())
                 for parser, podcast in podcasts if parser in listed and podcast.episodes], output_dir / 'index.html',
                title=config['general'].get('title', 'Podcasts'), lang=config['general'].get('language', 'en'))
    logger.info(f"Created '{output_dir / 'index.html'}'")
    # published alongside, so a run's problems can be seen without access to its log
    (output_dir / 'status.json').write_text(json.dumps({
        'updated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'failures': failures,
        'stale': stale_sites(),  # sites read from their last answers, so without their newest lessons
    }, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()
