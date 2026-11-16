import json
import logging
import re
import time

import requests

from .config import env

log = logging.getLogger(__name__)


def chat_json(system, user, temperature=0.3):
    base_url = env("LLM_BASE_URL", "https://models.github.ai/inference").rstrip("/")
    for attempt in range(4):
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {env('LLM_API_KEY', required=True)}"},
            json={
                "model": env("LLM_MODEL", "openai/gpt-4.1-mini"),
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=300,
        )
        if resp.status_code != 429 or attempt == 3:
            break
        wait = min(int(resp.headers.get("Retry-After") or 60), 300)
        log.info("AI 接口限流，%d 秒后重试", wait)
        time.sleep(wait)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(text)
