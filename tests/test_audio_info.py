import struct
import unittest
from unittest.mock import MagicMock, patch

from podtuber import audio_info

FTYP = struct.pack('>I', 24) + b'ftyp3gp4' + b'\0' * 4 + b'isom3gp4'


def mvhd(seconds, version=0, timescale=1000):
    times = struct.pack('>QQIQ', 0, 0, timescale, seconds * timescale) if version else \
        struct.pack('>IIII', 0, 0, timescale, seconds * timescale)
    body = bytes([version, 0, 0, 0]) + times + b'\0' * 80
    return struct.pack('>I', 8 + len(body)) + b'mvhd' + body


def response(content, size):
    answer = MagicMock(status_code=206, headers={'Content-Range': f'bytes 0-{len(content) - 1}/{size}'},
                       content=content)
    answer.iter_content.return_value = [content]
    return answer


class Mp4Test(unittest.TestCase):
    def test_mp4_duration_is_read_from_its_movie_header(self):
        self.assertEqual(471, audio_info.mp4_duration(b'moov' + mvhd(471)))
        self.assertEqual(3600, audio_info.mp4_duration(b'moov' + mvhd(3600, version=1)))
        self.assertIsNone(audio_info.mp4_duration(FTYP + b'mdat' + b'\0' * 100))

    @patch('podtuber.audio_info._session')
    def test_an_mp4_with_its_index_last_is_read_from_its_end(self, session):
        # Nach Yomi's lessons: AAC in an mp4 (some named .mp4 are mp3s), whose index follows the audio
        head = FTYP + b'mdat' + b'\0' * (audio_info.HEAD_SIZE - len(FTYP) - 4)
        tail = b'\0' * 100 + b'moov' + mvhd(471)
        session.return_value.get.side_effect = [response(head, 7705279), response(tail, 7705279)]

        self.assertEqual({'size': 7705279, 'type': 'audio/x-m4a', 'duration': 471},
                         audio_info._probe('https://example.com/a.mp4'))

    @patch('podtuber.audio_info.TinyTag')
    @patch('podtuber.audio_info._session')
    def test_a_variable_bitrate_mp3_without_its_length_is_timed_by_its_size(self, session, tinytag):
        # Nach Yomi's יהושע ג: 1.9MB at 44kbps, of which the frames first read last 24 seconds
        session.return_value.get.return_value = response(b'\xff\xfb\x90\xc4' + b'\0' * 100, 1937122)
        tinytag.get.return_value = MagicMock(duration=24.1, bitrate=43.787)

        self.assertEqual({'size': 1937122, 'duration': 353.9}, audio_info._probe('https://example.com/a.mp3'))


if __name__ == '__main__':
    unittest.main()
