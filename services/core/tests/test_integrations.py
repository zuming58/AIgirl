import asyncio
from datetime import datetime, timedelta, timezone

from xinyu_core.contracts import CalendarEventRecord, WeatherCurrent
from xinyu_core.integrations import (
    CalendarProvider,
    DesktopIntegrationService,
    WeatherProvider,
)


class FakeWeather(WeatherProvider):
    id = "fake-weather"

    @property
    def authorized(self) -> bool:
        return True

    async def current(self) -> WeatherCurrent:
        return WeatherCurrent(
            location_label="测试城市",
            observed_at=datetime(2026, 8, 4, 8, tzinfo=timezone.utc),
            condition="晴",
            temperature_c=26.5,
            feels_like_c=27.0,
            humidity_percent=61,
        )


class FakeCalendar(CalendarProvider):
    id = "fake-calendar"

    @property
    def authorized(self) -> bool:
        return True

    async def events(self, start, end):
        return [
            CalendarEventRecord(
                id="event-1",
                title="测试日程",
                starts_at=start + timedelta(hours=1),
                ends_at=start + timedelta(hours=2),
            )
        ]


def test_integrations_default_to_honest_disabled_state() -> None:
    service = DesktopIntegrationService()

    weather = asyncio.run(service.current_weather())
    calendar = asyncio.run(
        service.calendar_events(
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=1),
        )
    )

    assert weather.status.status == "disabled"
    assert weather.status.error_code == "weather_not_configured"
    assert weather.current is None
    assert calendar.status.status == "disabled"
    assert calendar.status.error_code == "calendar_not_configured"
    assert calendar.events == []


def test_authorized_fake_providers_return_contract_data() -> None:
    service = DesktopIntegrationService(FakeWeather(), FakeCalendar())
    start = datetime(2026, 8, 4, tzinfo=timezone.utc)

    weather = asyncio.run(service.current_weather())
    calendar = asyncio.run(
        service.calendar_events(start, start + timedelta(days=1))
    )

    assert weather.status.status == "ready"
    assert weather.current.location_label == "测试城市"
    assert calendar.status.status == "ready"
    assert calendar.events[0].title == "测试日程"
    assert "token" not in weather.model_dump_json().lower()


def test_provider_failures_are_isolated_and_redacted() -> None:
    class FailingWeather(FakeWeather):
        async def current(self):
            raise RuntimeError("secret-token-and-endpoint")

    response = asyncio.run(
        DesktopIntegrationService(FailingWeather()).current_weather()
    )

    assert response.status.status == "degraded"
    assert response.status.error_code == "weather_provider_failed"
    assert "secret" not in response.model_dump_json().lower()
