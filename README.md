podtuber
========

Simple Python application to create podcast `.rss` files from YouTube playlists,
and from the recorded lessons on [haravyosefkalner.com](https://www.haravyosefkalner.com/shiurim),
[bneidavid.org](https://bneidavid.org), [meirtv.com](https://meirtv.com) and [hakotel.org.il](https://www.hakotel.org.il).

A series published on several sites becomes a single podcast when the sites have the same lessons
(the same dates and durations), or when one has all of the other's lessons and more.

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
`config.toml` writes the feeds, and an `index.html` listing them, to `output_dir`,
along with a `cache.json` of what doesn't change between runs (such as each lesson's audio and duration),
which the next run reads back from `base_url`, so it only fetches what's new.
The `Publish podcasts` workflow in this repository runs `podtuber` daily (and on every push),
and deploys that folder to GitHub Pages, at `base_url`.
To use it in a fork, set the repository's *Settings → Pages → Source* to *GitHub Actions*, and update `base_url`.

Sites that refuse GitHub's servers (Meir TV) are read from `snapshots/` there;
run `./refresh-snapshots.sh` on another computer to refresh and push them.

GitHub pauses scheduled workflows in repositories with no activity for 60 days,
so the workflow re-enables itself on every run, which resets that timer.
