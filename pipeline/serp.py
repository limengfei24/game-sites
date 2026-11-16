import logging
from urllib.parse import urlparse

import requests

from .config import env

log = logging.getLogger(__name__)


def competition(keyword, slug):
    """返回谷歌前 10 名里「专门做这个游戏的站」的数量；没配 SERPER_API_KEY 时返回 None。"""
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
    dedicated = 0
    for result in resp.json().get("organic", []):
        host = urlparse(result.get("link", "")).hostname or ""
        if compact and compact in host.replace("-", "").replace(".", ""):
            dedicated += 1
    return dedicated
