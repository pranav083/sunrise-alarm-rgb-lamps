"""HTTP API + phone UI."""
from pathlib import Path

from aiohttp import web

from .settings import from_dict, save

STATIC = Path(__file__).parent / "static"


def make_app(scheduler, settings_path: Path, state: dict) -> web.Application:
    routes = web.RouteTableDef()

    @routes.get("/")
    async def index(_):
        return web.FileResponse(STATIC / "index.html")

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
