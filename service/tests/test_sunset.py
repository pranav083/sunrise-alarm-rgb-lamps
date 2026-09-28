from sunlight.sunset import CODES, STAGES, SunsetDriver, stage_index


class FakeIR:
    def __init__(self, ok=True):
        self.sent, self.ok = [], ok

    async def __call__(self, code):
        self.sent.append(code)
        return self.ok

    async def healthy(self):
        return self.ok


def names(sent):
    rev = {v: k for k, v in CODES.items()}
    return [rev[c] for c in sent]


def test_stage_index():
    assert stage_index(0.0) == 0
    assert stage_index(0.17) == 0
    assert stage_index(0.18) == 1
    assert stage_index(1.0) == len(STAGES) - 1


async def test_start_sets_red_at_lowest_level():
    ir = FakeIR(); d = SunsetDriver(ir, ir.healthy)
    await d.start()
    assert names(ir.sent) == ["on", "on", "R", "R"] + ["down"] * 7
    assert d.ready


async def test_update_sends_each_stage_once_colour_twice_brightness_once():
    ir = FakeIR(); d = SunsetDriver(ir, ir.healthy)
    await d.start(); ir.sent.clear()
    await d.update(0.0)                      # stage 0 = R level 0 -> nothing new
    assert ir.sent == []
    await d.update(0.20)                     # stage 1 = R level 1
    assert names(ir.sent) == ["R", "R", "up"]
    ir.sent.clear()
    await d.update(0.20)                     # same stage again -> nothing
    assert ir.sent == []


async def test_update_jumping_ahead_applies_final_stage_level():
    ir = FakeIR(); d = SunsetDriver(ir, ir.healthy)
    await d.start(); ir.sent.clear()
    await d.update(1.0)
    assert names(ir.sent) == ["W", "W"] + ["up"] * 5


async def test_unhealthy_board_not_ready_and_sends_nothing():
    ir = FakeIR(ok=False); d = SunsetDriver(ir, ir.healthy)
    await d.start()
    assert not d.ready and ir.sent == []
    await d.update(0.5)
    assert ir.sent == []


def test_sunset_driver_never_recovers_once_skipped():
    ir = FakeIR(ok=False); d = SunsetDriver(ir, ir.healthy)
    assert d.recovering is False


class FlakyHealthy:
    """Fails a fixed number of times, then succeeds."""
    def __init__(self, fail_times):
        self.fail_times, self.calls = fail_times, 0

    async def __call__(self):
        self.calls += 1
        return self.calls > self.fail_times


async def test_start_retries_health_check_and_succeeds():
    ir = FakeIR()
    healthy = FlakyHealthy(fail_times=2)
    d = SunsetDriver(ir, healthy)
    await d.start()
    assert d.ready
    assert healthy.calls == 3
    assert names(ir.sent)[:2] == ["on", "on"]        # IR was actually sent once healthy


async def test_start_retries_health_check_then_gives_up():
    ir = FakeIR()
    healthy = FlakyHealthy(fail_times=3)
    d = SunsetDriver(ir, healthy)
    await d.start()
    assert not d.ready
    assert healthy.calls == 3
    assert ir.sent == []                              # no IR commands sent when skipped


async def test_off_sends_off_twice():
    ir = FakeIR(); d = SunsetDriver(ir, ir.healthy)
    await d.start(); ir.sent.clear()
    await d.off()
    assert names(ir.sent) == ["off", "off"]
