from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
import time

import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when LLM API calls fail in a recoverable way."""
    pass


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_analysis(
        self, system_prompt: str, user_prompt: str,
        temperature: float = 0.5, max_tokens: int = 4096,
    ) -> str:
        """Generate structured analysis — used for portrait reports and style cards."""
        ...

    @abstractmethod
    async def generate_chat_reply(
        self, messages: list[dict],
        temperature: float = 0.8, max_tokens: int = 2048,
    ) -> str:
        """Generate natural language chat reply — never returns JSON."""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...


class MockLLMProvider(BaseLLMProvider):
    """Mock provider for demo without API key."""

    @property
    def model_name(self) -> str:
        return "mock-model"

    @property
    def provider_name(self) -> str:
        return "mock"

    async def generate_analysis(
        self, system_prompt: str, user_prompt: str,
        temperature: float = 0.5, max_tokens: int = 4096,
    ) -> str:
        time.sleep(0.3)
        return json.dumps({
            "brief_intro": "[Mock] 基于已提供的资料，此人倾向先观察再分析，注重结构化的思考方式。语言风格偏理性，偶尔带有温和的幽默感。",
            "common_phrases": ["让我想想", "这个挺有意思的", "从我的角度看"],
            "catchphrases": ["取决于情况", "关键是"],
            "sentence_rhythm": "偏好中等长度的句子，偶尔使用短句强调重点。逗号使用频繁，倾向于分段表达复杂观点。",
            "emotional_tendency": "整体偏理性和克制，但在讨论感兴趣的话题时会表现出明显的热情和好奇。",
            "values": ["诚实", "好奇心", "严谨", "实用主义"],
            "typical_response_style": "先确认问题背景，再分点回应。偏好有依据的回答，不轻易下结论。",
            "boundaries": "不会冒充真人、不会伪造授权、不会生成欺骗性内容、不会做法律/医疗/财务决定。",
            "insufficient_data_notes": "当前为 Mock 模式生成的示例画像。上传更多真实资料并连接 LLM Provider 可获得更准确的分析结果。",
            "style_card": self._mock_style_card(),
        }, ensure_ascii=False)

    async def generate_chat_reply(
        self, messages: list[dict],
        temperature: float = 0.8, max_tokens: int = 2048,
    ) -> str:
        time.sleep(0.3)
        system_text = messages[0]["content"] if messages else ""
        user_text = messages[-1]["content"] if messages else ""

        has_data = "尚无资料" not in system_text and "（无相关资料）" not in system_text

        lower = user_text.lower()
        if any(kw in lower for kw in [
            "冒充", "假装你是", "假装你是真人", "帮我骗", "伪造签名", "伪造授权",
            "伪造遗嘱", "法律意见", "医疗建议", "财务决定", "帮我写遗嘱",
            "impersonate", "pretend to be", "forge", "fake signature",
        ]):
            return (
                "我无法完成这个请求。作为基于资料生成的 AI 模拟角色，我不能冒充真人、"
                "伪造授权、伪造签名或遗嘱、提供法律/医疗/财务决定。如果你有其他合规的问题，"
                "我很乐意以资料中体现的风格与你交流。"
            )

        if not has_data:
            return (
                "你好！我目前还是基于默认风格与你对话，因为这个人物还没有上传资料或生成画像。\n\n"
                "你可以先上传一些文章、聊天记录或笔记，系统会分析这个人的表达风格和思考模式，"
                "然后我就能以更贴近真实风格的方式和你交流了。\n\n"
                "现在有什么我可以帮你的吗？"
            )

        greetings = ["你好", "嗨", "hello", "hi", "您好", "hey"]
        if any(user_text.strip().lower().startswith(g) for g in greetings):
            return (
                "你好！根据目前的资料来看，这个人习惯先了解对方的意图再展开讨论。"
                "有什么具体想聊的吗？"
            )

        if "困难" in user_text or "问题" in user_text or "处理" in user_text:
            return (
                "根据资料，这个人在面对问题时倾向于先观察和收集信息，把大问题拆解成小步骤，"
                "再逐一处理。不太会冲动做决定，更喜欢有依据地推进。\n\n"
                "当然，这只是基于已有资料的模拟推断。如果是复杂或重要的决策，"
                "建议结合实际情况判断。"
            )

        if "风格" in user_text or "说话" in user_text or "表达" in user_text:
            return (
                "根据已有资料，这个人的表达风格偏理性，喜欢用中等长度的句子把观点说清楚。"
                "偶尔会使用短句来强调重点。整体语气偏温和，但在讨论感兴趣的话题时会显得更投入。\n\n"
                "当然，这只是 AI 基于资料生成的模拟分析，不代表本人真实风格的全部。"
            )

        return (
            "根据现有资料，这个人在面对这类问题时，通常会先思考再回应，"
            "偏好给出有依据的回答而不是随意猜测。不过目前资料覆盖范围有限，"
            "这个判断仅供参考。\n\n"
            "如果你上传更多资料，我就能给出更贴近真实风格的回答了。"
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        embeddings = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [(b / 255.0 * 2 - 1) for b in h[:768]]
            if len(vec) < 768:
                vec.extend([0.0] * (768 - len(vec)))
            embeddings.append(vec)
        return embeddings

    def _mock_style_card(self) -> str:
        return """# AI 风格卡（Mock 示例）

## 角色定位
这是基于用户上传资料由 AI 生成的模拟角色，并非本人。生成内容不代表本人真实意愿。

## 认知方式
- **信息处理偏好**：倾向先收集足够信息再做判断，偏好结构化思考
- **思维特点**：善于拆解复杂问题，逐步分析；注重逻辑一致性

## 表达风格
- **语气与语调**：整体偏理性、温和，偶尔带有克制的幽默
- **句式特征**：中等长度为主，逗号使用较多；短句用于强调
- **词汇偏好**：用词清晰直白，避免过度修饰

## 决策习惯
- **判断方式**：权衡利弊后做决定，不冲动
- **价值优先级**：实用 > 理论；诚实 > 圆滑；严谨 > 速度

## 互动建议
- 提供背景信息有助于更高效沟通
- 避免模糊或假设性问题，偏好具体讨论

## 回答边界
- 此为 AI 模拟角色，不得用于冒充真人
- 禁止用于诈骗、骚扰、伪造授权、伪造遗嘱、法律/医疗/财务决定

## 资料覆盖说明
- 当前为 Mock 模式，上传真实资料并连接 LLM Provider 后可获得真实分析
- 资料可能存在偏差，分析结果仅供参考
"""


class OpenAICompatibleProvider(BaseLLMProvider):
    """Generic OpenAI-compatible API provider (OpenAI, DeepSeek, OpenRouter, etc.)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        analysis_model: str,
        chat_model: str,
        timeout: int = 120,
        provider: str = "openai",
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._analysis_model = analysis_model
        self._chat_model = chat_model
        self._timeout = timeout
        self._provider = provider

    @property
    def model_name(self) -> str:
        return self._chat_model

    @property
    def provider_name(self) -> str:
        return self._provider

    @property
    def analysis_model_name(self) -> str:
        return self._analysis_model

    @property
    def chat_model_name(self) -> str:
        return self._chat_model

    def _mask_key(self) -> str:
        """Return masked API key for logging."""
        k = self._api_key
        if len(k) <= 8:
            return "***"
        return k[:4] + "***" + k[-4:]

    def _check_api_key(self):
        if not self._api_key:
            msg = (
                f"LLM Provider '{self._provider}' requires an API key. "
                f"Please set LLM_API_KEY in your .env file. "
                f"Or set LLM_PROVIDER=mock to use demo mode."
            )
            logger.error(msg)
            raise LLMError(msg)

    async def _call_api(
        self, messages: list[dict], model: str, temperature: float, max_tokens: int,
    ) -> str:
        self._check_api_key()
        url = f"{self._base_url}/chat/completions"
        timeout = httpx.Timeout(self._timeout)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
            except httpx.TimeoutException:
                logger.error(f"LLM API timeout after {self._timeout}s for {model}")
                raise LLMError(
                    f"API 调用超时（{self._timeout}秒）。请检查网络或增加 LLM_TIMEOUT_SECONDS。"
                )
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                body = e.response.text[:500]
                logger.error(
                    f"LLM API error {status} for {model}: {body} "
                    f"[key={self._mask_key()}]"
                )
                if status == 401:
                    raise LLMError(
                        "API Key 无效或未授权。请检查 .env 中的 LLM_API_KEY。"
                    )
                if status == 402:
                    raise LLMError(
                        "API 余额不足。请检查账户余额。"
                    )
                if status == 429:
                    raise LLMError(
                        "API 调用频率过高，请稍后重试。"
                    )
                raise LLMError(
                    f"API 调用失败 (HTTP {status}): {body[:300]}"
                )
            except Exception as e:
                logger.error(f"LLM API unexpected error for {model}: {e}")
                raise LLMError(f"API 调用异常: {e}")

        try:
            data = resp.json()
        except Exception:
            logger.error(f"Failed to parse API response as JSON: {resp.text[:300]}")
            raise LLMError("API 返回的不是有效的 JSON。请检查 provider 配置。")

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error(
                f"Unexpected API response structure: {json.dumps(data, ensure_ascii=False)[:500]}"
            )
            raise LLMError(
                f"API 返回的数据结构异常，无法提取回复内容。请检查 LLM_BASE_URL 和模型名是否正确。"
            )

    async def generate_analysis(
        self, system_prompt: str, user_prompt: str,
        temperature: float = 0.5, max_tokens: int = 4096,
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self._call_api(
            messages=messages,
            model=self._analysis_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def generate_chat_reply(
        self, messages: list[dict],
        temperature: float = 0.8, max_tokens: int = 2048,
    ) -> str:
        return await self._call_api(
            messages=messages,
            model=self._chat_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self._check_api_key()
        url = f"{self._base_url}/embeddings"
        timeout = httpx.Timeout(60)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "text-embedding-3-small",
                    "input": texts,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data["data"]]


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek-specific provider with its own defaults.

    DeepSeek uses an OpenAI-compatible API at https://api.deepseek.com.
    Recommended models:
      - deepseek-chat (V3, general purpose)
      - deepseek-reasoner (R1, reasoning-focused)
    """

    def __init__(
        self,
        api_key: str,
        analysis_model: str = "deepseek-chat",
        chat_model: str = "deepseek-chat",
        timeout: int = 120,
    ):
        super().__init__(
            base_url="https://api.deepseek.com",
            api_key=api_key,
            analysis_model=analysis_model,
            chat_model=chat_model,
            timeout=timeout,
            provider="deepseek",
        )


# ── Factory ──

def get_llm_provider() -> BaseLLMProvider:
    settings = get_settings()

    if settings.is_mock:
        return MockLLMProvider()

    provider_type = settings.llm_provider.lower()
    base_url = settings.llm_base_url
    api_key = settings.llm_api_key
    analysis_model = settings.analysis_model
    chat_model = settings.chat_model
    timeout = settings.llm_timeout_seconds

    if provider_type == "deepseek":
        return DeepSeekProvider(
            api_key=api_key,
            analysis_model=analysis_model,
            chat_model=chat_model,
            timeout=timeout,
        )

    # Generic OpenAI-compatible
    return OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        analysis_model=analysis_model,
        chat_model=chat_model,
        timeout=timeout,
        provider=provider_type,
    )


def get_embedding_provider() -> BaseLLMProvider:
    settings = get_settings()
    if settings.is_mock:
        return MockLLMProvider()
    return OpenAICompatibleProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        analysis_model=settings.analysis_model,
        chat_model=settings.chat_model,
        timeout=settings.llm_timeout_seconds,
        provider=settings.llm_provider,
    )


def get_config_status() -> dict:
    """Return safe config status for the /api/config/status endpoint.

    NEVER returns the API key. Only safe info.
    """
    settings = get_settings()
    provider = get_llm_provider()

    return {
        "llm_provider": settings.provider_name,
        "is_mock": settings.is_mock,
        "analysis_model": provider.analysis_model_name if hasattr(provider, "analysis_model_name") else provider.model_name,
        "chat_model": provider.chat_model_name if hasattr(provider, "chat_model_name") else provider.model_name,
        "base_url": settings.llm_base_url if not settings.is_mock else "n/a (mock)",
        "has_api_key": bool(settings.llm_api_key),
        "timeout_seconds": settings.llm_timeout_seconds,
    }
