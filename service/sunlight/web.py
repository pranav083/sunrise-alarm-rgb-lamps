"""HTTP API + phone UI."""
import asyncio
import re
from pathlib import Path

from aiohttp import web

from .floor import FloorController
from .settings import from_dict, save
from .sunset import ALL_CODES, HttpIrSender

STATIC = Path(__file__).parent / "static"
IR_CODE_RE = re.compile(r"^[0-9a-fA-F]{6}$")
FLOOR_TIMEOUT_S = 25


def make_app(scheduler, settings_path: Path, state: dict, ir_sender=None, floor_ctrl=None) -> web.Application:
    ir_sender = ir_sender if ir_sender is not None else HttpIrSender()
    floor_ctrl = floor_ctrl if floor_ctrl is not None else FloorController()
    routes = web.RouteTableDef()

    @routes.get("/")
    async def index(_):
        return web.FileResponse(STATIC / "index.html")

    @routes.get("/remote")
    async def remote(_):
        return web.FileResponse(STATIC / "remote.html")

    @routes.post("/api/ir")
    async def api_ir(request):
        if scheduler.running:
            return web.json_response({"error": "busy: a sunrise is running"}, status=409)
        try:
            body = await request.json()
        except (ValueError, TypeError) as e:
            return web.json_response({"error": f"invalid JSON body: {e}"}, status=400)
        code = body.get("code") if isinstance(body, dict) else None
        if not isinstance(code, str) or not IR_CODE_RE.match(code) or code.upper() not in ALL_CODES:
            return web.json_response({"error": "unknown or malformed IR code"}, status=400)
        try:
            ok = await ir_sender(code.upper())
        except Exception as e:
            return web.json_response({"error": f"IR board unreachable: {e}"}, status=502)
        if not ok:
            return web.json_response({"error": "IR board request failed"}, status=502)
        return web.json_response({"sent": code.upper()})

    @routes.post("/api/floor")
    async def api_floor(request):
        if scheduler.running:
            return web.json_response({"error": "busy: a sunrise is running"}, status=409)
        try:
            body = await request.json()
        except (ValueError, TypeError) as e:
            return web.json_response({"error": f"invalid JSON body: {e}"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "invalid body"}, status=400)

        def is_int(v):
            return isinstance(v, int) and not isinstance(v, bool)

        try:
            if "power" in body:
                if body["power"] not in ("on", "off"):
                    raise ValueError("power must be 'on' or 'off'")
                coro = floor_ctrl.power(body["power"] == "on")
            elif "rgb" in body:
                rgb = body["rgb"]
                if not (isinstance(rgb, list) and len(rgb) == 3
                        and all(is_int(v) and 0 <= v <= 255 for v in rgb)):
                    raise ValueError("rgb must be [r, g, b] with ints 0-255")
                coro = floor_ctrl.rgb(*rgb)
            elif "brightness" in body:
                b = body["brightness"]
                if not (is_int(b) and 1 <= b <= 100):
                    raise ValueError("brightness must be an int 1-100")
                coro = floor_ctrl.brightness(b)
            else:
                raise ValueError("body must contain 'power', 'rgb', or 'brightness'")
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        try:
            await asyncio.wait_for(coro, FLOOR_TIMEOUT_S)
        except Exception as e:
            return web.json_response({"error": f"floor lamp unreachable: {e}"}, status=502)
        return web.json_response({"ok": True})

    @routes.get("/api/settings")
    async def get_settings(_):
        return web.json_response(state["settings"].to_dict())

    @routes.put("/api/settings")
    async def put_settings(request):
        try:
            body = await request.json()
        except (ValueError, TypeError) as e:
            return web.json_response({"error": f"invalid JSON body: {e}"}, status=400)
        try:
            s = from_dict({**state["settings"].to_dict(), **body})
        except (ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        save(s, settings_path)
        state["settings"] = s
        return web.json_response(s.to_dict())

    @routes.get("/api/status")
    async def status(_):
        return web.json_response(scheduler.status())

    @routes.post("/api/demo")
    async def demo(request):
        if scheduler.running:
            return web.json_response({"error": "a run is already active"}, status=409)
        try:
            body = await request.json() if request.can_read_body else {}
        except (ValueError, TypeError) as e:
            return web.json_response({"error": f"invalid JSON body: {e}"}, status=400)
        try:
            seconds = max(10, min(600, float(body.get("seconds", 30))))
        except (ValueError, TypeError) as e:
            return web.json_response({"error": f"invalid seconds: {e}"}, status=400)
        scheduler.start_demo(seconds)
        return web.json_response({"started": seconds}, status=202)

    @routes.post("/api/sunrise-now")
    async def sunrise_now(request):
        if scheduler.running:
            return web.json_response({"error": "a run is already active"}, status=409)
        try:
            body = await request.json() if request.can_read_body else {}
        except (ValueError, TypeError) as e:
            return web.json_response({"error": f"invalid JSON body: {e}"}, status=400)
        if "minutes" in body:
            minutes = body["minutes"]
            if not isinstance(minutes, int) or isinstance(minutes, bool) or not (1 <= minutes <= 60):
                return web.json_response({"error": "minutes must be an int 1-60"}, status=400)
        else:
            minutes = state["settings"].length_min
        scheduler.start_sunrise_now(minutes)
        return web.json_response({"started_minutes": minutes}, status=202)

    @routes.post("/api/stop")
    async def stop(_):
        scheduler.stop()
        return web.json_response({"stopped": True})

    @routes.post("/api/wake")
    async def wake(_):
        woke = scheduler.wake_up()
        return web.json_response({"woke": woke})

    app = web.Application()
    app.add_routes(routes)
    return app
