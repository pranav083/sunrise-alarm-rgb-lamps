import asyncio

import pytest
from sunlight.floor import (FloorDriver, POWER_OFF, POWER_ON, brightness_packet, color_packet)


def test_packets():
    assert color_packet(255, 30, 0) == bytes.fromhex("7e070503ff1e0010ef")
    assert brightness_packet(5) == bytes.fromhex("7e040105ff000000ef")
    assert POWER_ON == bytes.fromhex("7e0404f00001ff00ef")
    assert POWER_OFF == bytes.fromhex("7e0404000000ff00ef")


class FakeClient:
    instances = []

    def __init__(self, address, disconnected_callback):
        self.cb, self.writes, self.is_connected = disconnected_callback, [], False
        FakeClient.instances.append(self)

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def write_gatt_char(self, char, data, response=False):
        if not self.is_connected:
            raise OSError("not connected")
        self.writes.append(bytes(data).hex())

    def drop(self):
        self.is_connected = False
        self.cb(self)


async def wait_ready(d):
    for _ in range(100):
        if d.ready:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("never ready")


async def test_start_connects_inits_and_powers_on():
    FakeClient.instances.clear()
    d = FloorDriver(client_factory=FakeClient)
    await d.start(); await wait_ready(d)
    w = FakeClient.instances[0].writes
    assert w[:3] == ["7e0783", "7e0404", "7e0404f00001ff00ef"]
    await d.close()


async def test_update_sends_only_changes():
    FakeClient.instances.clear()
    d = FloorDriver(client_factory=FakeClient)
    await d.start(); await wait_ready(d)
    c = FakeClient.instances[0]; c.writes.clear()
    await d.update(0.0)
    assert c.writes == ["7e07050328000010ef", "7e040101ff000000ef"]   # (40,0,0) @1%
    c.writes.clear()
    await d.update(0.0)
    assert c.writes == []
    await d.close()


async def test_reconnects_after_drop_and_resends_state():
    FakeClient.instances.clear()
    d = FloorDriver(client_factory=FakeClient, retry_delay=0)
    await d.start(); await wait_ready(d)
    await d.update(0.5)
    FakeClient.instances[0].drop()
    assert not d.ready
    await wait_ready(d)
    c2 = FakeClient.instances[-1]
    assert c2 is not FakeClient.instances[0]
    await d.update(0.5)          # same p, but new link must get the state again
    assert any(w.startswith("7e070503") for w in c2.writes)
    await d.close()


async def test_update_while_down_is_silently_skipped():
    FakeClient.instances.clear()
    d = FloorDriver(client_factory=FakeClient, retry_delay=10)
    await d.start(); await wait_ready(d)
    FakeClient.instances[0].drop()
    await d.update(0.3)          # must not raise
    await d.close()


class FakeCtrlClient(FakeClient):
    """Auto-connects like a real short-lived BLE connection for FloorController tests."""


async def test_controller_rgb_applies_calibration():
    from sunlight.floor import FloorController
    FakeClient.instances.clear()
    ctrl = FloorController(client_factory=FakeClient)
    await ctrl.rgb(255, 100, 100)
    w = FakeClient.instances[0].writes
    assert w == ["7e0783", "7e0404", "7e070503ff1e3c10ef"]
    assert FakeClient.instances[0].is_connected is False


async def test_controller_power_on_off():
    from sunlight.floor import FloorController
    FakeClient.instances.clear()
    ctrl = FloorController(client_factory=FakeClient)
    await ctrl.power(True)
    assert FakeClient.instances[0].writes == ["7e0783", "7e0404", "7e0404f00001ff00ef"]
    await ctrl.power(False)
    assert FakeClient.instances[1].writes == ["7e0783", "7e0404", "7e0404000000ff00ef"]


async def test_controller_brightness():
    from sunlight.floor import FloorController
    FakeClient.instances.clear()
    ctrl = FloorController(client_factory=FakeClient)
    await ctrl.brightness(42)
    assert FakeClient.instances[0].writes == ["7e0783", "7e0404", "7e04012aff000000ef"]


async def test_controller_serializes_concurrent_calls():
    import asyncio as _asyncio
    from sunlight.floor import FloorController
    FakeClient.instances.clear()
    ctrl = FloorController(client_factory=FakeClient)
    await _asyncio.gather(ctrl.power(True), ctrl.power(False), ctrl.brightness(10))
    assert len(FakeClient.instances) == 3
    for c in FakeClient.instances:
        assert len(c.writes) == 3


class HangingConnectClient(FakeClient):
    """connect() hangs forever (simulates a stalled BLE connect attempt)."""

    async def connect(self):
        await asyncio.Event().wait()

    async def disconnect(self):
        self.disconnect_called = True
        self.is_connected = False


async def test_controller_disconnects_after_cancelled_connect():
    import asyncio as _asyncio
    from sunlight.floor import FloorController
    FakeClient.instances.clear()
    ctrl = FloorController(client_factory=HangingConnectClient)
    with pytest.raises(_asyncio.TimeoutError):
        await _asyncio.wait_for(ctrl.power(True), timeout=0.05)
    c = FakeClient.instances[0]
    assert getattr(c, "disconnect_called", False) is True
    # lock must be released: a second call proceeds without hanging
    FakeClient.instances.clear()
    ctrl2 = FloorController(client_factory=FakeClient)
    ctrl._factory = FakeClient
    await _asyncio.wait_for(ctrl.power(True), timeout=1)
    assert FakeClient.instances[0].writes == ["7e0783", "7e0404", "7e0404f00001ff00ef"]
