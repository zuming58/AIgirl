from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, time, timezone
from typing import Protocol

from .contracts import EventEnvelope
from .repository import Repository


class EventPublisher(Protocol):
    async def publish(self, event: EventEnvelope) -> None: ...


def _parse_clock(value: str) -> time | None:
    try:
        hours, minutes = value.split(":", maxsplit=1)
        return time(hour=int(hours), minute=int(minutes))
    except (AttributeError, TypeError, ValueError):
        return None


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def is_quiet_time(value: object, current: datetime) -> bool:
    if not isinstance(value, str) or "-" not in value:
        return False
    start_text, end_text = value.split("-", maxsplit=1)
    start = _parse_clock(start_text)
    end = _parse_clock(end_text)
    if start is None or end is None:
        return False
    local_time = current.astimezone().time().replace(tzinfo=None)
    if start <= end:
        return start <= local_time < end
    return local_time >= start or local_time < end


class ReminderScheduler:
    def __init__(
        self,
        repository: Repository,
        events: EventPublisher,
        poll_interval_seconds: float = 5,
    ) -> None:
        self.repository = repository
        self.events = events
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def dispatch_due(self, now: datetime | None = None) -> int:
        settings = self.repository.get_settings()
        if not settings.get("privacy.proactive_enabled", True):
            return 0
        current = now or datetime.now(timezone.utc)
        if is_quiet_time(settings.get("privacy.quiet_hours"), current):
            return 0

        claimed = self.repository.claim_due_plan_reminders(current)
        for item in claimed:
            await self.events.publish(
                EventEnvelope(
                    type="plan.reminder_due",
                    payload={
                        "notification_id": item["event_id"],
                        "task": item["task"],
                    },
                )
            )
            self.repository.mark_proactive_event_delivered(item["event_id"])

        checkin = None
        if settings.get("proactive.checkin_enabled", True):
            checkin = self.repository.claim_proactive_checkin(
                current,
                daily_limit=_bounded_int(
                    settings.get("proactive.daily_limit"),
                    default=2,
                    minimum=0,
                    maximum=8,
                ),
                cooldown_minutes=_bounded_int(
                    settings.get("proactive.cooldown_minutes"),
                    default=240,
                    minimum=30,
                    maximum=1440,
                ),
                inactivity_minutes=_bounded_int(
                    settings.get("proactive.inactivity_minutes"),
                    default=240,
                    minimum=30,
                    maximum=10080,
                ),
            )
        if checkin:
            await self.events.publish(
                EventEnvelope(
                    type="companion.checkin_due",
                    payload={
                        "notification_id": checkin["event_id"],
                        "message": checkin["message"],
                        "reason": checkin["reason"],
                        "kind": checkin["kind"],
                    },
                )
            )
            self.repository.mark_proactive_event_delivered(checkin["event_id"])
        return len(claimed) + int(checkin is not None)

    async def _run(self) -> None:
        while True:
            await self.dispatch_due()
            await asyncio.sleep(self.poll_interval_seconds)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
