"""Small OpenAI-compatible client with repository-external key storage."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

import requests

from stock_assist.paths import PROJECT_ROOT


class LLMError(RuntimeError):
    """Raised when the optional LLM backend is missing or fails."""


def default_api_key_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"
    return root / "InsightRadar" / "secrets" / "openai_api_key.txt"


def save_api_key(api_key: str, path: Path | None = None) -> Path:
    cleaned = api_key.strip()
    if not cleaned or len(cleaned) < 16 or re.search(r"\s", cleaned):
        raise ValueError("API key 格式无效。")
    target = path or default_api_key_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(cleaned, encoding="utf-8")
    try:
        target.chmod(stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass
    return target


def load_api_key(path: Path | None = None) -> str:
    _load_project_env()
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if value:
        return value
    target = path or default_api_key_path()
    if not target.exists():
        raise LLMError("未配置 AI API key；请先运行 `insight-radar llm-auth set`。")
    value = target.read_text(encoding="utf-8").strip()
    if not value:
        raise LLMError("本机 AI API key 文件为空；请重新运行 `insight-radar llm-auth set`。")
    return value


def clear_api_key(path: Path | None = None) -> bool:
    target = path or default_api_key_path()
    if not target.exists():
        return False
    target.unlink()
    return True


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float

    @classmethod
    def from_local(cls, model: str | None = None) -> "LLMConfig":
        _load_project_env()
        return cls(
            api_key=load_api_key(),
            base_url=os.environ.get("OPENAI_BASE_URL", "https://aiapi.world/v1").rstrip("/"),
            model=model or os.environ.get("STOCK_ASSIST_LLM_MODEL", "gpt-4o-mini"),
            timeout_seconds=float(os.environ.get("STOCK_ASSIST_LLM_TIMEOUT", "120")),
        )


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage: dict[str, Any]
    model: str


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_local()

    def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.15,
        max_tokens: int = 3200,
        json_mode: bool = False,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = requests.post(
                f"{self.config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise LLMError(f"AI API 请求失败：{exc}") from exc
        if response.status_code >= 400:
            raise LLMError(f"AI API HTTP {response.status_code}: {response.text[:500]}")
        result = response.json()
        try:
            content = str(result["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("AI API 返回结构异常。") from exc
        return LLMResponse(
            content=content,
            usage=dict(result.get("usage") or {}),
            model=str(result.get("model") or self.config.model),
        )


def parse_json_response(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise LLMError("AI 摘要必须返回 JSON object。")
    return payload


def _load_project_env() -> None:
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
