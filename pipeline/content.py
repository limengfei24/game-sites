import json
import logging

from . import sources
from .llm import chat_json
from .state import now_iso

log = logging.getLogger(__name__)

SYSTEM = """You write SEO landing pages for a website dedicated to one newly trending game.
Use ONLY facts supported by the provided sources (store pages, Wikipedia, YouTube transcripts or notes
taken while watching the videos,
video titles and descriptions, news headlines). Ignore self-promotion in video descriptions
(subscribe links, sponsors, social media); a code from a video description is only a fact if the
description clearly presents it as a code for this game. Never invent release dates, prices, platforms, developers or
controls; if the sources don't say, leave that field empty or omit the item. Write naturally for
players, no fluff, no keyword stuffing. Write in language: {language}.

Return JSON:
{{
  "title": "<SEO title, <= 60 chars, starts with the game name>",
  "meta_description": "<= 155 chars",
  "tagline": "<one sentence hook>",
  "overview": ["<paragraph>", "..."],
  "facts": [{{"label": "Developer|Platforms|Release|Genre|Price|...", "value": "..."}}],
  "how_to_play": ["<step>", "..."],
  "controls": [{{"input": "<key/button>", "action": "..."}}],
  "tips": ["<tip>", "..."],
  "faq": [{{"q": "...", "a": "..."}}]
}}"""


def generate(candidate, rec, cfg):
    game_name = rec.get("game_name") or candidate["keyword"]
    ccfg = cfg["content"]

    store_pages = [s for s in (sources.steam(game_name), sources.roblox(game_name), sources.wikipedia(game_name)) if s]

    videos = sources.find_videos(f"{game_name} gameplay", ccfg["youtube_videos"])
    material = {
        "game_name": game_name,
        "search_keyword": candidate["keyword"],
        "store_pages": store_pages,
        "news_headlines": [n["title"] for n in candidate.get("news", [])][:10],
        "youtube_videos": [{k: v[k] for k in ("title", "channel", "published", "description") if v.get(k)}
                           for v in videos],
    }
    # 字幕只能用商店页、新闻等资料之外剩下的长度
    room = ccfg.get("max_input_chars", 60000) - len(json.dumps(material, ensure_ascii=False))
    transcripts, budget = [], min(ccfg["max_transcript_chars"], room)
    # Gemini 免费额度是每天 8 小时 YouTube 视频，所以每个游戏只看几个不太长的视频
    watched = 0
    for video in videos:
        if budget <= 0:
            break
        text = ""
        short = (video.get("minutes") or 0) <= ccfg.get("max_video_minutes", 15)
        if watched < ccfg.get("gemini_videos", 2) and short and video.get("minutes"):
            text = sources.gemini_video_notes(video["id"], game_name)
            watched += 1
        if not text:
            text = sources.youtube_transcript(video["id"])
        text = text[:budget]
        if text:
            transcripts.append({"video": video["title"], "transcript": text})
            budget -= len(text)

    log.info("%s 资料：%s，%d 个视频，%d 份字幕", game_name,
             "、".join(s["source"] for s in store_pages) or "无商店页", len(videos), len(transcripts))
    has_descriptions = any(len(v.get("description", "")) > 200 for v in videos)
    if not store_pages and not transcripts and not has_descriptions and not candidate.get("news"):
        raise RuntimeError("找不到任何可靠资料，跳过以免 AI 编造内容")

    material["youtube_transcripts"] = transcripts
    page = chat_json(
        SYSTEM.format(language=cfg["site"]["language"]),
        json.dumps(material, ensure_ascii=False),
        temperature=0.5,
    )

    return {
        "slug": rec["slug"],
        "game_name": game_name,
        "keyword": candidate["keyword"],
        "created_at": now_iso(),
        "links": [{"label": s["source"], "url": s["url"]} for s in store_pages],
        "image": next((s.get("header_image") for s in store_pages if s.get("header_image")), None),
        "videos": [{k: v[k] for k in ("id", "title", "channel") if k in v} for v in videos[:3]],
        "news": candidate.get("news", [])[:5],
        "page": page,
    }
