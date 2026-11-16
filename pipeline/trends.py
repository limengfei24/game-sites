import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from .config import normalize_keyword

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
HT = {"ht": "https://trends.google.com/trending/rss"}
GAMES_CATEGORY = 8


def fetch_trending_rss(geo):
    resp = requests.get(f"https://trends.google.com/trending/rss?geo={geo}", headers=UA, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.iter("item"):
        news = [
            {
                "title": n.findtext("ht:news_item_title", "", HT),
                "url": n.findtext("ht:news_item_url", "", HT),
                "source": n.findtext("ht:news_item_source", "", HT),
            }
            for n in item.findall("ht:news_item", HT)
        ]
        items.append({
            "keyword": item.findtext("title", "").strip(),
            "traffic": item.findtext("ht:approx_traffic", "", HT),
            "source": f"daily:{geo}",
            "news": news,
        })
    return items


def _trendreq():
    from pytrends.request import TrendReq
    return TrendReq(hl="en-US", tz=0, timeout=(10, 30))


def fetch_rising(seeds, geo, timeframe):
    pytrends = _trendreq()
    items = []
    for seed in seeds:
        try:
            pytrends.build_payload([seed], cat=GAMES_CATEGORY, timeframe=timeframe, geo=geo)
            rising = pytrends.related_queries().get(seed, {}).get("rising")
            if rising is not None:
                for _, row in rising.iterrows():
                    items.append({
                        "keyword": str(row["query"]),
                        "traffic": f"+{row['value']}%",
                        "source": f"rising:{seed}",
                        "news": [],
                    })
        except Exception as exc:
            log.warning("飙升词查询失败 seed=%s: %s", seed, exc)
        time.sleep(4)
    return items


def keyword_age_days(keyword, geo="US"):
    """估算一个词「火起来」多少天了：90 天曲线里第一次超过峰值 20% 的日期距今的天数。"""
    try:
        pytrends = _trendreq()
        pytrends.build_payload([keyword], timeframe="today 3-m", geo=geo)
        df = pytrends.interest_over_time()
    except Exception as exc:
        log.warning("无法获取 %s 的搜索曲线: %s", keyword, exc)
        return None
    if df is None or df.empty or keyword not in df:
        return None
    series = df[keyword]
    peak = series.max()
    if peak <= 0:
        return None
    started = series[series >= peak * 0.2].index[0].to_pydatetime().replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).days


def collect(cfg):
    tcfg = cfg["trends"]
    items = []
    for geo in tcfg["rss_geos"]:
        try:
            items += fetch_trending_rss(geo)
        except Exception as exc:
            log.warning("每日热搜 RSS 获取失败 geo=%s: %s", geo, exc)
    items += fetch_rising(tcfg["rising_seeds"], tcfg["rising_geo"], tcfg["rising_timeframe"])

    merged = {}
    for item in items:
        key = normalize_keyword(item["keyword"])
        if not key:
            continue
        if key in merged:
            merged[key]["news"] += item["news"]
            merged[key]["sources"].append(item["source"])
        else:
            merged[key] = {**item, "keyword": key, "sources": [item["source"]]}
    log.info("共收集到 %d 个去重后的趋势词", len(merged))
    return list(merged.values())
