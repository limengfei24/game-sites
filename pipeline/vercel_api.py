import logging

import requests

from . import aliyun_dns
from .config import env

log = logging.getLogger(__name__)

API = "https://api.vercel.com"
CNAME_TARGET = "cname.vercel-dns.com"
APEX_IP = "76.76.21.21"


def _request(method, path, **kwargs):
    params = kwargs.pop("params", {})
    team = env("VERCEL_ORG_ID")
    if team and team.startswith("team_"):
        params["teamId"] = team
    resp = requests.request(
        method, f"{API}{path}",
        headers={"Authorization": f"Bearer {env('VERCEL_TOKEN', required=True)}"},
        params=params, timeout=30, **kwargs,
    )
    return resp


def add_domain(hostname, base_domain):
    """把 hostname 绑定到 Vercel 项目，并在阿里云 DNS 上加好解析记录和所需的验证 TXT。"""
    project = env("VERCEL_PROJECT_ID", required=True)
    if hostname == base_domain:
        aliyun_dns.upsert_record(base_domain, "@", "A", APEX_IP)
    else:
        aliyun_dns.upsert_record(base_domain, hostname[: -len(base_domain) - 1], "CNAME", CNAME_TARGET)

    resp = _request("POST", f"/v10/projects/{project}/domains", json={"name": hostname})
    if resp.status_code == 409:
        resp = _request("GET", f"/v9/projects/{project}/domains/{hostname}")
    if resp.status_code >= 400:
        raise RuntimeError(f"Vercel 绑定域名失败 {hostname}: {resp.status_code} {resp.text}")

    info = resp.json()
    if info.get("verified", True):
        log.info("Vercel 已绑定 %s", hostname)
        return True

    for item in info.get("verification", []):
        if item.get("type") == "TXT":
            txt_rr = item["domain"][: -len(base_domain) - 1]
            aliyun_dns.upsert_record(base_domain, txt_rr, "TXT", item["value"])
    verify = _request("POST", f"/v9/projects/{project}/domains/{hostname}/verify")
    if verify.status_code >= 400:
        log.warning("%s 已加验证记录，Vercel 暂未验证通过（DNS 生效后下次运行会重试）: %s",
                    hostname, verify.text)
        return False
    log.info("Vercel 已绑定并验证 %s", hostname)
    return True
