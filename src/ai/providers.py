from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlparse

import httpx


OPENAI_COMPATIBLE = "openai_compatible"
ANTHROPIC_COMPATIBLE = "anthropic_compatible"

PROTOCOL_LABELS = {
    OPENAI_COMPATIBLE: "OpenAI Compatible",
    ANTHROPIC_COMPATIBLE: "Anthropic Compatible",
}


class ProviderConfigError(ValueError):
    pass


class ProviderRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompletionResult:
    text: str
    stop_reason: Optional[str] = None

    @property
    def truncated(self) -> bool:
        reason = (self.stop_reason or "").strip().casefold()
        return reason in {"length", "max_tokens", "max_output_tokens"}


@dataclass(frozen=True)
class ProviderTemplate:
    id: str
    name: str
    protocol: str
    base_url: str
    endpoint: str
    model: str
    models_endpoint: str = "models"
    supports_json_mode: bool = True
    description: str = ""


PROVIDER_TEMPLATES = (
    ProviderTemplate(
        id="openai",
        name="OpenAI",
        protocol=OPENAI_COMPATIBLE,
        base_url="https://api.openai.com/v1",
        endpoint="chat/completions",
        model="gpt-4o-mini",
    ),
    ProviderTemplate(
        id="anthropic",
        name="Anthropic",
        protocol=ANTHROPIC_COMPATIBLE,
        base_url="https://api.anthropic.com",
        endpoint="v1/messages",
        model="claude-sonnet-4-20250514",
        models_endpoint="v1/models",
        supports_json_mode=False,
    ),
    ProviderTemplate(
        id="zhipu",
        name="智谱 GLM",
        protocol=OPENAI_COMPATIBLE,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        endpoint="chat/completions",
        model="glm-4.7-flash",
    ),
    ProviderTemplate(
        id="deepseek",
        name="DeepSeek",
        protocol=OPENAI_COMPATIBLE,
        base_url="https://api.deepseek.com",
        endpoint="chat/completions",
        model="deepseek-chat",
    ),
    ProviderTemplate(
        id="openrouter",
        name="OpenRouter",
        protocol=OPENAI_COMPATIBLE,
        base_url="https://openrouter.ai/api/v1",
        endpoint="chat/completions",
        model="openai/gpt-4o-mini",
    ),
    ProviderTemplate(
        id="qwen",
        name="通义千问",
        protocol=OPENAI_COMPATIBLE,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        endpoint="chat/completions",
        model="qwen-plus",
    ),
    ProviderTemplate(
        id="siliconflow",
        name="硅基流动",
        protocol=OPENAI_COMPATIBLE,
        base_url="https://api.siliconflow.cn/v1",
        endpoint="chat/completions",
        model="deepseek-ai/DeepSeek-V3",
    ),
    ProviderTemplate(
        id="custom_openai",
        name="自定义 OpenAI Compatible",
        protocol=OPENAI_COMPATIBLE,
        base_url="",
        endpoint="chat/completions",
        model="",
        supports_json_mode=False,
    ),
    ProviderTemplate(
        id="custom_anthropic",
        name="自定义 Anthropic Compatible",
        protocol=ANTHROPIC_COMPATIBLE,
        base_url="",
        endpoint="v1/messages",
        model="",
        models_endpoint="v1/models",
        supports_json_mode=False,
    ),
)

_TEMPLATE_MAP = {template.id: template for template in PROVIDER_TEMPLATES}


def get_provider_template(template_id: str) -> ProviderTemplate:
    try:
        return _TEMPLATE_MAP[template_id]
    except KeyError as exc:
        raise ProviderConfigError(f"未知 Provider 模板: {template_id}") from exc


@dataclass
class ProviderConfig:
    id: str
    name: str
    template_id: str
    protocol: str
    base_url: str
    endpoint: str
    api_key: str
    model: str
    models_endpoint: str = "models"
    supports_json_mode: bool = True
    custom_headers: Dict[str, str] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def protocol_label(self) -> str:
        return PROTOCOL_LABELS.get(self.protocol, self.protocol)

    @property
    def request_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/{self.endpoint.lstrip('/')}"

    @property
    def models_url(self) -> str:
        parsed = urlparse(self.models_endpoint)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return self.models_endpoint
        return f"{self.base_url.rstrip('/')}/{self.models_endpoint.lstrip('/')}"

    @property
    def masked_key(self) -> str:
        if not self.api_key:
            return "未设置"
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:3]}{'*' * 6}{self.api_key[-4:]}"

    def validate(self, *, require_model: bool = True) -> None:
        self.name = self.name.strip()
        self.base_url = self.base_url.strip()
        self.endpoint = self.endpoint.strip().lstrip("/")
        self.model = self.model.strip()
        self.models_endpoint = self.models_endpoint.strip()
        self.api_key = self.api_key.strip()

        if not self.name:
            raise ProviderConfigError("Provider 名称不能为空")
        if self.protocol not in PROTOCOL_LABELS:
            raise ProviderConfigError(f"不支持的协议: {self.protocol}")
        if not self.base_url:
            raise ProviderConfigError("Base URL 不能为空")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ProviderConfigError("Base URL 必须是有效的 HTTP(S) 地址")
        if not self.endpoint:
            raise ProviderConfigError("API 端点不能为空")
        if require_model and not self.model:
            raise ProviderConfigError("模型名称不能为空")
        if not isinstance(self.custom_headers, dict):
            raise ProviderConfigError("自定义 Headers 必须是对象")
        self.custom_headers = {
            str(key).strip(): str(value).strip()
            for key, value in self.custom_headers.items()
            if str(key).strip()
        }

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ProviderConfig":
        try:
            config = cls(
                id=str(data["id"]),
                name=str(data["name"]),
                template_id=str(data.get("template_id", "custom_openai")),
                protocol=str(data["protocol"]),
                base_url=str(data["base_url"]),
                endpoint=str(data["endpoint"]),
                api_key=str(data.get("api_key", "")),
                model=str(data["model"]),
                models_endpoint=str(
                    data.get("models_endpoint")
                    or (
                        "v1/models"
                        if data.get("protocol") == ANTHROPIC_COMPATIBLE
                        else "models"
                    )
                ),
                supports_json_mode=bool(data.get("supports_json_mode", True)),
                custom_headers=dict(data.get("custom_headers", {})),
                created_at=int(data.get("created_at", int(time.time() * 1000))),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderConfigError("Provider 配置字段不完整") from exc
        config.validate()
        return config


def create_provider_from_template(
    template_id: str,
    *,
    name: Optional[str] = None,
    base_url: Optional[str] = None,
    endpoint: Optional[str] = None,
    api_key: str = "",
    model: Optional[str] = None,
    models_endpoint: Optional[str] = None,
    custom_headers: Optional[Mapping[str, str]] = None,
    supports_json_mode: Optional[bool] = None,
    provider_id: Optional[str] = None,
    require_model: bool = True,
) -> ProviderConfig:
    template = get_provider_template(template_id)
    config = ProviderConfig(
        id=provider_id or uuid.uuid4().hex,
        name=name if name is not None else template.name,
        template_id=template.id,
        protocol=template.protocol,
        base_url=base_url if base_url is not None else template.base_url,
        endpoint=endpoint if endpoint is not None else template.endpoint,
        api_key=api_key,
        model=model if model is not None else template.model,
        models_endpoint=(
            models_endpoint
            if models_endpoint is not None
            else template.models_endpoint
        ),
        supports_json_mode=(
            supports_json_mode
            if supports_json_mode is not None
            else template.supports_json_mode
        ),
        custom_headers=dict(custom_headers or {}),
    )
    config.validate(require_model=require_model)
    return config


@dataclass
class ProviderState:
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    current: Optional[str] = None

    @property
    def active(self) -> Optional[ProviderConfig]:
        if not self.current:
            return None
        return self.providers.get(self.current)


class ProviderStore:
    VERSION = 1

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or ".aero-analytica/providers.json")

    def load(self) -> ProviderState:
        if not self.path.exists():
            return ProviderState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            providers = {
                provider_id: ProviderConfig.from_dict(provider_data)
                for provider_id, provider_data in raw.get("providers", {}).items()
            }
            current = raw.get("current")
            if current not in providers:
                current = next(iter(providers), None)
            return ProviderState(providers=providers, current=current)
        except (OSError, json.JSONDecodeError, AttributeError, ProviderConfigError) as exc:
            raise ProviderConfigError(f"无法读取 Provider 配置: {exc}") from exc

    def save(self, state: ProviderState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "current": state.current,
            "providers": {
                provider_id: provider.to_dict()
                for provider_id, provider in state.providers.items()
            },
        }

        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix="providers-",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                json.dump(payload, temp_file, ensure_ascii=False, indent=2)
                temp_file.write("\n")
                temp_name = temp_file.name
            os.replace(temp_name, self.path)
            os.chmod(self.path, 0o600)
        except OSError as exc:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
            raise ProviderConfigError(f"无法保存 Provider 配置: {exc}") from exc

    def upsert(self, provider: ProviderConfig) -> ProviderState:
        provider.validate()
        state = self.load()
        duplicate = next(
            (
                item
                for item in state.providers.values()
                if item.id != provider.id and item.name.casefold() == provider.name.casefold()
            ),
            None,
        )
        if duplicate:
            raise ProviderConfigError(f"Provider 名称已存在: {provider.name}")
        state.providers[provider.id] = provider
        if not state.current:
            state.current = provider.id
        self.save(state)
        return state

    def set_current(self, provider_id: str) -> ProviderState:
        state = self.load()
        if provider_id not in state.providers:
            raise ProviderConfigError("要激活的 Provider 不存在")
        state.current = provider_id
        self.save(state)
        return state

    def delete(self, provider_id: str) -> ProviderState:
        state = self.load()
        if provider_id not in state.providers:
            raise ProviderConfigError("要删除的 Provider 不存在")
        del state.providers[provider_id]
        if state.current == provider_id:
            state.current = next(iter(state.providers), None)
        self.save(state)
        return state


class ProviderClient:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        timeout: float = 60.0,
        http_client: Optional[httpx.Client] = None,
    ):
        config.validate(require_model=False)
        self.config = config
        self.timeout = timeout
        self._http_client = http_client

    def complete(
        self,
        messages: Iterable[Mapping[str, str]],
        *,
        json_mode: bool = False,
        max_tokens: int = 2048,
    ) -> str:
        return self.complete_with_metadata(
            messages,
            json_mode=json_mode,
            max_tokens=max_tokens,
        ).text

    def complete_with_metadata(
        self,
        messages: Iterable[Mapping[str, str]],
        *,
        json_mode: bool = False,
        max_tokens: int = 2048,
    ) -> CompletionResult:
        if not self.config.model:
            raise ProviderConfigError("模型名称不能为空")
        normalized = self._normalize_messages(messages)
        if self.config.protocol == OPENAI_COMPATIBLE:
            return self._complete_openai(normalized, json_mode, max_tokens)
        if self.config.protocol == ANTHROPIC_COMPATIBLE:
            return self._complete_anthropic(normalized, max_tokens)
        raise ProviderConfigError(f"不支持的协议: {self.config.protocol}")

    def test_connection(self) -> str:
        return self.complete(
            [{"role": "user", "content": "Reply with OK only."}],
            max_tokens=16,
        )

    def list_models(self) -> List[str]:
        if not self.config.models_endpoint:
            raise ProviderConfigError("模型列表端点不能为空")

        headers = {"Accept": "application/json"}
        if self.config.protocol == OPENAI_COMPATIBLE:
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
        elif self.config.protocol == ANTHROPIC_COMPATIBLE:
            headers["anthropic-version"] = "2023-06-01"
            if self.config.api_key:
                headers["x-api-key"] = self.config.api_key
        else:
            raise ProviderConfigError(f"不支持的协议: {self.config.protocol}")
        headers.update(self.config.custom_headers)

        data = self._get(headers)
        raw_models = data.get("data")
        if raw_models is None:
            raw_models = data.get("models")
        if not isinstance(raw_models, list):
            raise ProviderRequestError("Provider 模型列表响应缺少 data 数组")

        model_ids = []
        for item in raw_models:
            if isinstance(item, str):
                model_id = item.strip()
            elif isinstance(item, dict):
                model_id = str(
                    item.get("id") or item.get("name") or item.get("model") or ""
                ).strip()
            else:
                model_id = ""
            if model_id:
                model_ids.append(model_id)

        models = sorted(set(model_ids), key=str.casefold)
        if not models:
            raise ProviderRequestError("Provider 未返回可用模型")
        return models

    @staticmethod
    def _normalize_messages(
        messages: Iterable[Mapping[str, str]],
    ) -> List[Dict[str, str]]:
        normalized = []
        for message in messages:
            role = str(message.get("role", "user"))
            content = str(message.get("content", ""))
            if content:
                normalized.append({"role": role, "content": content})
        if not normalized:
            raise ProviderConfigError("消息列表不能为空")
        return normalized

    def _complete_openai(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool,
        max_tokens: int,
    ) -> CompletionResult:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        headers.update(self.config.custom_headers)

        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if json_mode and self.config.supports_json_mode:
            payload["response_format"] = {"type": "json_object"}

        data = self._post(headers, payload)
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            stop_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestError("OpenAI Compatible 响应缺少 choices.message.content") from exc
        return CompletionResult(
            text=self._coerce_text(content),
            stop_reason=str(stop_reason) if stop_reason is not None else None,
        )

    def _complete_anthropic(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
    ) -> CompletionResult:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.config.api_key:
            headers["x-api-key"] = self.config.api_key
        headers.update(self.config.custom_headers)

        system_messages = [m["content"] for m in messages if m["role"] == "system"]
        conversation = [
            {
                "role": m["role"] if m["role"] in {"user", "assistant"} else "user",
                "content": m["content"],
            }
            for m in messages
            if m["role"] != "system"
        ]
        if not conversation:
            conversation = [{"role": "user", "content": "Continue."}]

        payload = {
            "model": self.config.model,
            "messages": conversation,
            "max_tokens": max_tokens,
        }
        if system_messages:
            payload["system"] = "\n\n".join(system_messages)

        data = self._post(headers, payload)
        try:
            content = data["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderRequestError("Anthropic Compatible 响应缺少 content") from exc
        stop_reason = data.get("stop_reason")
        return CompletionResult(
            text=self._coerce_text(content),
            stop_reason=str(stop_reason) if stop_reason is not None else None,
        )

    def _post(self, headers: Mapping[str, str], payload: Mapping[str, object]) -> dict:
        return self._request_json("POST", self.config.request_url, headers, payload)

    def _get(self, headers: Mapping[str, str]) -> dict:
        return self._request_json("GET", self.config.models_url, headers)

    def _request_json(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        payload: Optional[Mapping[str, object]] = None,
    ) -> dict:
        try:
            request_kwargs = {
                "headers": dict(headers),
                "timeout": self.timeout,
            }
            if payload is not None:
                request_kwargs["json"] = dict(payload)
            if self._http_client is not None:
                response = self._http_client.request(method, url, **request_kwargs)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.request(method, url, **request_kwargs)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ProviderRequestError("Provider 返回的 JSON 不是对象")
            return data
        except httpx.HTTPStatusError as exc:
            detail = self._response_error(exc.response)
            raise ProviderRequestError(
                f"Provider 请求失败 ({exc.response.status_code}): {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError(f"无法连接 Provider: {exc}") from exc
        except ValueError as exc:
            raise ProviderRequestError("Provider 返回了无效 JSON") from exc

    @staticmethod
    def _response_error(response: httpx.Response) -> str:
        try:
            data = response.json()
            error = data.get("error", data)
            if isinstance(error, dict):
                return str(error.get("message") or error.get("type") or "未知错误")[:400]
            return str(error)[:400]
        except ValueError:
            return response.text.strip()[:400] or "未知错误"

    @staticmethod
    def _coerce_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    parts.append(item)
            text = "\n".join(part for part in parts if part)
            if text:
                return text
        raise ProviderRequestError("Provider 响应中没有可用文本")


def create_provider_client(config: ProviderConfig) -> ProviderClient:
    return ProviderClient(config)
