from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from .config import AppConfig
from .contracts import MessageRecord, PersonaRecord


class ChatProvider(ABC):
    id = "unknown"

    @abstractmethod
    async def reply(
        self,
        message: str,
        history: list[MessageRecord],
        persona: PersonaRecord,
        memories: list[str],
        conversation_summary: str | None = None,
    ) -> str:
        raise NotImplementedError


class DevelopmentCompanionProvider(ChatProvider):
    id = "development-fallback"

    async def reply(
        self,
        message: str,
        history: list[MessageRecord],
        persona: PersonaRecord,
        memories: list[str],
        conversation_summary: str | None = None,
    ) -> str:
        normalized = message.strip()
        if any(token in normalized for token in ("累", "难受", "焦虑", "烦")):
            return "我听见了。先不用急着把所有问题解决，我们把最让你累的那一件事慢慢说清楚。"
        if any(token in normalized for token in ("晚安", "睡觉", "休息")):
            return "好，今晚先到这里。把没做完的事留给明天，我会记得我们聊到哪里。晚安。"
        if any(token in normalized for token in ("计划", "提醒", "待办")):
            return "可以。你把要做的事和大概时间告诉我，我会把它放进计划里，并让你随时能修改。"
        if memories:
            return f"我记得你之前提过{memories[0]}。这次听起来又多了一点新的感受，你愿意继续说吗？"
        return "我在听。你不用一次把所有事都想清楚，我们可以从现在最想说的这一点开始。"


class OpenAICompatibleProvider(ChatProvider):
    id = "openai-compatible"

    def __init__(self, config: AppConfig) -> None:
        if not config.llm_base_url:
            raise ValueError("llm_base_url is required")
        self.base_url = config.llm_base_url.rstrip("/")
        self.model = config.llm_model
        self.api_key = config.llm_api_key

    async def reply(
        self,
        message: str,
        history: list[MessageRecord],
        persona: PersonaRecord,
        memories: list[str],
        conversation_summary: str | None = None,
    ) -> str:
        system = (
            f"你是{persona.name}，角色是{persona.relationship_role}。"
            f"{persona.background}\n"
            "回答要自然、简短、适合朗读；尊重用户边界，不假装工具已经执行。"
        )
        if memories:
            system += "\n可引用但不要过度强调的相关记忆：\n- " + "\n- ".join(memories[:5])
        if conversation_summary:
            system += (
                "\n以下是用户可查看和管理的既有对话摘要，仅用于保持上下文，"
                "不要把其中未确认内容升级为事实：\n"
                + conversation_summary[:8_000]
            )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.extend(
            {"role": item.role, "content": item.content}
            for item in history[-12:]
            if item.role in {"user", "assistant"}
        )
        messages.append({"role": "user", "content": message})
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        return payload["choices"][0]["message"]["content"].strip()


def create_provider(config: AppConfig) -> ChatProvider:
    if config.llm_base_url:
        return OpenAICompatibleProvider(config)
    return DevelopmentCompanionProvider()
