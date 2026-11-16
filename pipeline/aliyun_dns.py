import base64
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from .config import env

log = logging.getLogger(__name__)

ENDPOINT = "https://alidns.aliyuncs.com/"


def _pe(value):
    return quote(str(value), safe="~")


def call(action, **params):
    secret = env("ALIYUN_ACCESS_KEY_SECRET", required=True)
    query = {
        "Action": action,
        "Format": "JSON",
        "Version": "2015-01-09",
        "AccessKeyId": env("ALIYUN_ACCESS_KEY_ID", required=True),
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid.uuid4().hex,
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **{k: v for k, v in params.items() if v is not None},
    }
    canonical = "&".join(f"{_pe(k)}={_pe(v)}" for k, v in sorted(query.items()))
    string_to_sign = f"GET&{_pe('/')}&{_pe(canonical)}"
    digest = hmac.new(f"{secret}&".encode(), string_to_sign.encode(), hashlib.sha1).digest()
    signature = base64.b64encode(digest).decode()

    resp = requests.get(f"{ENDPOINT}?{canonical}&Signature={_pe(signature)}", timeout=30)
    data = resp.json()
    if resp.status_code != 200:
        raise RuntimeError(f"阿里云 DNS {action} 失败: {data.get('Code')} {data.get('Message')}")
    return data


def find_records(domain, rr, record_type):
    data = call("DescribeDomainRecords", DomainName=domain, RRKeyWord=rr, Type=record_type, PageSize=100)
    return [r for r in data["DomainRecords"]["Record"] if r["RR"] == rr]


def upsert_record(domain, rr, record_type, value):
    existing = find_records(domain, rr, record_type)
    for record in existing:
        if record["Value"].rstrip(".") == value.rstrip("."):
            log.info("DNS 已存在 %s.%s %s -> %s", rr, domain, record_type, value)
            return
    if existing and record_type in ("A", "CNAME"):
        record = existing[0]
        call("UpdateDomainRecord", RecordId=record["RecordId"], RR=rr, Type=record_type, Value=value)
        log.info("DNS 已更新 %s.%s %s -> %s", rr, domain, record_type, value)
        return
    call("AddDomainRecord", DomainName=domain, RR=rr, Type=record_type, Value=value)
    log.info("DNS 已添加 %s.%s %s -> %s", rr, domain, record_type, value)


def check_domain(domain):
    """确认主域名在当前 AccessKey 的阿里云账号下并由阿里云 DNS 解析。"""
    call("DescribeDomainInfo", DomainName=domain)
