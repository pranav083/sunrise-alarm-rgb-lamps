"""Floor lamp (MELK-OA10): BLE, ELK-BLEDOM-style packets, held link with auto-reconnect."""
import asyncio
import logging
import os

from .curve import curve, floor_values

log = logging.getLogger("sunlight.floor")

# Set SUNLIGHT_FLOOR_ADDRESS to your lamp's BLE MAC address. To find it, run a BLE scan
# (e.g. `bleak-lescan` or a phone BLE scanner app) and look for a device name starting
# with "MELK" (the ELK-BLEDOM / LotusLamp X protocol family).
ADDRESS = os.environ.get("SUNLIGHT_FLOOR_ADDRESS", "AA:BB:CC:DD:EE:FF")
WRITE_CHAR = "0000fff3-0000-1000-8000-00805f9b34fb"
INIT = [bytes.fromhex("7e0783"), bytes.fromhex("7e0404")]
POWER_ON = bytes.fromhex("7e0404f00001ff00ef")
POWER_OFF = bytes.fromhex("7e0404000000ff00ef")


def color_packet(r: int, g: int, b: int) -> bytes:
    return bytes.fromhex(f"7e070503{r:02x}{g:02x}{b:02x}10ef")


def brightness_packet(pct: int) -> bytes:
    return bytes.fromhex(f"7e0401{pct:02x}ff000000ef")


def _bleak_factory(address, disconnected_callback):
    from bleak import BleakClient
    return BleakClient(address, timeout=20, disconnected_callback=disconnected_callback,
                       winrt={"use_cached_services": True})


class FloorDriver:
    name = "floor"

    def __init__(self, address: str = ADDRESS, client_factory=None, retry_delay: float = 1.0):
        self._address = address
        self._factory = client_factory or _bleak_factory
        self._retry_delay = retry_delay
        self._client = None
        self._up = asyncio.Event()
        self._lost = asyncio.Event()
        self._task = None
        self._last = (None, None)   # last colour/brightness packet sent on this link

    @property
    def ready(self) -> bool:
        return self._up.is_set()

    @property
    def recovering(self) -> bool:
        """Down now but the link loop is actively retrying."""
        return self._task is not None and not self._up.is_set()

    async def start(self) -> None:
        """Begin the connect/reconnect loop (returns immediately; watch `ready`)."""
        if self._task is None:
            self._task = asyncio.create_task(self._link_loop())

    async def _link_loop(self) -> None:
        while True:
            self._lost.clear()
            client = self._factory(self._address, lambda _c: self._on_lost())
            try:
                await client.connect()
                for pkt in INIT + [POWER_ON]:
                    await client.write_gatt_char(WRITE_CHAR, pkt, response=False)
                    await asyncio.sleep(0.1)
                self._client, self._last = client, (None, None)
                self._up.set()
                log.info("floor lamp connected")
                await self._lost.wait()
                log.warning("floor lamp link dropped")
            except asyncio.CancelledError:
                await self._safe_disconnect(client)
                raise
            except Exception as e:                      # bleak raises many types
                log.warning("floor connect failed: %s: %s", type(e).__name__, e)
            self._on_lost()
            await self._safe_disconnect(client)
            await asyncio.sleep(self._retry_delay)

    def _on_lost(self) -> None:
        self._up.clear()
        self._client = None
        self._lost.set()

    @staticmethod
    async def _safe_disconnect(client) -> None:
        try:
            await client.disconnect()
        except Exception:
            pass

    async def _write(self, pkt: bytes) -> None:
        await self._client.write_gatt_char(WRITE_CHAR, pkt, response=False)

    async def update(self, p: float) -> None:
        if not self.ready:
            return
        r, g, b, pct = floor_values(*curve(p))
        cpk, bpk = color_packet(r, g, b), brightness_packet(pct)
        try:
            if cpk != self._last[0]:
                await self._write(cpk)
            if bpk != self._last[1]:
                await self._write(bpk)
            self._last = (cpk, bpk)
        except Exception as e:
            log.warning("floor write failed: %s", e)
            self._on_lost()

    async def off(self) -> None:
        if self.ready:
            try:
                await self._write(POWER_OFF)
            except Exception as e:
                log.warning("floor off failed: %s", e)

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._up.clear()
