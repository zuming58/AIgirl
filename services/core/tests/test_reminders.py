import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from xinyu_core.contracts import PlanCreate
from xinyu_core.database import Database
from xinyu_core.reminders import ReminderScheduler, is_quiet_time
from xinyu_core.repository import Repository


class RecordingEvents:
    def __init__(self) -> None:
        self.items = []

    async def publish(self, event) -> None:
        self.items.append(event)


def make_repository(tmp_path: Path) -> Repository:
    database = Database(tmp_path / "reminders.db")
    database.initialize()
    return Repository(database)


def test_due_plan_reminder_is_delivered_exactly_once(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.set_setting("privacy.quiet_hours", "invalid")
    now = datetime.now(timezone.utc)
    plan = repository.create_plan(
        PlanCreate(
            title="十分钟后开会",
            due_at=now + timedelta(minutes=10),
            reminder_at=now - timedelta(seconds=1),
        )
    )
    events = RecordingEvents()
    scheduler = ReminderScheduler(repository, events)

    assert asyncio.run(scheduler.dispatch_due(now)) == 1
    assert asyncio.run(scheduler.dispatch_due(now + timedelta(seconds=5))) == 0
    assert events.items[0].type == "plan.reminder_due"
    assert events.items[0].payload["task"]["id"] == plan.id

    exported = repository.export_data().data["proactive_events"]
    assert exported[0]["status"] == "delivered"
    notifications = repository.list_notifications()
    assert len(notifications) == 1
    assert notifications[0].payload["task"]["id"] == plan.id
    acknowledged = repository.acknowledge_notification(notifications[0].id)
    assert acknowledged is not None
    assert acknowledged.status == "acknowledged"
    assert repository.list_notifications() == []
    assert len(repository.list_notifications(include_acknowledged=True)) == 1


def test_proactive_setting_disables_reminders(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.set_setting("privacy.proactive_enabled", False)
    repository.create_plan(
        PlanCreate(
            title="保持安静",
            reminder_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    events = RecordingEvents()

    assert asyncio.run(ReminderScheduler(repository, events).dispatch_due()) == 0
    assert events.items == []


def test_gentle_checkin_respects_inactivity_and_daily_budget(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    repository.set_setting("privacy.quiet_hours", "invalid")
    repository.set_setting("proactive.daily_limit", 1)
    repository.set_setting("proactive.cooldown_minutes", 30)
    repository.set_setting("proactive.inactivity_minutes", 30)
    now = datetime.now(timezone.utc)
    session_id = repository.ensure_session(None, "text")
    message = repository.add_message(session_id, "user", "晚点再聊")
    with repository.database.connect() as connection:
        connection.execute(
            "UPDATE messages SET created_at=? WHERE id=?",
            ((now - timedelta(hours=5)).isoformat(), message.id),
        )
    events = RecordingEvents()
    scheduler = ReminderScheduler(repository, events)

    assert asyncio.run(scheduler.dispatch_due(now)) == 1
    assert asyncio.run(scheduler.dispatch_due(now + timedelta(hours=1))) == 0
    assert events.items[0].type == "companion.checkin_due"
    assert "距离上次交流" in events.items[0].payload["reason"]

    notifications = repository.list_notifications()
    assert len(notifications) == 1
    assert notifications[0].event_type == "companion.checkin_due"
    assert notifications[0].reason == "inactivity_checkin"
    assert notifications[0].payload["kind"] == "gentle_checkin"


def test_checkin_category_can_be_disabled_independently(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.set_setting("privacy.quiet_hours", "invalid")
    repository.set_setting("proactive.checkin_enabled", False)
    session_id = repository.ensure_session(None, "text")
    repository.add_message(session_id, "user", "先忙一会儿")
    events = RecordingEvents()

    assert (
        asyncio.run(
            ReminderScheduler(repository, events).dispatch_due(
                datetime.now(timezone.utc) + timedelta(days=1)
            )
        )
        == 0
    )
    assert events.items == []


def test_quiet_hours_support_ranges_that_cross_midnight() -> None:
    local_zone = datetime.now().astimezone().tzinfo
    late = datetime(2026, 7, 29, 23, 45, tzinfo=local_zone)
    morning = datetime(2026, 7, 30, 7, 30, tzinfo=local_zone)
    daytime = datetime(2026, 7, 30, 12, 0, tzinfo=local_zone)

    assert is_quiet_time("23:30-08:00", late) is True
    assert is_quiet_time("23:30-08:00", morning) is True
    assert is_quiet_time("23:30-08:00", daytime) is False


def test_quiet_hours_use_configured_timezone_across_dst_boundaries() -> None:
    before_spring_jump = datetime(2026, 3, 8, 6, 45, tzinfo=timezone.utc)
    after_spring_jump = datetime(2026, 3, 8, 7, 15, tzinfo=timezone.utc)
    repeated_fall_hour = datetime(2026, 11, 1, 6, 15, tzinfo=timezone.utc)

    assert (
        is_quiet_time(
            "01:30-03:30",
            before_spring_jump,
            "America/New_York",
        )
        is True
    )
    assert (
        is_quiet_time(
            "01:30-03:30",
            after_spring_jump,
            "America/New_York",
        )
        is True
    )
    assert (
        is_quiet_time(
            "01:00-02:00",
            repeated_fall_hour,
            "America/New_York",
        )
        is True
    )


def test_invalid_notification_timezone_falls_back_without_error() -> None:
    current = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    assert isinstance(is_quiet_time("23:30-08:00", current, "Invalid/Zone"), bool)
