import asyncio
from datetime import datetime, timedelta
import sunlight.scheduler as scheduler_mod
from sunlight.scheduler import Scheduler, next_start
from sunlight.settings import Settings


def dt(s): return datetime.fromisoformat(s)


def test_next_start_today():
    # Mon 2026-09-28 05:00, wake 06:30, 30 min -> starts 06:00 today
    assert next_start(Settings(), dt("2026-09-28T05:00")) == dt("2026-09-28T06:00")


def test_next_start_after_todays_start_goes_to_tomorrow():
    assert next_start(Settings(), dt("2026-09-28T06:01")) == dt("2026-09-29T06:00")


def test_next_start_skips_weekend():
    # Fri 2026-10-02 07:00 -> Mon 2026-10-05 06:00
    assert next_start(Settings(), dt("2026-10-02T07:00")) == dt("2026-10-05T06:00")


def test_midnight_wrap_uses_wake_day():
    s = Settings(wake="00:10", days=[1], length_min=30)       # Tuesday wake
    # Mon 2026-09-28 20:00 -> starts Mon 23:40 for Tue 00:10
    assert next_start(s, dt("2026-09-28T20:00")) == dt("2026-09-28T23:40")


def test_disabled_or_no_days():
    assert next_start(Settings(enabled=False), dt("2026-09-28T05:00")) is None
    assert next_start(Settings(days=[]), dt("2026-09-28T05:00")) is None


class FakeDriver:
    def __init__(self): self.events, self._ready = [], True
    name = "fake"
    @property
    def ready(self): return self._ready
    @property
    def recovering(self): return False
    async def start(self): self.events.append("start")
    async def update(self, p): self.events.append(("p", round(p, 2)))
    async def off(self): self.events.append("off")
    async def close(self): self.events.append("close")


async def test_demo_runs_and_reports():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(), lambda s: [d])
    result = await sch.demo(0.05)
    assert result == "done"
    assert d.events[0] == "start" and ("p", 1.0) in d.events
    assert sch.status()["last_result"].startswith("demo: done")


async def test_stop_cancels_demo():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(), lambda s: [d])
    task = asyncio.create_task(sch.demo(60))
    await asyncio.sleep(0.05)
    assert sch.status()["state"] == "demo"
    sch.stop()
    assert await asyncio.wait_for(task, 2) == "stopped"
    assert "off" in d.events


async def _drain(sch):
    """Await any tasks the scheduler is still tracking (e.g. from stop())."""
    tasks = list(sch._tasks)
    if tasks:
        await asyncio.gather(*tasks)


async def test_alarm_done_then_hold_then_lamps_off():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(length_min=0.001, hold_min=0), lambda s: [d])
    await sch._alarm(datetime.now())
    assert sch.last_result.startswith("alarm: done")
    assert sch.state == "idle"
    assert "off" in d.events


async def test_alarm_stay_on_keeps_lamps_lit_until_stop():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(length_min=0.001, stay_on=True), lambda s: [d])
    await sch._alarm(datetime.now())
    assert sch.last_result.startswith("alarm: done")
    assert sch.state == "idle"
    assert "off" not in d.events   # lamps stay lit: no auto-off for stay_on

    sch.stop()
    await _drain(sch)
    assert "off" in d.events


async def test_stop_when_idle_after_stay_on_turns_lamps_off():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(length_min=0.001, stay_on=True), lambda s: [d])
    await sch._alarm(datetime.now())
    assert sch.state == "idle"

    sch.stop()
    await _drain(sch)
    assert d.events[-1] == "close"
    assert "off" in d.events


async def test_stop_when_idle_and_lamps_off_makes_no_driver_calls():
    d = FakeDriver()
    made = []

    def make_drivers(s):
        made.append(d)
        return [d]

    sch = Scheduler(lambda: Settings(length_min=0.001, hold_min=0), make_drivers)
    await sch._alarm(datetime.now())  # normal alarm: done, lamps auto-off
    assert sch.state == "idle"
    assert "off" in d.events
    made.clear()
    d.events.clear()

    sch.stop()
    await _drain(sch)
    assert d.events == []
    assert made == []


async def test_alarm_with_no_lamps_sets_last_result():
    sch = Scheduler(lambda: Settings(), lambda s: [])
    await sch._alarm(datetime.now())
    assert sch.last_result.startswith("alarm: skipped")
    assert "no lamps enabled" in sch.last_result
    assert sch.state == "idle"


async def test_demo_wake_up_finishes_lit_no_off_then_stop_turns_off():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(), lambda s: [d])
    task = asyncio.create_task(sch.demo(60))
    await asyncio.sleep(0.05)
    assert sch.wake_up() is True
    result = await asyncio.wait_for(task, 2)
    assert result == "done"
    assert "off" not in d.events
    assert sch._lamps_may_be_lit is True

    sch.stop()
    await _drain(sch)
    assert "off" in d.events


async def test_alarm_wake_up_mid_sunrise_proceeds_to_hold_and_auto_off():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(length_min=1, hold_min=0), lambda s: [d])
    task = asyncio.create_task(sch._alarm(datetime.now()))
    await asyncio.sleep(0.05)
    assert sch.wake_up() is True
    await asyncio.wait_for(task, 2)
    assert sch.last_result.startswith("alarm: done")
    assert sch.state == "idle"
    assert "off" in d.events


async def test_wake_up_when_idle_does_nothing():
    sch = Scheduler(lambda: Settings(), lambda s: [])
    assert sch.wake_up() is False


async def test_demo_wake_up_and_stop_same_tick_lamps_off():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(), lambda s: [d])
    task = asyncio.create_task(sch.demo(60))
    await asyncio.sleep(0.05)
    assert sch.wake_up() is True
    sch.stop()
    result = await asyncio.wait_for(task, 2)
    await _drain(sch)
    assert result == "stopped"
    assert "off" in d.events


async def test_loop_fires_alarm_once_and_tracks_task(monkeypatch):
    monkeypatch.setattr(scheduler_mod, "TICK_S", 0.01)
    monkeypatch.setattr(scheduler_mod, "PRECONNECT_S", 2)

    calls = []
    starts = [datetime.now() + timedelta(seconds=1), None]

    def fake_next_start(settings, now):
        return starts.pop(0) if starts else None

    monkeypatch.setattr(scheduler_mod, "next_start", fake_next_start)

    sch = Scheduler(lambda: Settings(), lambda s: [])

    seen_in_tasks = []

    async def fake_alarm(start):
        calls.append(start)
        seen_in_tasks.append(len(sch._tasks) >= 1)
        await asyncio.sleep(0.2)

    sch._alarm = fake_alarm

    task = asyncio.create_task(sch.loop())
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(calls) == 1
    assert seen_in_tasks == [True]


async def test_sunrise_now_runs_alarm_mode_immediately_and_reports():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(hold_min=0), lambda s: [d])
    sch.start_sunrise_now(0.001)
    await asyncio.sleep(0.2)
    await _drain(sch)
    assert d.events[0] == "start" and ("p", 1.0) in d.events
    assert sch.last_result.startswith("sunrise-now: done")
    assert "off" in d.events
    assert sch.state == "idle"


async def test_sunrise_now_stop_mid_run():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(hold_min=0), lambda s: [d])
    sch.start_sunrise_now(1)
    await asyncio.sleep(0.05)
    assert sch.state == "sunrise"
    sch.stop()
    await asyncio.sleep(0.1)
    await _drain(sch)
    assert sch.last_result.startswith("sunrise-now: stopped")
    assert "off" in d.events


async def test_sunrise_now_wake_up_mid_run_goes_to_done_then_auto_off():
    d = FakeDriver()
    sch = Scheduler(lambda: Settings(hold_min=0), lambda s: [d])
    sch.start_sunrise_now(1)
    await asyncio.sleep(0.05)
    assert sch.wake_up() is True
    await asyncio.sleep(0.1)
    await _drain(sch)
    assert sch.last_result.startswith("sunrise-now: done")
    assert "off" in d.events
