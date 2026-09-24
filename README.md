podtuber
========

Simple Python application to create podcast `.rss` files from YouTube playlists,
and from the recorded lessons on [haravyosefkalner.com](https://www.haravyosefkalner.com/shiurim).

Installation
------------
You might want to start with creating a Python virtual env. For example:
```shell
conda create -n podtuber python=3
conda activate podtuber
```

and then:
```shell
pip install podtuber
```
you might need to logout and login, in order for the new `podtuber` command to be updated in `PATH`.

Usage
-----
- copy the [example config.toml](https://github.com/ZvikaZ/podtuber/blob/master/config.toml) to your working directory, and modify it as needed (it's thoroughly commented),
- and run: 
```shell
podtuber
```

Notes
-----
- The .rss file needs to be served from an HTTP(S) server. Running the server is out of the scope of this tool.

- Also, you might want to periodically update the .rss file (because the playlist might have been updated).
It can be achieved for example by using a Cron job to run `podtuber` on regular times.

Development
-----------
The project is managed with [uv](https://docs.astral.sh/uv/):
```shell
uv sync
uv run podtuber
```

Publishing with GitHub Pages
----------------------------
`config.toml` writes the feeds, and an `index.html` listing them, to `output_dir`.
The `Publish podcasts` workflow in this repository runs `podtuber` daily (and on every push),
and deploys that folder to GitHub Pages, at `base_url`.
To use it in a fork, set the repository's *Settings → Pages → Source* to *GitHub Actions*, and update `base_url`.

Note that GitHub pauses scheduled workflows in repositories with no activity for 60 days;
re-enable it from the *Actions* tab if that happens.
