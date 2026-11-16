import json
from datetime import datetime, timezone

from .config import GAMES_DIR, STATE_FILE

# 每个关键词的 status:
#   candidate  已识别为游戏词，等待建站
#   rejected   AI 判断不是具体游戏
#   abandoned  太老或竞争太激烈，放弃
#   built      内容已生成
#   live       子域名 DNS + Vercel 已配置


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"keywords": {}}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_games():
    games = []
    for path in sorted(GAMES_DIR.glob("*.json")):
        games.append(json.loads(path.read_text(encoding="utf-8")))
    return games


def save_game(game):
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    path = GAMES_DIR / f"{game['slug']}.json"
    path.write_text(json.dumps(game, ensure_ascii=False, indent=2), encoding="utf-8")
