import logging
import re
from datetime import datetime
from urllib.parse import urlparse

import requests

from .config import env

log = logging.getLogger(__name__)

# 官方 / 平台 / 视频 / 论坛页面不算抢排名的竞争对手
PLATFORMS = ("youtube.com", "reddit.com", "roblox.com", "steampowered.com", "steamcommunity.com",
             "steamdb.info", "wikipedia.org", "twitter.com", "x.com", "tiktok.com", "facebook.com",
             "instagram.com", "discord.com", "apps.apple.com", "play.google.com", "epicgames.com",
             "playstation.com", "xbox.com", "nintendo.com", "itch.io", "twitch.tv")


def _days_ago(text):
    """把 Serper 的 "3 days ago" / "Nov 1, 2026" 转成天数；认不出来返回 None。"""
    if not text:
        return None
    m = re.match(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return n * {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[unit]
    for fmt in ("%b %d, %Y", "%d %b %Y"):
        try:
            return (datetime.now() - datetime.strptime(text, fmt)).days
        except ValueError:
            pass
    return None


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def competition(keyword, game_name, slug):
    """谷歌前 10 名里的竞争情况；没配 SERPER_API_KEY 或查询失败时返回 None。

    pages: 标题里带游戏名的攻略/资讯页（不含官方、平台、视频、论坛）
    dedicated: 域名就是这个游戏名的专门站
    oldest_days: 这些竞争页里最早发布的距今天数
    """
    key = env("SERPER_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key},
            json={"q": keyword, "num": 10},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("SERP 查询失败 %s: %s", keyword, exc)
        return None

    compact = slug.replace("-", "")
    name = _tokens(game_name)
    pages, dedicated, ages = 0, 0, []
    for result in resp.json().get("organic", []):
        host = (urlparse(result.get("link", "")).hostname or "").removeprefix("www.")
        if any(host == p or host.endswith("." + p) for p in PLATFORMS):
            continue
        if compact and compact in host.replace("-", "").replace(".", ""):
            dedicated += 1
            continue
        if name and name <= _tokens(result.get("title", "")):
            pages += 1
            age = _days_ago(result.get("date"))
            if age is not None:
                ages.append(age)
    return {"pages": pages, "dedicated": dedicated, "oldest_days": max(ages) if ages else None}
