"""Sunrise engine: runs the curve over lamp drivers."""
import asyncio
import logging
import time
from typing import Protocol


class Driver(Protocol):
    name: str

    @property
    def ready(self) -> bool: ...
    @property
    def recovering(self) -> bool: ...
    async def start(self) -> None: ...
    async def update(self, p: float) -> None: ...
    async def off(self) -> None: ...
    async def close(self) -> None: ...


log = logging.getLogger("sunlight.engine")


class Sunrise:
    """Drive all lamps along one progress value p (0 -> 1)."""

    def __init__(self, drivers, total_s: float, mode: str = "alarm", tick: float = 0.4, clock=time.time,
                 max_pause_s: float = 60.0):
        assert mode in ("alarm", "demo")
        self.drivers, self.total, self.mode, self.tick, self.clock = drivers, total_s, mode, tick, clock
        self.max_pause_s = max_pause_s
        self.progress = 0.0
        self.running = False
        self._stop = asyncio.Event()
        self._finish_now = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    def finish_now(self) -> None:
        """Ask the run to jump straight to full brightness and end as 'done'."""
        self._finish_now.set()

    async def _wait_wake(self, s: float) -> str | None:
        """Sleep up to s seconds; return 'stop', 'finish', or None on plain timeout."""
        stop_task = asyncio.create_task(self._stop.wait())
        finish_task = asyncio.create_task(self._finish_now.wait())
        try:
            done, pending = await asyncio.wait(
                {stop_task, finish_task}, timeout=s, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for t in (stop_task, finish_task):
                if not t.done():
                    t.cancel()
        # "Lights off" always wins over "I'm up", even if both fired the same tick.
        if stop_task in done or self._stop.is_set():
            return "stop"
        if finish_task in done:
            return "finish"
        return None

    async def _finish_now_done(self) -> str:
        if self._stop.is_set():
            return await self._finish("stopped", lamps_off=True)
        self.progress = 1.0
        for d in self.drivers:
            try:
                await d.update(1.0)
            except Exception:
                log.exception("%s update failed", d.name)
        if self._stop.is_set():
            return await self._finish("stopped", lamps_off=True)
        return await self._finish("done", lamps_off=False)

    async def run(self, begin_at: float | None = None) -> str:
        self.running = True
        try:
            for d in self.drivers:
                await d.start()
            begin_at = self.clock() if begin_at is None else begin_at
            while self.clock() < begin_at:                       # early connect window
                w = await self._wait_wake(min(self.tick, 1.0))
                if w == "finish":
                    return await self._finish_now_done()
                if w == "stop":
                    return await self._finish("stopped", lamps_off=True)
            elapsed, last = 0.0, self.clock()
            pause_started = None
            pause_warned = False
            while True:
                now = self.clock()
                if self.mode == "alarm":
                    elapsed = now - begin_at
                else:
                    paused = any(d.recovering for d in self.drivers)
                    if paused:
                        if pause_started is None:
                            pause_started = now
                        if now - pause_started > self.max_pause_s:
                            if not pause_warned:
                                log.warning(
                                    "demo paused > %.0fs waiting on a recovering driver; advancing anyway",
                                    self.max_pause_s,
                                )
                                pause_warned = True
                            elapsed += now - last
                    else:
                        pause_started = None
                        pause_warned = False
                        elapsed += now - last
                last = now
                self.progress = min(1.0, max(0.0, elapsed / self.total))
                for d in self.drivers:
                    try:
                        await d.update(self.progress)
                    except Exception:
                        log.exception("%s update failed", d.name)
                if self.progress >= 1.0:
                    return await self._finish("done", lamps_off=False)
                w = await self._wait_wake(self.tick)
                if w == "finish":
                    return await self._finish_now_done()
                if w == "stop":
                    return await self._finish("stopped", lamps_off=True)
        finally:
            self.running = False

    async def _finish(self, result: str, lamps_off: bool) -> str:
        for d in self.drivers:
            try:
                if lamps_off:
                    await d.off()
                await d.close()
            except Exception:
                log.exception("%s shutdown failed", d.name)
        log.info("sunrise %s (p=%.2f)", result, self.progress)
        return result
