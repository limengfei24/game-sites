import logging

import requests

from .config import env

log = logging.getLogger(__name__)

API = "https://api.vercel.com"
NAMESERVERS = ["ns1.vercel-dns.com", "ns2.vercel-dns.com"]


def _request(method, path, **kwargs):
    params = kwargs.pop("params", {})
    team = env("VERCEL_ORG_ID")
    if team and team.startswith("team_"):
        params["teamId"] = team
    return requests.request(
        method, f"{API}{path}",
        headers={"Authorization": f"Bearer {env('VERCEL_TOKEN', required=True)}"},
        params=params, timeout=30, **kwargs,
    )


def ensure_domains(base_domain):
    """把主域名、www 和 *.主域名 绑定到 Vercel 项目。

    通配符域名要求主域名的 DNS 服务器指向 Vercel（NAMESERVERS），
    这样之后任何 <slug>.主域名 都直接生效，不需要再逐个配置解析。
    """
    project = env("VERCEL_PROJECT_ID", required=True)
    all_ok = True
    for name in (base_domain, f"www.{base_domain}", f"*.{base_domain}"):
        resp = _request("POST", f"/v10/projects/{project}/domains", json={"name": name})
        if resp.status_code == 409:
            resp = _request("GET", f"/v9/projects/{project}/domains/{name}")
        if resp.status_code >= 400:
            log.error("Vercel 绑定 %s 失败: %s %s", name, resp.status_code, resp.text)
            all_ok = False
            continue
        if not resp.json().get("verified", True):
            log.warning("%s 还没验证通过，请确认 %s 的 DNS 服务器已改为 %s",
                        name, base_domain, " / ".join(NAMESERVERS))
            all_ok = False
        else:
            log.info("Vercel 已绑定 %s", name)
    return all_ok
