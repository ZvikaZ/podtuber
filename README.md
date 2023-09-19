podtuber
========

Simple Python application to create podcast `.rss` files from YouTube playlists.

installation
------------
```shell
pip install git+https://github.com/ZvikaZ/podtuber.git
```

usage
-----
- copy the example `config.toml` to your working directory, and modify it as needed (it's thoroughly commented).
- and run: 
```shell
python podtuber/main.py
```

notes
-----
- The .rss file needs to be served from an HTTP(S) server. Running the server is out of the scope of this tool.

- :Also, you might want to periodically update the .rss file (because the playlist might have been updated).
It can be achieved for example by using a Cron job to run `podtuber` on regular times.