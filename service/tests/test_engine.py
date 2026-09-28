import asyncio
from sunlight.engine import Sunrise


class FakeDriver:
    def __init__(self, name="fake", ready=True, recovering=False):
        self.name, self._ready, self.ps, self.events = name, ready, [], []
        self._recovering = recovering

    @property
    def ready(self):
        return self._ready

    @property
    def recovering(self):
        # by default, mirror "down and expected to come back" only while explicitly set
        return self._recovering and not self._ready

    async def start(self): self.events.append("start")
    async def update(self, p): self.ps.append(p)
    async def off(self): self.events.append("off")
    async def close(self): self.events.append("close")


class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


async def drive(sunrise, clock, step, n):
    task = asyncio.create_task(sunrise.run(begin_at=clock.t))
    for _ in range(n):
        await asyncio.sleep(0)
        clock.t += step
        await asyncio.sleep(0.002)
    return await asyncio.wait_for(task, 2)


async def test_alarm_runs_to_one_and_reports_done():
    clock, d = FakeClock(), FakeDriver()
    s = Sunrise([d], total_s=10, tick=0.001, clock=clock)
    assert await drive(s, clock, 1.0, 15) == "done"
    assert d.ps[-1] == 1.0 and d.ps == sorted(d.ps)
    assert d.events[0] == "start"


async def test_demo_pauses_while_driver_down():
    clock, d = FakeClock(), FakeDriver()
    s = Sunrise([d], total_s=10, mode="demo", tick=0.001, clock=clock)
    task = asyncio.create_task(s.run(begin_at=clock.t))
    await asyncio.sleep(0.01); clock.t += 3; await asyncio.sleep(0.01)
    d._ready = False
    d._recovering = True                             # down but expected to come back
    clock.t += 5; await asyncio.sleep(0.01)          # 5 s of outage must not count
    frozen = s.progress
    d._ready = True
    d._recovering = False
    await asyncio.sleep(0.01)
    assert frozen < 0.5
    s.stop(); assert await task == "stopped"


async def test_demo_completes_when_driver_permanently_not_ready_and_not_recovering():
    # reproduces the production bug: a skipped lamp that never recovers must not
    # hold the demo clock (and the scheduler lock) forever.
    clock = FakeClock()
    d = FakeDriver(ready=False, recovering=False)
    s = Sunrise([d], total_s=10, mode="demo", tick=0.001, clock=clock)
    assert await drive(s, clock, 1.0, 15) == "done"


async def test_demo_advances_after_max_pause_when_driver_recovers_forever():
    clock = FakeClock()
    d = FakeDriver(ready=False, recovering=True)
    s = Sunrise([d], total_s=1, mode="demo", tick=0.001, clock=clock, max_pause_s=0.01)
    assert await drive(s, clock, 1.0, 15) == "done"


async def test_alarm_skips_ahead_after_outage():
    clock, d = FakeClock(), FakeDriver()
    s = Sunrise([d], total_s=10, tick=0.001, clock=clock)
    task = asyncio.create_task(s.run(begin_at=clock.t))
    await asyncio.sleep(0.01); d._ready = False
    clock.t += 6; await asyncio.sleep(0.01); d._ready = True; await asyncio.sleep(0.01)
    assert s.progress >= 0.6
    s.stop(); await task


async def test_stop_turns_lamps_off_and_closes():
    clock, d = FakeClock(), FakeDriver()
    s = Sunrise([d], total_s=100, tick=0.001, clock=clock)
    task = asyncio.create_task(s.run(begin_at=clock.t))
    await asyncio.sleep(0.01); s.stop()
    assert await task == "stopped"
    assert d.events[-2:] == ["off", "close"]


async def test_waits_for_begin_at():
    clock, d = FakeClock(), FakeDriver()
    s = Sunrise([d], total_s=10, tick=0.001, clock=clock)
    task = asyncio.create_task(s.run(begin_at=clock.t + 120))
    await asyncio.sleep(0.02)
    assert d.events == ["start"] and d.ps == []       # connected early, not started
    s.stop(); await task


async def test_finish_now_jumps_to_full_and_reports_done():
    clock, d = FakeClock(), FakeDriver()
    s = Sunrise([d], total_s=100, tick=0.001, clock=clock)
    task = asyncio.create_task(s.run(begin_at=clock.t))
    await asyncio.sleep(0.01)
    s.finish_now()
    assert await asyncio.wait_for(task, 2) == "done"
    assert d.ps[-1] == 1.0
    assert d.events[-1] == "close"
    assert "off" not in d.events


async def test_finish_now_during_early_connect_wait():
    clock, d = FakeClock(), FakeDriver()
    s = Sunrise([d], total_s=10, tick=0.001, clock=clock)
    task = asyncio.create_task(s.run(begin_at=clock.t + 120))
    await asyncio.sleep(0.02)
    assert d.ps == []
    s.finish_now()
    assert await asyncio.wait_for(task, 2) == "done"
    assert d.ps[-1] == 1.0
    assert "off" not in d.events
