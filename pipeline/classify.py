import json
import logging

from .config import normalize_keyword, slugify
from .llm import chat_json

log = logging.getLogger(__name__)

SYSTEM = """You are a gaming market analyst. You receive Google Trends search terms that are spiking.
Decide for each term whether people are searching for ONE specific, newly released or newly viral
video game / web game / mobile game (or a specific new mode / update of a game that people would
search as its own name). Reject: sports matches, athletes, celebrities, movies, TV, generic phrases
("free games", "games online"), big evergreen franchises with no new release (e.g. "minecraft"),
news about huge AAA franchises (GTA, Call of Duty, Pokémon, Zelda, FIFA/EA FC...) because big gaming
media own those searches and a small new site can't rank, and anything you are unsure is a game.
Prefer small, indie, Roblox, Steam, mobile or web games that just went viral.

Reply as JSON: {"results": [{"keyword": "<exact input term>", "is_game": true/false,
"game_name": "<official game title>", "slug": "<short lowercase ascii-hyphen name for a subdomain>",
"confidence": 0.0-1.0, "reason": "<short>"}]}"""


def classify(candidates, batch_size=40):
    results = {}
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        payload = [
            {"keyword": c["keyword"], "traffic": c["traffic"],
             "news": [n["title"] for n in c["news"][:3]]}
            for c in batch
        ]
        try:
            reply = chat_json(SYSTEM, json.dumps(payload, ensure_ascii=False), temperature=0)
        except Exception as exc:
            log.error("AI 分类失败: %s", exc)
            continue
        for r in reply.get("results", []):
            key = normalize_keyword(r.get("keyword", ""))
            if not key:
                continue
            r["slug"] = slugify(r.get("slug") or r.get("game_name") or key)
            results[key] = r
    return results
