# TODO add to pip, update instructions

# TODO Pocket Casts assumes next episode release time - why? how can we control this?

# I'm not sure that those are still relevant, they're from before I started downloading from youtube:
# TODO podcastindex.org doesn't play, or download
# TODO Mac's podcast takes 30 minutes to start playing (Daniel's report in Discord)

import argparse
import json
import shutil
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
from podtuber import kalner_parser, bneidavid_parser, meirtv_parser, hakotel_parser, shaveihevron_parser, linked_feed
from podtuber.cache import cache
from podtuber.dedup import deduplicate
from podtuber.index_page import write_index
from podtuber import presentation
from podtuber.wordpress import remember_answers, save_snapshots, set_snapshots_url, stale_sites

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('podtuber')

example_config_toml_url = 'https://github.com/ZvikaZ/podtuber/blob/master/config.toml'


def get_parsers(url, podcast_config=None):
    netloc = urlparse(url).netloc
    if netloc == 'www.youtube.com':
        if urlparse(url).path == '/playlist':
            return [YoutubePlaylistParser(url)]
        else:
            return [YoutubeSingleParser(url)]
    elif netloc in ('www.haravyosefkalner.com', 'haravyosefkalner.com'):
        return kalner_parser.get_series_parsers(url)
    elif netloc in ('www.bneidavid.org', 'bneidavid.org'):
        return bneidavid_parser.get_series_parsers(url, (podcast_config or {}).get('topics', ()),
                                                   (podcast_config or {}).get('split_by_year', False))
    elif netloc in ('www.meirtv.com', 'meirtv.com'):
        return meirtv_parser.get_series_parsers(url, (podcast_config or {}).get('rav'),
                                                (podcast_config or {}).get('topics', ()),
                                                (podcast_config or {}).get('split', ()))
    elif netloc in ('www.hakotel.org.il', 'hakotel.org.il'):
        return hakotel_parser.get_series_parsers(url)
    elif netloc in ('www.shaveihevron.org', 'shaveihevron.org'):
        return shaveihevron_parser.get_series_parsers(url, (podcast_config or {}).get('rav'))
    else:
        logger.error(f'Unsupported playlist: {url}\n'
                     'Currently only YouTube, haravyosefkalner.com, bneidavid.org, meirtv.com, hakotel.org.il and '
                     'shaveihevron.org are supported. You can open an issue, maybe your parser will be added.')
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
        # an entry is either a url of a source (a playlist, a rav's page...), or podcasts that already exist (feeds)
        for url in podcast_config.get('feeds') or [podcast_config['url']]:
            try:
                if 'feeds' in podcast_config:
                    found = linked_feed.get_parsers(url, podcast_config['rav'], podcast_config.get('source', ''),
                                                    podcast_config.get('title_include'),
                                                    podcast_config.get('title_exclude'),
                                                    podcast_config.get('title_language'),
                                                    podcast_config.get('series', ()))
                else:
                    found = get_parsers(url, podcast_config)
            except Exception as err:
                logger.exception(f"Couldn't read {url}")
                failures[url] = f'{type(err).__name__}: {err}'
                keep_published_feeds(published.get(url, []), config['general']['base_url'], output_dir)
                continue
            published[url] = [feed_id(parser) for parser in found
                              if podcast_config.get('publish') or not hasattr(parser, 'get_linked_feed_url')]
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
    """
    The parser's podcast, written as a feed (unless it's a podcast that already exists elsewhere): named, titled and
    described for podcast apps, with its own artwork; a course numbered, for apps to play in order
    """
    logger.info(f'Handling playlist {parser.get_name()}')
    base_url = config['general']['base_url'].rstrip('/')
    rss_filename = f'{feed_id(parser)}.rss'
    linked = hasattr(parser, 'get_linked_feed_url') and not podcast_config.get('publish')
    rav = podcast_config.get('rav') or parser.get_owner_name()
    source = getattr(parser, 'get_source_name', lambda: '')()
    name = presentation.short_name(parser.get_name(), rav)
    course = not linked and presentation.is_course(name)

    podcast = Podcast()
    podcast.name = name + getattr(parser, 'name_suffix', '')  # set when told apart from a duplicate
    podcast.website = parser.get_website()
    podcast.explicit = False  # will be updated if one of the episodes is True
    podcast.authors = parser.get_authors()
    try:
        podcast.category = Category(podcast_config['category'], podcast_config.get('subcategory'))
    except KeyError:
        pass
    podcast.feed_url = f'{base_url}/{rss_filename}'
    if podcast_config.get('owner_mail'):
        podcast.owner = Person(parser.get_owner_name(), podcast_config.get('owner_mail'))
    # TODO set automatically (e.g., https://github.com/pytube/pytube/issues/1742)
    podcast.language = podcast_config.get('language')

    available = []
    for parsed_episode in parser.get_episodes():
        try:
            parsed_episode.check_availability()
        except Exception as err:
            logger.warning(f"Skipping '{parsed_episode.get_title()}' ({parsed_episode.get_link()}) because of: {err}")
        else:
            available.append(parsed_episode)
    for number, parsed_episode in enumerate(available, 1):
        episode = podcast.add_episode()
        original_title, summary = parsed_episode.get_title(), parsed_episode.get_summary()
        episode.original_title, episode.original_summary = original_title, summary  # for the index page
        if linked:  # its titles are its publisher's
            episode.title, episode.summary = original_title, htmlencode(summary)
        else:
            episode.title = presentation.episode_title(original_title, name, rav, number if course else None)
            note = presentation.episode_note(number if course else None, len(available), name, rav, source)
            episode.summary = htmlencode('\n'.join(part for part in (summary, original_title, note) if part))
        episode.publication_date = parsed_episode.get_publication_date()
        episode.explicit = parsed_episode.get_explicit()
        if episode.explicit:
            podcast.explicit = True
        episode.media = parsed_episode.get_media(base_url=base_url, series_title=feed_id(parser))
        episode.id = parsed_episode.get_id()
        episode.link = parsed_episode.get_link()
        episode.authors = parsed_episode.get_authors()

    podcast.missing = getattr(parser, 'missing_count', lambda: 0)()
    podcast.course = course
    podcast.years = presentation.years_span([episode.publication_date.date() for episode in podcast.episodes])
    if linked:  # a podcast that already exists is subscribed to at its source
        podcast.description = parser.get_description()
        podcast.image = podcast_config.get('image') or parser.get_image()
        podcast.feed_url = parser.get_linked_feed_url()
        return podcast
    podcast.description = presentation.channel_description(name, rav, source, podcast.website, len(available),
                                                           podcast.missing, podcast.years, base_url)
    image = podcast_config.get('image') or parser.get_image()
    # (a portrait: logos, such as the Bnei David one some rabbis' podcasts have instead, aren't drawn)
    portrait = Path(config['general'].get('static_dir', 'static')) / image.removeprefix(base_url + '/')         if image and image.startswith(base_url + '/') and not image.endswith('.png') else None
    art = f'{presentation.ART_DIR}/{feed_id(parser)}.jpg'
    presentation.make_artwork(output_dir / art, name, rav, source, portrait)
    podcast.image = f'{base_url}/{art}'
    podcast.rss_file(str(output_dir / rss_filename))
    if course:
        mark_as_course(output_dir / rss_filename)
    logger.info(f"Created '{output_dir / rss_filename}'\n")
    return podcast


def mark_as_course(path):
    """
    Tells podcast apps the feed is a course, to list and play from its first lesson (itunes:type serial), and
    numbers its lessons (itunes:episode), which podgen can't write itself
    """
    rss = path.read_text(encoding='utf8')
    rss = rss.replace('</language>', '</language>\n    <itunes:type>serial</itunes:type>', 1)
    parts = rss.split('</item>')
    rss = ''.join(f'{part}  <itunes:episode>{number}</itunes:episode>\n    </item>' for number, part in
                  enumerate(parts[:-1], 1)) + parts[-1]
    path.write_text(rss, encoding='utf8')


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
    if Path(config['general'].get('static_dir', 'static')).is_dir():
        shutil.copytree(config['general'].get('static_dir', 'static'), output_dir, dirs_exist_ok=True)
    set_snapshots_url(config['general'].get('snapshots_url'))
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
    write_index([{'podcast': podcast, 'name': podcast.name.removesuffix(getattr(parser, 'name_suffix', '')),
                  'feed_id': feed_id(parser), 'source': getattr(parser, 'get_source_name', lambda: '')(),
                  'rav': podcast_config.get('rav') or parser.get_owner_name(),
                  'rav_image': podcast_config.get('image') or parser.get_image()}
                 for (parser, podcast), (_, podcast_config) in zip(podcasts, parsers)
                 if parser in listed and podcast.episodes], output_dir / 'index.html',
                title=config['general'].get('title', 'Podcasts'), lang=config['general'].get('language', 'en'),
                base_url=config['general']['base_url'], stale=stale_sites())
    logger.info(f"Created '{output_dir / 'index.html'}'")
    # published alongside, so a run's problems can be seen without access to its log
    (output_dir / 'status.json').write_text(json.dumps({
        'updated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'failures': failures,
        'stale': stale_sites(),  # sites read from their last answers, so without their newest lessons
    }, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()
