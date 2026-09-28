from sunlight.settings import Settings
from sunlight.web import make_app


class FakeScheduler:
    def __init__(self): self.demos, self.stopped, self.busy, self.woken = [], 0, False, 0
    def status(self): return {"state": "idle", "progress": None, "next_start": None, "last_result": None, "lamps": {}}
    async def demo(self, seconds): self.demos.append(seconds); return "done"
    def start_demo(self, seconds): self.demos.append(seconds)
    def stop(self): self.stopped += 1
    def wake_up(self): self.woken += 1; return True
    @property
    def running(self): return self.busy


class FakeIrSender:
    def __init__(self, ok=True, raise_error=False):
        self.sent, self.ok, self.raise_error = [], ok, raise_error

    async def __call__(self, code):
        if self.raise_error:
            raise OSError("board unreachable")
        self.sent.append(code)
        return self.ok


class FakeFloorCtrl:
    def __init__(self, raise_error=False):
        self.calls, self.raise_error = [], raise_error

    async def power(self, on):
        if self.raise_error:
            raise OSError("lamp unreachable")
        self.calls.append(("power", on))

    async def rgb(self, r, g, b):
        if self.raise_error:
            raise OSError("lamp unreachable")
        self.calls.append(("rgb", r, g, b))

    async def brightness(self, pct):
        if self.raise_error:
            raise OSError("lamp unreachable")
        self.calls.append(("brightness", pct))


async def client_for(aiohttp_client, tmp_path, sch=None, ir_sender=None, floor_ctrl=None):
    state = {"settings": Settings()}
    app = make_app(sch or FakeScheduler(), tmp_path / "settings.json", state,
                    ir_sender=ir_sender or FakeIrSender(), floor_ctrl=floor_ctrl or FakeFloorCtrl())
    return await aiohttp_client(app), state


async def test_get_and_put_settings(aiohttp_client, tmp_path):
    c, state = await client_for(aiohttp_client, tmp_path)
    assert (await (await c.get("/api/settings")).json())["wake"] == "06:30"
    r = await c.put("/api/settings", json={**Settings().to_dict(), "wake": "07:15"})
    assert r.status == 200 and state["settings"].wake == "07:15"
    assert (tmp_path / "settings.json").exists()


async def test_put_invalid_is_400_and_unchanged(aiohttp_client, tmp_path):
    c, state = await client_for(aiohttp_client, tmp_path)
    r = await c.put("/api/settings", json={"wake": "99:99"})
    assert r.status == 400 and state["settings"].wake == "06:30"


async def test_demo_and_stop(aiohttp_client, tmp_path):
    sch = FakeScheduler()
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    assert (await c.post("/api/demo", json={"seconds": 20})).status == 202
    assert (await c.post("/api/stop")).status == 200 and sch.stopped == 1


async def test_wake_calls_scheduler_wake_up(aiohttp_client, tmp_path):
    sch = FakeScheduler()
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/wake")
    assert r.status == 200
    assert (await r.json()) == {"woke": True}
    assert sch.woken == 1


async def test_demo_conflict_when_busy(aiohttp_client, tmp_path):
    sch = FakeScheduler(); sch.busy = True
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    assert (await c.post("/api/demo", json={"seconds": 20})).status == 409


async def test_put_settings_malformed_json_is_400(aiohttp_client, tmp_path):
    c, state = await client_for(aiohttp_client, tmp_path)
    r = await c.put("/api/settings", data="not json", headers={"Content-Type": "application/json"})
    assert r.status == 400
    assert "error" in await r.json()
    assert state["settings"].wake == "06:30"


async def test_demo_malformed_json_is_400(aiohttp_client, tmp_path):
    sch = FakeScheduler()
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/demo", data="not json", headers={"Content-Type": "application/json"})
    assert r.status == 400
    assert "error" in await r.json()
    assert sch.demos == []


async def test_demo_non_numeric_seconds_is_400(aiohttp_client, tmp_path):
    sch = FakeScheduler()
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/demo", json={"seconds": "banana"})
    assert r.status == 400
    assert "error" in await r.json()
    assert sch.demos == []


async def test_index_served(aiohttp_client, tmp_path):
    c, _ = await client_for(aiohttp_client, tmp_path)
    r = await c.get("/")
    assert r.status == 200 and "Sunrise" in await r.text()


class FakeSchedulerSunriseNow(FakeScheduler):
    def __init__(self):
        super().__init__()
        self.sunrise_now_calls = []
    def start_sunrise_now(self, minutes): self.sunrise_now_calls.append(minutes)


async def test_sunrise_now_happy_path_default_minutes(aiohttp_client, tmp_path):
    sch = FakeSchedulerSunriseNow()
    c, state = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/sunrise-now")
    assert r.status == 202
    assert (await r.json()) == {"started_minutes": state["settings"].length_min}
    assert sch.sunrise_now_calls == [state["settings"].length_min]


async def test_sunrise_now_explicit_minutes(aiohttp_client, tmp_path):
    sch = FakeSchedulerSunriseNow()
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/sunrise-now", json={"minutes": 5})
    assert r.status == 202
    assert (await r.json()) == {"started_minutes": 5}
    assert sch.sunrise_now_calls == [5]


async def test_sunrise_now_conflict_when_busy(aiohttp_client, tmp_path):
    sch = FakeSchedulerSunriseNow(); sch.busy = True
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/sunrise-now")
    assert r.status == 409
    assert sch.sunrise_now_calls == []


async def test_sunrise_now_malformed_json_is_400(aiohttp_client, tmp_path):
    sch = FakeSchedulerSunriseNow()
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/sunrise-now", data="not json", headers={"Content-Type": "application/json"})
    assert r.status == 400
    assert sch.sunrise_now_calls == []


async def test_sunrise_now_zero_minutes_is_400(aiohttp_client, tmp_path):
    sch = FakeSchedulerSunriseNow()
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/sunrise-now", json={"minutes": 0})
    assert r.status == 400
    assert sch.sunrise_now_calls == []


async def test_sunrise_now_too_large_minutes_is_400(aiohttp_client, tmp_path):
    sch = FakeSchedulerSunriseNow()
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/sunrise-now", json={"minutes": 61})
    assert r.status == 400
    assert sch.sunrise_now_calls == []


async def test_sunrise_now_non_int_minutes_is_400(aiohttp_client, tmp_path):
    sch = FakeSchedulerSunriseNow()
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/sunrise-now", json={"minutes": "x"})
    assert r.status == 400
    assert sch.sunrise_now_calls == []


async def test_remote_page_serves_both_remotes(aiohttp_client, tmp_path):
    c, _ = await client_for(aiohttp_client, tmp_path)
    r = await c.get("/remote")
    assert r.status == 200
    html = await r.text()
    assert "Sunset lamp" in html and "Floor lamp" in html


async def test_index_links_to_remote(aiohttp_client, tmp_path):
    c, _ = await client_for(aiohttp_client, tmp_path)
    html = await (await c.get("/")).text()
    assert "/remote" in html


async def test_api_ir_sends_known_code(aiohttp_client, tmp_path):
    ir = FakeIrSender()
    c, _ = await client_for(aiohttp_client, tmp_path, ir_sender=ir)
    r = await c.post("/api/ir", json={"code": "f720df"})
    assert r.status == 200
    assert ir.sent == ["F720DF"]


async def test_api_ir_unknown_code_400(aiohttp_client, tmp_path):
    c, _ = await client_for(aiohttp_client, tmp_path)
    r = await c.post("/api/ir", json={"code": "abcdef"})
    assert r.status == 400


async def test_api_ir_malformed_400(aiohttp_client, tmp_path):
    c, _ = await client_for(aiohttp_client, tmp_path)
    assert (await c.post("/api/ir", json={"code": "xyz"})).status == 400
    assert (await c.post("/api/ir", json={})).status == 400
    assert (await c.post("/api/ir", data="not json")).status == 400


async def test_api_ir_409_while_running(aiohttp_client, tmp_path):
    sch = FakeScheduler(); sch.busy = True
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/ir", json={"code": "F720DF"})
    assert r.status == 409


async def test_api_ir_502_on_sender_failure(aiohttp_client, tmp_path):
    ir = FakeIrSender(ok=False)
    c, _ = await client_for(aiohttp_client, tmp_path, ir_sender=ir)
    r = await c.post("/api/ir", json={"code": "F720DF"})
    assert r.status == 502


async def test_api_ir_502_on_sender_raise(aiohttp_client, tmp_path):
    ir = FakeIrSender(raise_error=True)
    c, _ = await client_for(aiohttp_client, tmp_path, ir_sender=ir)
    r = await c.post("/api/ir", json={"code": "F720DF"})
    assert r.status == 502


async def test_api_floor_power(aiohttp_client, tmp_path):
    fc = FakeFloorCtrl()
    c, _ = await client_for(aiohttp_client, tmp_path, floor_ctrl=fc)
    r = await c.post("/api/floor", json={"power": "on"})
    assert r.status == 200
    assert fc.calls == [("power", True)]


async def test_api_floor_rgb(aiohttp_client, tmp_path):
    fc = FakeFloorCtrl()
    c, _ = await client_for(aiohttp_client, tmp_path, floor_ctrl=fc)
    r = await c.post("/api/floor", json={"rgb": [255, 100, 0]})
    assert r.status == 200
    assert fc.calls == [("rgb", 255, 100, 0)]


async def test_api_floor_brightness(aiohttp_client, tmp_path):
    fc = FakeFloorCtrl()
    c, _ = await client_for(aiohttp_client, tmp_path, floor_ctrl=fc)
    r = await c.post("/api/floor", json={"brightness": 50})
    assert r.status == 200
    assert fc.calls == [("brightness", 50)]


async def test_api_floor_invalid_rgb_400(aiohttp_client, tmp_path):
    c, _ = await client_for(aiohttp_client, tmp_path)
    assert (await c.post("/api/floor", json={"rgb": [256, 0, 0]})).status == 400
    assert (await c.post("/api/floor", json={"rgb": [-1, 0, 0]})).status == 400
    assert (await c.post("/api/floor", json={"rgb": [1, 2]})).status == 400


async def test_api_floor_invalid_brightness_400(aiohttp_client, tmp_path):
    c, _ = await client_for(aiohttp_client, tmp_path)
    assert (await c.post("/api/floor", json={"brightness": 0})).status == 400
    assert (await c.post("/api/floor", json={"brightness": 101})).status == 400


async def test_api_floor_unknown_key_400(aiohttp_client, tmp_path):
    c, _ = await client_for(aiohttp_client, tmp_path)
    assert (await c.post("/api/floor", json={"foo": 1})).status == 400


async def test_api_floor_non_json_400(aiohttp_client, tmp_path):
    c, _ = await client_for(aiohttp_client, tmp_path)
    assert (await c.post("/api/floor", data="not json")).status == 400


async def test_api_floor_409_while_running(aiohttp_client, tmp_path):
    sch = FakeScheduler(); sch.busy = True
    c, _ = await client_for(aiohttp_client, tmp_path, sch)
    r = await c.post("/api/floor", json={"power": "on"})
    assert r.status == 409


async def test_api_floor_502_on_failure(aiohttp_client, tmp_path):
    fc = FakeFloorCtrl(raise_error=True)
    c, _ = await client_for(aiohttp_client, tmp_path, floor_ctrl=fc)
    r = await c.post("/api/floor", json={"power": "on"})
    assert r.status == 502
