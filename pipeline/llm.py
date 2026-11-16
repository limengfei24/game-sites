import json
import re

import requests

from .config import env


def chat_json(system, user, temperature=0.3):
    base_url = env("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {env('LLM_API_KEY', required=True)}"},
        json={
            "model": env("LLM_MODEL", "qwen-plus"),
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=300,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(text)
