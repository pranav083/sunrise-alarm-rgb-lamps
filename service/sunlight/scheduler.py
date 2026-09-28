"""When to run the sunrise, plus hold / auto-off and demo runs."""
import asyncio
import logging
import time
from datetime import datetime, timedelta

from .engine import Sunrise

log = logging.getLogger("sunlight.scheduler")
PRECONNECT_S = 120
TICK_S = 30


def next_start(settings, now: datetime) -> datetime | None:
    if not settings.enabled or not settings.days:
        return None
    hh, mm = map(int, settings.wake.split(":"))
    for ahead in range(0, 9):
        wake = (now + timedelta(days=ahead)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        start = wake - timedelta(minutes=settings.length_min)
        if wake.weekday() in settings.days and start > now:
            return start
    return None


class Scheduler:
    def __init__(self, get_settings, make_drivers, power=None, clock=time.time):
        self.get_settings, self.make_drivers, self.power, self.clock = get_settings, make_drivers, power, clock
        self.state, self.last_result = "idle", None
        self._sunrise: Sunrise | None = None
        self._drivers = []
        self._lamps_may_be_lit = False
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    def _track(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def start_demo(self, seconds: float) -> None:
        self._track(self.demo(seconds))

    def start_sunrise_now(self, minutes: float) -> None:
        """Manual "sunrise now": real alarm-mode run starting immediately, ignoring settings.enabled."""
        self._track(self._alarm(datetime.now(), length_min=minutes, label="sunrise-now"))

    # ---------- status / control ----------
    def status(self) -> dict:
        ns = next_start(self.get_settings(), datetime.now())
        return {
            "state": self.state,
            "progress": round(self._sunrise.progress, 3) if self._sunrise else None,
            "next_start": ns.isoformat(timespec="minutes") if ns else None,
            "last_result": self.last_result,
            "lamps": {d.name: d.ready for d in self._drivers},
        }

    def stop(self) -> None:
        self._stop.set()
        if self._sunrise:
            self._sunrise.stop()
        if not self.running and self._lamps_may_be_lit:
            # Not mid-run, but lamps may still be lit after a "done" run
            # (stay_on, or holding before auto-off completes). Reconnect
            # fresh drivers just to switch them off.
            self._track(self._stop_all_off(self.get_settings()))

    def wake_up(self) -> bool:
        """"I'm up": jump the running alarm/demo straight to full brightness and 'done'."""
        if self.state in ("connecting", "sunrise", "demo") and self._sunrise:
            self._sunrise.finish_now()
            return True
        return False

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def _awake(self, on: bool) -> None:
        if self.power:
            self.power.keep_awake(on)

    # ---------- runs ----------
    async def demo(self, seconds: float) -> str:
        async with self._lock:
            self._stop.clear()
            s = self.get_settings()
            self._drivers = self.make_drivers(s)
            self._sunrise = Sunrise(self._drivers, seconds, mode="demo")
            self.state = "demo"
            try:
                result = await self._sunrise.run()
            finally:
                self.state = "idle"
            if result == "done":
                self._lamps_may_be_lit = True
            self.last_result = f"demo: {result} at {datetime.now():%H:%M}"
            return result

    async def _alarm(self, start: datetime, length_min: float | None = None, label: str = "alarm") -> None:
        async with self._lock:
            self._stop.clear()
            s = self.get_settings()
            self._drivers = self.make_drivers(s)
            if not self._drivers:
                log.warning("%s skipped: no lamps enabled at %s", label, f"{datetime.now():%H:%M}")
                self.last_result = f"{label}: skipped — no lamps enabled at {datetime.now():%H:%M}"
                return
            self._awake(True)
            try:
                minutes = s.length_min if length_min is None else length_min
                self._sunrise = Sunrise(self._drivers, minutes * 60, mode="alarm")
                self.state = "connecting"
                run = asyncio.create_task(self._sunrise.run(begin_at=start.timestamp()))
                while not run.done():
                    if self.clock() >= start.timestamp():
                        self.state = "sunrise"
                    await asyncio.sleep(1)
                result = run.result()
                self.last_result = f"{label}: {result} at {datetime.now():%H:%M}"
                if result == "done":
                    self._lamps_may_be_lit = True
                if result == "done" and not s.stay_on:
                    self.state = "holding"
                    try:
                        await asyncio.wait_for(self._stop.wait(), s.hold_min * 60)
                    except asyncio.TimeoutError:
                        pass
                    await self._all_off(s)
                    self._lamps_may_be_lit = False
            finally:
                self.state = "idle"
                self._awake(False)

    async def _stop_all_off(self, s) -> None:
        await self._all_off(s)
        self._lamps_may_be_lit = False

    async def _all_off(self, s) -> None:
        """Lamps were left lit after 'done'; reconnect fresh drivers just to switch them off."""
        drivers = self.make_drivers(s)
        for d in drivers:
            await d.start()
        for _ in range(30):
            if all(d.ready for d in drivers):
                break
            await asyncio.sleep(1)
        for d in drivers:
            await d.off()
            await d.close()

    async def loop(self) -> None:
        """Main scheduler loop: every TICK_S, start the alarm run PRECONNECT_S before sunrise."""
        armed_for = None
        while True:
            s = self.get_settings()
            start = next_start(s, datetime.now())
            if start and self.power and armed_for != start:
                await asyncio.to_thread(self.power.schedule_wake, start - timedelta(minutes=5))
                armed_for = start
            if start and (start - datetime.now()).total_seconds() <= PRECONNECT_S and not self._lock.locked():
                log.info("alarm run for sunrise starting %s", start)
                self._track(self._alarm(start))
                await asyncio.sleep(PRECONNECT_S + 5)   # don't re-trigger for the same start
                continue
            await asyncio.sleep(TICK_S)
