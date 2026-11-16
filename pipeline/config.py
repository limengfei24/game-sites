import os
import re
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
GAMES_DIR = DATA_DIR / "games"
STATE_FILE = DATA_DIR / "state.json"
DIST_DIR = ROOT / "dist"
TEMPLATES_DIR = ROOT / "templates"


def load_dotenv():
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_config():
    load_dotenv()
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name, default=None, required=False):
    value = os.environ.get(name) or default
    if required and not value:
        raise RuntimeError(f"缺少环境变量 {name}，请在 .env 或 GitHub Secrets 里配置")
    return value


def normalize_keyword(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    # 子域名的单个 label 最长 63 个字符
    return text[:63].rstrip("-")
