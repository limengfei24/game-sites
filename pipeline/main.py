import argparse
import logging
import os
from datetime import datetime, timezone

import requests

from . import builder, classify, content, serp, trends, vercel_api
from .config import env, load_config
from .state import load_games, load_state, now_iso, save_game, save_state

log = logging.getLogger("pipeline")


def days_since(iso):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).days


def discover(cfg, state):
    keywords = state["keywords"]
    candidates = trends.collect(cfg)
    fresh = [c for c in candidates if c["keyword"] not in keywords]
    log.info("其中第一次见到的词 %d 个", len(fresh))
    if not fresh:
        return []

    results = classify.classify(fresh)
    min_conf = cfg["rules"]["min_confidence"]
    found = []
    for c in fresh:
        r = results.get(c["keyword"])
        if r is None:
            continue
        is_game = bool(r.get("is_game")) and r.get("confidence", 0) >= min_conf and bool(r["slug"])
        record = {
            "status": "candidate" if is_game else "rejected",
            "first_seen": now_iso(),
            "game_name": r.get("game_name", ""),
            "slug": r["slug"],
            "confidence": r.get("confidence"),
            "reason": r.get("reason", ""),
            "traffic": c["traffic"],
            "sources": c["sources"],
        }
        if is_game:
            record["news"] = c["news"][:5]
            found.append(c["keyword"])
            log.info("发现游戏新词: %s -> %s (%s)", c["keyword"], record["game_name"], record["slug"])
        keywords[c["keyword"]] = record
    return found


def build_new_sites(cfg, state):
    rules = cfg["rules"]
    existing = {g["slug"] for g in load_games()}
    pending = sorted(
        ((kw, rec) for kw, rec in state["keywords"].items() if rec["status"] == "candidate"),
        key=lambda item: item[1]["first_seen"], reverse=True,
    )
    built = []
    for keyword, rec in pending:
        if len(built) >= rules["max_new_sites_per_run"]:
            break
        if rec["slug"] in existing:
            rec["status"] = "duplicate"
            continue

        age = trends.keyword_age_days(keyword)
        rec["age_days"] = age if age is not None else days_since(rec["first_seen"])
        if rec["age_days"] > rules["max_keyword_age_days"]:
            rec["status"] = "abandoned"
            rec["reason"] = f"已经火了 {rec['age_days']} 天，超过 {rules['max_keyword_age_days']} 天"
            log.info("放弃 %s: %s", keyword, rec["reason"])
            continue

        competitors = serp.competition(keyword, rec["slug"])
        rec["competitors"] = competitors
        if competitors is not None and competitors >= rules["max_competitors"]:
            rec["status"] = "abandoned"
            rec["reason"] = f"谷歌前 10 已有 {competitors} 个专门站"
            log.info("放弃 %s: %s", keyword, rec["reason"])
            continue

        try:
            game = content.generate({"keyword": keyword, "news": rec.get("news", [])}, rec, cfg)
        except Exception as exc:
            log.error("生成 %s 的内容失败，下次重试: %s", keyword, exc)
            continue
        save_game(game)
        rec["status"] = "built"
        rec["built_at"] = now_iso()
        existing.add(rec["slug"])
        built.append(rec["slug"])
        log.info("已生成站点内容: %s", rec["slug"])
    return built


def provision(cfg, state):
    base = cfg["base_domain"]
    domains = state.setdefault("domains", {})
    if not domains.get("ready"):
        domains["ready"] = vercel_api.ensure_domains(base)
        if not domains["ready"]:
            return []

    live = []
    for rec in state["keywords"].values():
        if rec["status"] != "built":
            continue
        host = f"{rec['slug']}.{base}"
        rec["status"] = "live"
        rec["url"] = f"https://{host}/"
        rec["live_at"] = now_iso()
        live.append(host)
    return live


def ping(cfg, state):
    key = env("INDEXNOW_KEY")
    if not key:
        return
    for rec in state["keywords"].values():
        if rec["status"] != "live" or rec.get("indexnow_at"):
            continue
        host = rec["url"].split("/")[2]
        resp = requests.post("https://api.indexnow.org/indexnow", timeout=30, json={
            "host": host, "key": key, "keyLocation": f"https://{host}/{key}.txt", "urlList": [rec["url"]],
        })
        if resp.status_code < 300:
            rec["indexnow_at"] = now_iso()
            log.info("已提交 IndexNow: %s", rec["url"])
        else:
            log.warning("IndexNow 提交失败 %s: %s", rec["url"], resp.status_code)


def write_summary(found, built, live):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    lines = [
        "## 游戏新词建站",
        f"- 新发现游戏词：{', '.join(found) or '无'}",
        f"- 新生成站点：{', '.join(built) or '无'}",
        f"- 新上线子域名：{', '.join('https://' + h for h in live) or '无'}",
    ]
    log.info("\n".join(lines))
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="谷歌趋势游戏新词 -> 自动建站")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "build", "ping", "domains"],
                        help="run: 完整流程；build: 只根据已有数据重新生成 dist；"
                             "ping: 部署后通知搜索引擎；domains: 把主域名和通配符子域名绑定到 Vercel")
    parser.add_argument("--dry-run", action="store_true", help="不绑定 Vercel 域名")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config()
    state = load_state()
    try:
        if args.command == "ping":
            ping(cfg, state)
            return
        if args.command == "domains":
            state.setdefault("domains", {})["ready"] = vercel_api.ensure_domains(cfg["base_domain"])
            return
        if args.command == "run":
            found = discover(cfg, state)
            save_state(state)
            built = build_new_sites(cfg, state)
            save_state(state)
            live = [] if args.dry_run else provision(cfg, state)
            write_summary(found, built, live)
        builder.build(load_games(), cfg)
    finally:
        save_state(state)


if __name__ == "__main__":
    main()
