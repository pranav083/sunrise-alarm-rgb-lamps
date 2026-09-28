"""Entry point: web server + scheduler loop."""
import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiohttp import web

from .floor import FloorDriver
from .power import Power
from .scheduler import Scheduler
from .settings import load
from .sunset import HttpIrSender, SunsetDriver
from .web import make_app


def make_drivers(settings):
    drivers = []
    if settings.floor:
        drivers.append(FloorDriver())
    if settings.sunset:
        ir = HttpIrSender()
        drivers.append(SunsetDriver(ir, ir.healthy))
    return drivers


async def amain(port: int, data: Path) -> None:
    state = {"settings": load(data / "settings.json")}
    scheduler = Scheduler(lambda: state["settings"], make_drivers, power=Power())
    runner = web.AppRunner(make_app(scheduler, data / "settings.json", state))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logging.getLogger("sunlight").info("listening on :%d", port)
    await scheduler.loop()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(),
                                  RotatingFileHandler(args.data / "sunlight.log", maxBytes=1_000_000, backupCount=3)])
    asyncio.run(amain(args.port, args.data))


if __name__ == "__main__":
    main()
