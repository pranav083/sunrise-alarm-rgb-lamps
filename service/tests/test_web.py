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


async def client_for(aiohttp_client, tmp_path, sch=None):
    state = {"settings": Settings()}
    app = make_app(sch or FakeScheduler(), tmp_path / "settings.json", state)
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
