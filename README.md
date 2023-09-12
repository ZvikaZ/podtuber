podtuber
========

Simple Python application to create podcast `.rss` file from YouTube playlist.

usage
-----
- to get usage help, run: 
```shell
python podtuber/main.py -h
```
- or just get it running with a YouTube playlist URL, such as:
```shell
python podtuber/main.py https://www.youtube.com/playlist?list=PL9qFy7xdUfuTE4Xnzran_1ReI_Q0ofL3V
```

notes
-----
- The .rss file needs to be served from an HTTP(S) server. This is out of the scope of this tool.

- :Also, you might want to periodically update the .rss file (because the playlist might have been updated).
It can be achieved for example by using a Cron job to run podtuber on regular times.