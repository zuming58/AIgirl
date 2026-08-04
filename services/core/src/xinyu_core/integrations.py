from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .contracts import (
    CalendarEventRecord,
    CalendarResponse,
    ExternalProviderStatus,
    WeatherCurrent,
    WeatherResponse,
)


class WeatherProvider(ABC):
    id = "unknown"

    @property
    def configured(self) -> bool:
        return True

    @property
    def authorized(self) -> bool:
        return False

    @abstractmethod
    async def current(self) -> WeatherCurrent:
        raise NotImplementedError


class CalendarProvider(ABC):
    id = "unknown"

    @property
    def configured(self) -> bool:
        return True

    @property
    def authorized(self) -> bool:
        return False

    @abstractmethod
    async def events(
        self, start: datetime, end: datetime
    ) -> list[CalendarEventRecord]:
        raise NotImplementedError


class DisabledWeatherProvider(WeatherProvider):
    id = "disabled"

    @property
    def configured(self) -> bool:
        return False

    async def current(self) -> WeatherCurrent:
        raise RuntimeError("weather_not_configured")


class DisabledCalendarProvider(CalendarProvider):
    id = "disabled"

    @property
    def configured(self) -> bool:
        return False

    async def events(
        self, start: datetime, end: datetime
    ) -> list[CalendarEventRecord]:
        raise RuntimeError("calendar_not_configured")


class DesktopIntegrationService:
    def __init__(
        self,
        weather: WeatherProvider | None = None,
        calendar: CalendarProvider | None = None,
    ) -> None:
        self.weather = weather or DisabledWeatherProvider()
        self.calendar = calendar or DisabledCalendarProvider()

    @staticmethod
    def _status(kind: str, provider) -> ExternalProviderStatus:
        if not provider.configured:
            return ExternalProviderStatus(
                kind=kind,
                provider=provider.id,
                status="disabled",
                authorized=False,
                error_code=f"{kind}_not_configured",
            )
        if not provider.authorized:
            return ExternalProviderStatus(
                kind=kind,
                provider=provider.id,
                status="disabled",
                authorized=False,
                error_code=f"{kind}_authorization_required",
            )
        return ExternalProviderStatus(
            kind=kind,
            provider=provider.id,
            status="ready",
            authorized=True,
            error_code=None,
        )

    def statuses(self) -> list[ExternalProviderStatus]:
        return [
            self._status("weather", self.weather),
            self._status("calendar", self.calendar),
        ]

    async def current_weather(self) -> WeatherResponse:
        status = self._status("weather", self.weather)
        if status.status != "ready":
            return WeatherResponse(status=status)
        try:
            return WeatherResponse(
                status=status, current=await self.weather.current()
            )
        except Exception:
            return WeatherResponse(
                status=status.model_copy(
                    update={
                        "status": "degraded",
                        "error_code": "weather_provider_failed",
                    }
                )
            )

    async def calendar_events(
        self, start: datetime, end: datetime
    ) -> CalendarResponse:
        status = self._status("calendar", self.calendar)
        if status.status != "ready":
            return CalendarResponse(status=status)
        try:
            events = await self.calendar.events(start, end)
            return CalendarResponse(status=status, events=events)
        except Exception:
            return CalendarResponse(
                status=status.model_copy(
                    update={
                        "status": "degraded",
                        "error_code": "calendar_provider_failed",
                    }
                )
            )
