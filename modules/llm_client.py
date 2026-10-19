"""Minimal OpenAI-compatible Chat Completions adapter for external models."""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlparse

import requests


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        post: Callable = requests.post,
        sleep: Callable = time.sleep,
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("请配置模型 API Key 和模型名。")
        parsed = urlparse(base_url.strip())
        local = parsed.hostname in {"localhost", "127.0.0.1"}
        if not parsed.netloc or (parsed.scheme != "https" and not (local and parsed.scheme == "http")):
            raise ValueError("模型 API 地址必须为 HTTPS（本机地址可使用 HTTP）。")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.post = post
        self.sleep = sleep

    def complete(self, system: str, user: str, max_tokens: int = 1800) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in range(2):
            try:
                response = self.post(self.url, headers=headers, json=payload, timeout=(5, 90))
                if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                    self.sleep(1)
                    continue
                response.raise_for_status()
                choice = response.json()["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise RuntimeError("模型输出被截断；请缩短输入后重试。")
                content = choice["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("模型返回了空内容。")
                return content.strip()
            except requests.RequestException as exc:
                if attempt == 0 and not isinstance(exc, requests.HTTPError):
                    self.sleep(1)
                    continue
                raise RuntimeError("模型 API 调用失败；请检查地址、密钥、网络或额度。") from exc
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise RuntimeError("模型 API 返回了无法解析的响应。") from exc
        raise RuntimeError("模型 API 调用失败。")
