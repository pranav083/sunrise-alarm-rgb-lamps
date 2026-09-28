"""Sunset projection lamp: IR via the ESP8266 board (6 brightness levels, fixed colours)."""
import asyncio
import logging
import os
import urllib.request

log = logging.getLogger("sunlight.sunset")

CODES = {
    "on": "F7C03F", "off": "F740BF", "up": "F700FF", "down": "F7807F",
    "R": "F720DF", "OR": "F710EF", "O": "F730CF", "LO": "F708F7", "Y": "F728D7", "W": "F7E01F",
}

# All 24 NEC codes shared by both remotes (address 0xEF00), in physical button order
# (cmd 0x00-0x17), from firmware/ir_codes.md. Single source of truth for IR validation.
ALL_CODES = [
    "F700FF", "F7807F", "F740BF", "F7C03F", "F720DF", "F7A05F", "F7609F", "F7E01F",
    "F710EF", "F7906F", "F750AF", "F7D02F", "F730CF", "F7B04F", "F7708F", "F7F00F",
    "F708F7", "F78877", "F748B7", "F7C837", "F728D7", "F7A857", "F76897", "F7E817",
]
# (p threshold, colour, brightness level 0-5) — verified in the IR preview 2026-09-28
STAGES = [
    (0.00, "R", 0), (0.18, "R", 1), (0.32, "OR", 1), (0.44, "OR", 2), (0.54, "O", 2), (0.63, "O", 3),
    (0.71, "LO", 3), (0.79, "LO", 4), (0.86, "Y", 4), (0.93, "Y", 5), (1.00, "W", 5),
]
GAP = 0.3  # seconds between IR commands so the lamp registers each one
HEALTH_CHECK_RETRIES = 3
HEALTH_RETRY_DELAY = 1.0  # seconds between /version retries; patched to 0 in tests


def stage_index(p: float) -> int:
    return max(i for i, (th, _, _) in enumerate(STAGES) if p >= th) if p >= 0 else 0


class HttpIrSender:
    # Set SUNLIGHT_IR_HOST to your IR board's LAN IP or hostname. "192.168.1.50" below is
    # just a placeholder default -- set it to your IR board's IP.
    def __init__(self, host: str = None):
        self.host = host or os.environ.get("SUNLIGHT_IR_HOST", "192.168.1.50")

    def _get(self, path: str) -> bool:
        try:
            with urllib.request.urlopen(f"http://{self.host}{path}", timeout=3) as r:
                return r.status == 200
        except OSError as e:
            log.warning("IR board request %s failed: %s", path, e)
            return False

    async def __call__(self, code_hex: str) -> bool:
        path = f"/send?proto=NEC&value=0x{code_hex}&bits=32"
        for _ in range(2):  # one retry on network failure
            if await asyncio.to_thread(self._get, path):
                return True
        return False

    async def healthy(self) -> bool:
        return await asyncio.to_thread(self._get, "/version")


class SunsetDriver:
    name = "sunset"

    def __init__(self, send, healthy):
        self._send, self._healthy = send, healthy
        self._ok = False
        self._stage = -1
        self._level = 0

    @property
    def ready(self) -> bool:
        return self._ok

    @property
    def recovering(self) -> bool:
        # Never retries once skipped for a run; nothing to wait for.
        return False

    async def _cmd(self, key: str, times: int = 1) -> None:
        for _ in range(times):
            await self._send(CODES[key])
            await asyncio.sleep(GAP)

    async def start(self) -> None:
        for attempt in range(HEALTH_CHECK_RETRIES):
            self._ok = await self._healthy()
            if self._ok:
                break
            if attempt < HEALTH_CHECK_RETRIES - 1:
                await asyncio.sleep(HEALTH_RETRY_DELAY)
        if not self._ok:
            log.warning("IR board unhealthy; sunset lamp skipped")
            return
        await self._cmd("on", 2)
        await self._cmd("R", 2)
        await self._cmd("down", 7)   # floor it: level 0 regardless of previous state
        self._stage, self._level = 0, 0

    async def update(self, p: float) -> None:
        if not self._ok:
            return
        i = stage_index(p)
        if i == self._stage:
            return
        _, colour, level = STAGES[i]
        await self._cmd(colour, 2)                 # idempotent -> twice survives a drop
        while self._level < level:                 # not idempotent -> once per step
            await self._cmd("up")
            self._level += 1
        self._stage = i

    async def off(self) -> None:
        if self._ok:
            await self._cmd("off", 2)

    async def close(self) -> None:
        pass
