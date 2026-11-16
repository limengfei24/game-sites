import json
import logging
import re
import shutil
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import DIST_DIR, ROOT, TEMPLATES_DIR, env

log = logging.getLogger(__name__)


def _vercel_config(base_domain):
    escaped = re.escape(base_domain)
    return {
        "cleanUrls": True,
        "trailingSlash": False,
        # 只在 dist 根目录放 vercel.json / assets / hub / sites，
        # 这样子域名访问 / 时文件系统没有命中，才会走下面的按 Host 重写。
        # 根路径要重写到不带斜杠的目录名：在 cleanUrls + trailingSlash=false 下，
        # "/hub/" 和 "/hub/index.html" 作为重写目标都会 404，只有 "/hub" 能命中 hub/index.html。
        "rewrites": [
            {"source": "/", "has": [{"type": "host", "value": f"(www\\.)?{escaped}"}],
             "destination": "/hub"},
            {"source": "/:path+", "has": [{"type": "host", "value": f"(www\\.)?{escaped}"}],
             "destination": "/hub/:path+"},
            {"source": "/", "has": [{"type": "host", "value": f"(?<sub>[a-z0-9-]+)\\.{escaped}"}],
             "destination": "/sites/:sub"},
            {"source": "/:path+", "has": [{"type": "host", "value": f"(?<sub>[a-z0-9-]+)\\.{escaped}"}],
             "destination": "/sites/:sub/:path+"},
        ],
        "headers": [
            {"source": "/assets/(.*)",
             "headers": [{"key": "Cache-Control", "value": "public, max-age=31536000, immutable"}]},
        ],
    }


def build(games, cfg):
    base_domain = cfg["base_domain"]
    if not base_domain:
        raise RuntimeError("config.yaml 里的 base_domain 还没填")

    jinja = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape())
    common = {
        "site": cfg["site"],
        "base_domain": base_domain,
        "year": datetime.now(timezone.utc).year,
        "asset_version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M"),
    }
    indexnow_key = env("INDEXNOW_KEY")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    shutil.copytree(TEMPLATES_DIR / "assets", DIST_DIR / "assets")

    games = sorted(games, key=lambda g: g["created_at"], reverse=True)
    for game in games:
        url = f"https://{game['slug']}.{base_domain}/"
        out = DIST_DIR / "sites" / game["slug"]
        out.mkdir(parents=True)
        (out / "index.html").write_text(
            jinja.get_template("game.html").render(game=game, page=game["page"], url=url,
                                                   ld_json=_ld_json(game, url),
                                                   others=[g for g in games if g is not game][:6],
                                                   **common),
            encoding="utf-8",
        )
        _write_seo_files(out, [url], indexnow_key)

    hub_url = f"https://{base_domain}/"
    hub = DIST_DIR / "hub"
    hub.mkdir(parents=True)
    (hub / "index.html").write_text(
        jinja.get_template("hub.html").render(games=games, url=hub_url, **common), encoding="utf-8")
    # 主站 sitemap 同时列出所有子域名站：Search Console 里 many.pw 是网域资源，覆盖全部子域名，
    # 只提交这一个 sitemap，以后新建的站也会被 Google 自动发现。
    site_urls = [f"https://{g['slug']}.{base_domain}/" for g in games]
    _write_seo_files(hub, [hub_url, *site_urls], indexnow_key)

    (DIST_DIR / "vercel.json").write_text(
        json.dumps(_vercel_config(base_domain), indent=2), encoding="utf-8")
    shutil.copy(ROOT / "templates" / "404.html", DIST_DIR / "404.html")
    log.info("已生成 %d 个游戏站到 %s", len(games), DIST_DIR)


def _write_seo_files(out, urls, indexnow_key):
    origin = urls[0].rstrip("/")
    today = datetime.now(timezone.utc).date().isoformat()
    entries = "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    (out / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>\n',
        encoding="utf-8")
    (out / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {origin}/sitemap.xml\n", encoding="utf-8")
    if indexnow_key:
        (out / f"{indexnow_key}.txt").write_text(indexnow_key, encoding="utf-8")


def _ld_json(game, url):
    page = game["page"]
    data = [{
        "@context": "https://schema.org",
        "@type": "VideoGame",
        "name": game["game_name"],
        "url": url,
        "description": page.get("meta_description", ""),
    }]
    if page.get("faq"):
        data.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": f["q"],
                 "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
                for f in page["faq"]
            ],
        })
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
