"""给 AI 写内容用的游戏资料：Steam、Roblox、维基百科、YouTube 字幕。"""
import html
import logging
import os
import re
import tempfile
import uuid
from difflib import SequenceMatcher

import requests

from .config import env

log = logging.getLogger(__name__)

UA = {"User-Agent": "GameRadar/1.0 (+https://github.com)"}


def _tokens(name):
    name = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", name.lower())
    return re.findall(r"[a-z0-9]+", name)


def _name_matches(a, b, threshold=0.9):
    """按完整单词比较，避免 "GTA VI" 匹配到 "GTA: Vice City"、"GTA V" 或续作。"""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    return (len(ta) == len(tb) and ta[-1] == tb[-1]
            and SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio() >= threshold)


def _strip_html(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def steam(game_name):
    try:
        search = requests.get("https://store.steampowered.com/api/storesearch/",
                              params={"term": game_name, "cc": "us", "l": "english"},
                              headers=UA, timeout=30).json()
        item = next((i for i in search.get("items", []) if _name_matches(game_name, i["name"])), None)
        if not item:
            return None
        app = requests.get("https://store.steampowered.com/api/appdetails",
                           params={"appids": item["id"], "l": "english"},
                           headers=UA, timeout=30).json()[str(item["id"])]["data"]
    except Exception as exc:
        log.info("Steam 查询失败 %s: %s", game_name, exc)
        return None
    return {
        "source": "Steam store",
        "url": f"https://store.steampowered.com/app/{item['id']}/",
        "name": app.get("name"),
        "developers": app.get("developers"),
        "publishers": app.get("publishers"),
        "release_date": (app.get("release_date") or {}).get("date"),
        "is_free": app.get("is_free"),
        "price": (app.get("price_overview") or {}).get("final_formatted"),
        "platforms": [p for p, ok in (app.get("platforms") or {}).items() if ok],
        "genres": [g["description"] for g in app.get("genres", [])],
        "short_description": app.get("short_description"),
        "about": _strip_html(app.get("about_the_game"))[:6000],
        "header_image": app.get("header_image"),
    }


def roblox(game_name):
    try:
        search = requests.get("https://apis.roblox.com/search-api/omni-search",
                              params={"searchQuery": game_name, "sessionId": str(uuid.uuid4()), "pageType": "all"},
                              headers=UA, timeout=30).json()
        games = [c for g in search.get("searchResults", []) for c in g.get("contents", [])
                 if c.get("contentType") == "Game" and _name_matches(game_name, c.get("name", ""))]
        if not games:
            return None
        universe = games[0]["universeId"]
        data = requests.get("https://games.roblox.com/v1/games", params={"universeIds": universe},
                            headers=UA, timeout=30).json()["data"][0]
    except Exception as exc:
        log.info("Roblox 查询失败 %s: %s", game_name, exc)
        return None
    return {
        "source": "Roblox",
        "url": f"https://www.roblox.com/games/{data['rootPlaceId']}",
        "name": data["name"],
        "creator": data["creator"]["name"],
        "playing_now": data.get("playing"),
        "visits": data.get("visits"),
        "created": data.get("created", "")[:10],
        "updated": data.get("updated", "")[:10],
        "genre": data.get("genre"),
        "max_players": data.get("maxPlayers"),
        "description": (data.get("description") or "")[:4000],
        "platforms": "Roblox (PC, Mac, mobile, tablet, Xbox, PlayStation, VR)",
    }


def wikipedia(game_name):
    try:
        search = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
            "action": "query", "list": "search", "format": "json", "srlimit": 3,
            "srsearch": f"{game_name} video game",
        }).json()["query"]["search"]
        page = next((p for p in search if _name_matches(game_name, p["title"].split(" (")[0])), None)
        if not page:
            return None
        extract = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
            "action": "query", "prop": "extracts", "explaintext": 1, "format": "json",
            "titles": page["title"], "exchars": 6000,
        }).json()["query"]["pages"]
    except Exception as exc:
        log.info("维基百科查询失败 %s: %s", game_name, exc)
        return None
    text = next(iter(extract.values())).get("extract", "")
    return {"source": "Wikipedia", "url": f"https://en.wikipedia.org/wiki/{page['title'].replace(' ', '_')}",
            "text": text}


def _cookie_file():
    """YouTube 对机器人要求登录；在 YOUTUBE_COOKIES 里放 Netscape 格式的 cookies.txt 内容即可绕过。"""
    cookies = env("YOUTUBE_COOKIES")
    if not cookies:
        return None
    path = os.path.join(tempfile.gettempdir(), "yt_cookies.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(cookies)
    return path


def find_videos(query, limit):
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    except Exception as exc:
        log.warning("YouTube 搜索失败 %s: %s", query, exc)
        return []
    return [
        {"id": e["id"], "title": e.get("title", ""), "channel": e.get("channel") or e.get("uploader", "")}
        for e in info.get("entries", []) if e and e.get("id")
    ]


def youtube_transcript(video_id):
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    cookie_file = _cookie_file()
    if cookie_file:
        opts["cookiefile"] = cookie_file
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except Exception as exc:
        log.info("读取视频 %s 失败（没配 YOUTUBE_COOKIES 时通常会被 YouTube 拦截）: %s",
                 video_id, str(exc).splitlines()[0][:160])
        return ""

    for group in ("subtitles", "automatic_captions"):
        tracks = (info.get(group) or {}).get("en") or (info.get(group) or {}).get("en-US") or []
        url = next((t["url"] for t in tracks if t.get("ext") == "json3"), None)
        if not url:
            continue
        try:
            events = requests.get(url, timeout=30).json().get("events", [])
        except Exception:
            continue
        text = " ".join(s.get("utf8", "") for e in events for s in (e.get("segs") or []))
        return re.sub(r"\s+", " ", text).strip()
    return ""
