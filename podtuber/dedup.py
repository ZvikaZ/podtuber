"""
The same series of lessons can be published on several sites. Two lessons are the same recording when they're the
same file (the same size and duration; the sites' dates for it may differ by weeks), or when their durations and
their dates match. Then, for each two series from different sources that share lessons:
- when they're identical, only the first one (in config.toml's order) is listed,
- when one has all the other's lessons and more, only the more complete one is listed,
- otherwise both are listed, and each one's name says where it's from.

Parsers take part by providing get_source_name(), and get_recordings(): a (date, duration in seconds, size in bytes)
per episode, any of which may be None when unknown.
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

DURATION_TOLERANCE = 2  # seconds, for copies of a recording that were encoded separately
SAME_FILE_DURATION_TOLERANCE = 0.5  # seconds
DATE_TOLERANCE = timedelta(days=2)
MIN_SHARED = 2  # fewer shared lessons than this are taken as a coincidence


def deduplicate(parsers):
    """The parsers worth listing. Those that must be told apart get a name_suffix."""
    candidates = [parser for parser in parsers if hasattr(parser, 'get_recordings')]
    recordings = {parser: parser.get_recordings() for parser in candidates}
    dropped, overlapping = set(), []
    for i, first in enumerate(candidates):
        for second in candidates[i + 1:]:
            if first in dropped or second in dropped or first.get_source_name() == second.get_source_name():
                continue
            first_in_second = count_shared(recordings[first], recordings[second])
            second_in_first = count_shared(recordings[second], recordings[first])
            if min(first_in_second, second_in_first) < MIN_SHARED:
                continue
            description = (f"'{first.get_name()}' ({first_in_second} of {len(recordings[first])} lessons shared) "
                           f"and '{second.get_name()}' ({second_in_first} of {len(recordings[second])})")
            if first_in_second == len(recordings[first]) and second_in_first == len(recordings[second]):
                logger.info(f'Identical: {description}; listing the first')
                dropped.add(second)
            elif second_in_first == len(recordings[second]):
                logger.info(f'The first is more complete: {description}; listing the first')
                dropped.add(second)
            elif first_in_second == len(recordings[first]):
                logger.info(f'The second is more complete: {description}; listing the second')
                dropped.add(first)
            else:
                logger.info(f'Partly shared: {description}; listing both')
                overlapping.append((first, second))

    for pair in overlapping:
        if not dropped.intersection(pair):
            for parser in pair:
                parser.name_suffix = f' ({parser.get_source_name()})'
    return [parser for parser in parsers if parser not in dropped]


def count_shared(recordings, others):
    """how many of the recordings are also among the others"""
    by_duration = {}
    for other in others:
        if other[1] is not None:
            by_duration.setdefault(round(other[1]), []).append(other)
    return sum(1 for recording in recordings
               if recording[1] is not None
               and any(same_recording(recording, other)
                       for seconds in range(round(recording[1]) - DURATION_TOLERANCE,
                                            round(recording[1]) + DURATION_TOLERANCE + 1)
                       for other in by_duration.get(seconds, [])))


def same_recording(first, second):
    (first_date, first_duration, first_size), (second_date, second_duration, second_size) = first, second
    if first_size and first_size == second_size and abs(first_duration - second_duration) <= SAME_FILE_DURATION_TOLERANCE:
        return True
    # many lectures last about as long as some other one, so a duration alone isn't enough
    return (abs(first_duration - second_duration) <= DURATION_TOLERANCE and first_date is not None
            and second_date is not None and abs(first_date - second_date) <= DATE_TOLERANCE)
