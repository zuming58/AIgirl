from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

import httpx

from .config import AppConfig
from .contracts import ConversationSummaryRecord, MessageRecord
from .repository import Repository


class SummaryProvider(ABC):
    id = "unknown"
    model = "unknown"

    @property
    def configured(self) -> bool:
        return True

    @abstractmethod
    async def summarize(
        self,
        messages: list[MessageRecord],
        previous_summary: str | None,
    ) -> str:
        raise NotImplementedError


class DisabledSummaryProvider(SummaryProvider):
    id = "disabled"

    def __init__(self, model: str) -> None:
        self.model = model

    @property
    def configured(self) -> bool:
        return False

    async def summarize(
        self,
        messages: list[MessageRecord],
        previous_summary: str | None,
    ) -> str:
        raise RuntimeError("llm_not_configured")


class OpenAISummaryProvider(SummaryProvider):
    id = "openai-compatible"

    def __init__(self, config: AppConfig) -> None:
        if not config.llm_base_url:
            raise ValueError("llm_base_url is required")
        self.base_url = config.llm_base_url.rstrip("/")
        self.model = config.llm_model
        self.api_key = config.llm_api_key

    async def summarize(
        self,
        messages: list[MessageRecord],
        previous_summary: str | None,
    ) -> str:
        transcript = "\n".join(f"{item.role}: {item.content}" for item in messages)
        prompt = (
            "请把以下本地对话整理成简洁、可核对的上下文摘要。只保留用户明确表达的事实、"
            "已确认偏好、承诺、未解决话题和情绪背景；不要把猜测写成事实，不要创建新记忆。\n"
        )
        if previous_summary:
            prompt += f"已有摘要：\n{previous_summary}\n\n"
        prompt += f"新增对话：\n{transcript}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "你是本地对话摘要器。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        return payload["choices"][0]["message"]["content"].strip()


def create_summary_provider(config: AppConfig) -> SummaryProvider:
    if config.llm_base_url:
        return OpenAISummaryProvider(config)
    return DisabledSummaryProvider(config.llm_model)


class ConversationSummaryService:
    def __init__(self, repository: Repository, provider: SummaryProvider) -> None:
        self.repository = repository
        self.provider = provider
        self._tasks: set[asyncio.Task[None]] = set()

    def maybe_schedule(self, session_id: str) -> ConversationSummaryRecord | None:
        message_count = self.repository.count_messages(session_id)
        coverage = self.repository.latest_summary_coverage(session_id)
        if message_count < 24 or message_count - 12 - coverage < 12:
            return None
        return self.schedule(session_id)

    def schedule(
        self,
        session_id: str,
        *,
        force: bool = False,
    ) -> ConversationSummaryRecord:
        messages = self.repository.summary_messages(session_id, keep_recent=12)
        if not messages:
            raise ValueError("not_enough_messages_for_summary")
        previous = self.repository.active_summary(session_id)
        coverage = self.repository.latest_summary_coverage(session_id)
        incremental = messages if force else (messages[coverage:] if previous else messages)
        record = self.repository.create_summary_job(
            session_id,
            messages,
            self.provider.id,
            self.provider.model,
        )
        if not self.provider.configured:
            self.repository.fail_summary(record.id, "unavailable", "llm_not_configured")
            return self.repository.summary_job(record.id) or record
        previous_content = (
            previous.content if previous and not force else None
        )
        task = asyncio.create_task(
            self._generate(record.id, incremental, previous_content)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return record

    async def _generate(
        self,
        summary_id: str,
        messages: list[MessageRecord],
        previous_summary: str | None,
    ) -> None:
        try:
            content = await self.provider.summarize(messages, previous_summary)
            if not content:
                raise ValueError("empty_summary")
            self.repository.complete_summary(summary_id, content[:8_000])
        except Exception as error:
            self.repository.fail_summary(summary_id, "failed", type(error).__name__)

    def recover_pending(self) -> None:
        for summary_id in self.repository.pending_summary_ids():
            self.repository.fail_summary(summary_id, "failed", "process_restarted")

    async def close(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
