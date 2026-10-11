"""Local home panel for one official Project Zomboid dedicated server."""

import json
import math
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import commands
import host
import sandbox
from parse import format_uptime, mark_online, quiet_lines, quote_arg

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SESSIONS = {}
SESSION_TTL = 12 * 60 * 60
LOGIN_ATTEMPTS = {}

TILE_ROOT = "https://tiles.pzmap.org/42.20.0/base/layer0_files/"
TILE_PATH = re.compile(r"^/tiles/(\d+)/(\d+)_(\d+)\.jpg$")
TILE_CACHE = {}
TILE_LOCK = threading.Lock()
TILE_LIMIT = 48

DEMO_SANDBOX = """SandboxVars = {
    VERSION = 6,
    -- 1 = Insane
    -- 4 = Normal
    Zombies = 4,
    -- 4 = 1 Hour, 30 Minutes
    DayLength = 4,
}
"""
DEMO = {
    "running": True,
    "started": time.time() - (1 * 86400 + 10 * 3600 + 16 * 60),
    "rcon": True,
    "players": ["阿宁", "林夏"],
    "saved": False,
}


def fetch_tile(level, col, row):
    key = (level, col, row)
    with TILE_LOCK:
        cached = TILE_CACHE.get(key)
        if cached is not None:
            TILE_CACHE[key] = TILE_CACHE.pop(key)
            return cached
    url = f"{TILE_ROOT}{level}/{col}_{row}.jpg"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=12) as response:
            data = response.read(2_000_000)
    except HTTPError as exc:
        if exc.code == 404:
            return b""
        raise
    if not data.startswith(b"\xff\xd8"):
        return b""
    with TILE_LOCK:
        TILE_CACHE[key] = data
        while len(TILE_CACHE) > TILE_LIMIT:
            TILE_CACHE.pop(next(iter(TILE_CACHE)))
    return data


def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    password = data.get("password") or ""
    if len(password) < 8:
        raise SystemExit("config.json 里的面板密码至少 8 位")
    if not data.get("iniPath") or not data.get("rconPassword"):
        raise SystemExit("config.json 还缺 iniPath 或 rconPassword")
    data.setdefault("listen", "0.0.0.0")
    data.setdefault("port", 3010)
    return data


def demo_overview():
    running = DEMO["running"]
    payload = {
        "running": running,
        "failed": False,
        "uptimeSec": int(time.time() - DEMO["started"]) if running else 0,
        "rconOk": DEMO["rcon"] and running,
        "rconError": "" if running else "服务器关着，管理口没有开",
        "publicName": "萌新生存服",
        "map": "Muldraugh, KY",
        "port": "16261",
        "udpPort": "16262",
        "maxPlayers": "16",
        "open": True,
        "public": True,
            "hasPassword": False,
            "mods": [
                {"id": "B42Trans_CN", "workshop": "3556544454"},
                {"id": "B42ModTrans_CN", "workshop": "3556540080"},
            ],
            "rules": [
                {"label": "玩家对战", "value": "关着"},
                {"label": "没人时", "value": "继续跑"},
                {"label": "进服密码", "value": "没有"},
            ],
        "players": list(DEMO["players"]) if running and DEMO["rcon"] else [],
        "playerError": "" if running else "服务器关着",
        "sample": True,
        "usage": {
            "cpu": 18.0,
            "memUsed": 3400000000,
            "memTotal": 8000000000,
            "diskUsed": 48000000000,
            "diskTotal": 120000000000,
            "gameMem": 2100000000,
        },
    }
    return _decorate(payload)


def live_overview(config):
    view = {
        "running": False,
        "failed": False,
        "uptimeSec": 0,
        "rconOk": False,
        "rconError": "",
        "publicName": "家用服务器",
        "map": "",
        "port": "",
        "udpPort": "",
        "maxPlayers": "",
        "open": False,
        "public": False,
        "hasPassword": False,
        "mods": [],
        "rules": [],
        "players": [],
        "playerError": "",
        "configError": "",
        "usage": {},
    }
    try:
        status = host.read_status(config)
        view["running"] = status["running"]
        view["failed"] = status["failed"]
        view["uptimeSec"] = status["uptimeSec"]
    except host.PanelError as exc:
        view["configError"] = str(exc)
    try:
        view["usage"] = host.read_usage(config)
    except Exception:
        view["usage"] = {}
    try:
        shown = host.read_config_view(config)
        view.update(shown)
    except host.PanelError as exc:
        view["configError"] = str(exc)
    if view["running"]:
        try:
            players, _raw = host.list_players(config)
            view["players"] = players
            view["rconOk"] = True
        except host.PanelError as exc:
            view["rconOk"] = False
            view["rconError"] = str(exc)
            view["playerError"] = str(exc)
    else:
        view["playerError"] = "服务器关着"
    return _decorate(view)


TOWNS = (
    {"name": "Muldraugh", "x": 11181, "y": 9725},
    {"name": "West Point", "x": 11581, "y": 6916},
)
FULL_MAP = "https://pzfans.com/en/B42/"


DEMO_VEHICLES = (
    {"id": 18, "x": 10622, "y": 9728},
    {"id": 19, "x": 10658, "y": 9752},
)


def map_bounds(query):
    try:
        minx = float(query.get("minx", ["0"])[0])
        maxx = float(query.get("maxx", ["0"])[0])
        miny = float(query.get("miny", ["0"])[0])
        maxy = float(query.get("maxy", ["0"])[0])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(number) for number in (minx, maxx, miny, maxy)):
        return None
    if maxx < minx:
        minx, maxx = maxx, minx
    if maxy < miny:
        miny, maxy = maxy, miny
    if maxx - minx > 2500:
        middle = (minx + maxx) / 2
        minx, maxx = middle - 1250, middle + 1250
    if maxy - miny > 2500:
        middle = (miny + maxy) / 2
        miny, maxy = middle - 1250, middle + 1250
    return minx, maxx, miny, maxy


def map_payload(players, vehicles=None, capped=False, error=""):
    vehicles = list(vehicles or [])
    return {
        "note": "点右侧一名玩家，地图跳到他上次存档的位置。蓝色方块是这一带的车。这台服务器不能把指定玩家传到点中的格子，只能把一名在线玩家传到另一名在线玩家身边。",
        "towns": list(TOWNS),
        "players": players,
        "vehicles": vehicles,
        "vehicleCapped": capped,
        "fullMap": FULL_MAP,
        "error": error,
    }


def _decorate(view):
    if view.get("failed"):
        view["stateLabel"] = "服务器启动失败"
    elif view.get("running"):
        view["stateLabel"] = "服务器开着"
    else:
        view["stateLabel"] = "服务器关着"
    view["uptimeText"] = format_uptime(view.get("uptimeSec") or 0) if view.get("running") else "没有在运行"
    if view.get("rconOk"):
        view["rconLabel"] = "管理口通着"
    elif view.get("running"):
        view["rconLabel"] = "进程在，管理口没通"
    else:
        view["rconLabel"] = "管理口没开"
    return view


class Handler(BaseHTTPRequestHandler):
    config = None
    demo = False

    def log_message(self, fmt, *args):
        return

    def _send(self, code, payload, content_type="application/json; charset=utf-8", extra_headers=None):
        if isinstance(payload, str):
            body = payload.encode("utf-8")
        elif isinstance(payload, bytes):
            body = payload
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        }
        headers.update(extra_headers or {})
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self, limit=16000):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise host.PanelError("请求太大")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise host.PanelError("请求不是有效的数据") from exc
        if not isinstance(data, dict):
            raise host.PanelError("请求不是有效的数据")
        return data

    def _session_token(self):
        cookie = self.headers.get("Cookie") or ""
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "home_panel":
                return value
        return ""

    def _authorized(self):
        token = self._session_token()
        session = SESSIONS.get(token)
        if not session:
            return False
        if session["expires"] < time.time():
            SESSIONS.pop(token, None)
            return False
        return True

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host_header = self.headers.get("Host") or ""
        return origin in (f"http://{host_header}", f"https://{host_header}")

    def _client_ip(self):
        return self.client_address[0]

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            self._file(STATIC / "index.html", "text/html; charset=utf-8")
            return
        if path == "/app.css":
            self._file(STATIC / "app.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._file(STATIC / "app.js", "text/javascript; charset=utf-8")
            return
        if path == "/sandbox-zh.js":
            self._file(STATIC / "sandbox-zh.js", "text/javascript; charset=utf-8")
            return
        if path == "/api/session":
            self._send(200, {"ok": self._authorized()})
            return
        if path == "/api/overview":
            if not self._authorized():
                self._send(401, {"error": "先登录"})
                return
            payload = demo_overview() if self.demo else live_overview(self.config)
            self._send(200, payload)
            return
        tile = TILE_PATH.match(path)
        if tile:
            self._tile(tile)
            return
        if path == "/api/map":
            if not self._authorized():
                self._send(401, {"error": "先登录"})
                return
            self._map(query)
            return
        if path == "/api/commands":
            if not self._authorized():
                self._send(401, {"error": "先登录"})
                return
            self._send(200, {"commands": commands.catalog()})
            return
        if path == "/api/logs":
            if not self._authorized():
                self._send(401, {"error": "先登录"})
                return
            self._logs()
            return
        if path == "/api/sandbox":
            if not self._authorized():
                self._send(401, {"error": "先登录"})
                return
            self._sandbox_read()
            return
        if path == "/api/files":
            if not self._authorized():
                self._send(401, {"error": "先登录"})
                return
            self._files()
            return
        self._send(404, {"error": "没有这个页面"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._origin_ok():
            self._send(403, {"error": "请求来源不对"})
            return
        try:
            if path == "/api/login":
                self._login()
                return
            if path == "/api/logout":
                SESSIONS.pop(self._session_token(), None)
                self._send(200, {"ok": True}, extra_headers={"Set-Cookie": "home_panel=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"})
                return
            if not self._authorized():
                self._send(401, {"error": "先登录"})
                return
            body = self._json_body(200000 if path == "/api/sandbox" else 16000)
            if path == "/api/power":
                self._power(body)
                return
            if path == "/api/message":
                self._message(body)
                return
            if path == "/api/kick":
                self._kick(body)
                return
            if path == "/api/save":
                self._save()
                return
            if path == "/api/command":
                self._command(body)
                return
            if path == "/api/sandbox":
                self._sandbox_write(body)
                return
            if path == "/api/backup":
                self._backup()
                return
        except host.PanelError as exc:
            self._send(400, {"error": str(exc)})
            return
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return
        self._send(404, {"error": "没有这个操作"})

    def _file(self, path, content_type):
        try:
            data = path.read_bytes()
        except OSError:
            self._send(404, {"error": "页面文件缺失"})
            return
        self._send(200, data, content_type)

    def _login(self):
        ip = self._client_ip()
        locked_until = LOGIN_ATTEMPTS.get(ip, {}).get("until", 0)
        if locked_until > time.time():
            self._send(429, {"error": "试得太勤了，等一分钟"})
            return
        body = self._json_body()
        expected = "demo-home" if self.demo else self.config["password"]
        given = str(body.get("password") or "").encode("utf-8")
        wanted = expected.encode("utf-8")
        if len(given) != len(wanted) or not secrets.compare_digest(given, wanted):
            record = LOGIN_ATTEMPTS.setdefault(ip, {"count": 0, "until": 0})
            record["count"] += 1
            if record["count"] >= 8:
                record["until"] = time.time() + 60
                record["count"] = 0
            self._send(401, {"error": "密码不对"})
            return
        LOGIN_ATTEMPTS.pop(ip, None)
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = {"expires": time.time() + SESSION_TTL}
        self._send(200, {"ok": True}, extra_headers={
            "Set-Cookie": f"home_panel={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL}",
        })

    def _logs(self):
        if self.demo:
            self._send(200, {
                "lines": [
                    "SERVER STARTED",
                    "Workshop: numResult=2",
                    "loading B42Trans_CN",
                    "loading B42ModTrans_CN",
                    "RCON listening on port 27015",
                ],
                "visits": [
                    {"time": "15:20:04", "name": "阿宁", "action": "进来了"},
                    {"time": "18:02:11", "name": "阿宁", "action": "离开了"},
                    {"time": "21:14:40", "name": "林夏", "action": "进来了"},
                ],
                "chat": [
                    {"time": "21:16:02", "text": "林夏: 我到镇口了"},
                ],
            })
            return
        try:
            lines = quiet_lines(host.read_logs(self.config))
        except host.PanelError as exc:
            self._send(200, {"lines": [], "visits": [], "chat": [], "error": str(exc)})
            return
        try:
            visits, chat = host.read_activity(self.config)
        except host.PanelError as exc:
            visits, chat = [], []
            self._send(200, {"lines": lines, "visits": visits, "chat": chat, "error": str(exc)})
            return
        self._send(200, {"lines": lines, "visits": visits, "chat": chat})

    def _tile(self, match):
        if not self._authorized():
            self._send(401, {"error": "先登录"})
            return
        level, col, row = (int(part) for part in match.groups())
        if level > 22 or col > 4096 or row > 4096:
            self._send(404, {"error": "没有这块地图"})
            return
        try:
            data = fetch_tile(level, col, row)
        except (HTTPError, URLError, TimeoutError, OSError):
            self._send(502, {"error": "地图图块暂时取不到"})
            return
        if not data:
            self._send(404, {"error": "没有这块地图"})
            return
        self._send(200, data, "image/jpeg", extra_headers={"Cache-Control": "private, max-age=86400"})

    def _map(self, query):
        bounds = map_bounds(query or {})
        want_vehicles = (query or {}).get("vehicles", ["1"])[0] != "0"
        if self.demo:
            players = mark_online(
                [{"name": "林夏", "x": 10640, "y": 9740, "z": 0}],
                ["林夏"] if DEMO["running"] else [],
            )
            vehicles = []
            if want_vehicles and bounds:
                vehicles = [
                    row for row in DEMO_VEHICLES
                    if bounds[0] <= row["x"] <= bounds[1] and bounds[2] <= row["y"] <= bounds[3]
                ]
            self._send(200, map_payload(players, vehicles))
            return
        online = []
        try:
            online, _raw = host.list_players(self.config)
        except host.PanelError:
            online = []
        error = ""
        try:
            players = host.read_map(self.config, online)
        except host.PanelError as exc:
            players = []
            error = str(exc)
        vehicles = []
        capped = False
        if want_vehicles and bounds and not error:
            try:
                vehicles, capped = host.read_vehicles(self.config, bounds)
            except host.PanelError as exc:
                error = str(exc)
        self._send(200, map_payload(players, vehicles, capped, error))

    def _sandbox_read(self):
        if self.demo:
            fields = sandbox.parse_sandbox(DEMO_SANDBOX)
        else:
            try:
                fields = host.read_sandbox(self.config)
            except host.PanelError as exc:
                self._send(200, {"fields": [], "error": str(exc)})
                return
        self._send(200, {
            "note": "改的是沙盒文件。写入后不会马上生效，要重启游戏服才会进到这一局。这次不会重启。",
            "fields": [{key: value for key, value in item.items() if key != "line"} for item in fields],
        })

    def _sandbox_write(self, body):
        updates = body.get("values")
        if not isinstance(updates, dict) or len(updates) > 400:
            raise host.PanelError("没有要写入的沙盒项")
        if self.demo:
            sandbox.apply_sandbox(DEMO_SANDBOX, updates)
            self._send(200, {"ok": True, "changed": list(updates)})
            return
        changed = host.write_sandbox(self.config, updates)
        self._send(200, {"ok": True, "changed": changed})

    def _power(self, body):
        action = body.get("action")
        if action not in ("start", "stop", "restart"):
            raise host.PanelError("不认识这个操作")
        if self.demo:
            if action == "stop":
                DEMO["running"] = False
            elif action == "start":
                DEMO["running"] = True
                DEMO["started"] = time.time()
            else:
                DEMO["started"] = time.time()
                DEMO["running"] = True
            self._send(200, {"ok": True, "action": action})
            return
        host.change_power(self.config, action)
        self._send(200, {"ok": True, "action": action})

    def _message(self, body):
        text = str(body.get("text") or "").strip()
        if not text:
            raise host.PanelError("先写消息")
        quote_arg(text, "消息")
        if len(text) > 200:
            raise host.PanelError("消息太长了")
        if self.demo:
            self._send(200, {"ok": True})
            return
        host.send_message(self.config, text)
        self._send(200, {"ok": True})

    def _kick(self, body):
        name = str(body.get("username") or "")
        reason = str(body.get("reason") or "")
        quote_arg(name, "玩家名")
        if reason.strip():
            quote_arg(reason.strip(), "原因")
        if self.demo:
            if name not in DEMO["players"]:
                raise host.PanelError("这个玩家已经不在了")
            DEMO["players"] = [item for item in DEMO["players"] if item != name]
            self._send(200, {"ok": True})
            return
        host.kick_player(self.config, name, reason)
        self._send(200, {"ok": True})

    def _command(self, body):
        built = commands.build(body.get("id"), body.get("fields") or {})
        if self.demo:
            if not DEMO["running"]:
                raise host.PanelError("服务器关着，命令送不出去")
            self._send(200, {"ok": True, "reply": "演示服收到了这条命令", "label": built["label"]})
            return
        reply = host.run_command(self.config, built["line"])
        self._send(200, {
            "ok": True,
            "label": built["label"],
            "reply": reply or "服务器没有返回文字",
        })

    def _save(self):
        if self.demo:
            if not DEMO["running"]:
                raise host.PanelError("服务器关着，存不了")
            self._send(200, {"ok": True})
            return
        host.save_world(self.config)
        self._send(200, {"ok": True})

    def _files(self):
        if self.demo:
            self._send(200, {
                "files": [
                    {"label": "服务器配置", "name": "servertest.ini", "exists": True, "kind": "文件", "bytes": 4200, "mtime": "2026-10-11 22:00"},
                    {"label": "沙盒", "name": "servertest_SandboxVars.lua", "exists": True, "kind": "文件", "bytes": 44500, "mtime": "2026-10-11 22:00"},
                    {"label": "存档", "name": "servertest", "exists": True, "kind": "目录", "bytes": None, "mtime": "2026-10-12 03:00"},
                ],
                "backups": [],
                "mods": [{"id": "B42Trans_CN", "workshop": "3556544454"}],
                "note": "演示数据。击杀榜不是官方存档里的项目。聊天在「记录」。改模组这次不会写。",
            })
            return
        payload = host.server_files(self.config)
        try:
            shown = host.read_config_view(self.config)
            payload["mods"] = shown.get("mods") or []
        except host.PanelError:
            payload["mods"] = []
        self._send(200, payload)

    def _backup(self):
        if self.demo:
            raise host.PanelError("演示服不会写备份")
        host.save_world(self.config)
        name = host.backup_world(self.config)
        self._send(200, {"ok": True, "name": name})


def serve(config, demo=False):
    Handler.config = config
    Handler.demo = demo
    listen = "127.0.0.1" if demo else config["listen"]
    port = 3010 if demo else int(config["port"])
    server = ThreadingHTTPServer((listen, port), Handler)
    print(f"岗亭 http://{listen}:{port}", flush=True)
    if demo:
        print("演示密码 demo-home", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    import sys
    demo = "--demo" in sys.argv
    if demo:
        serve(None, demo=True)
    else:
        config_path = ROOT / "config.json"
        for arg in sys.argv[1:]:
            if arg.startswith("--config="):
                config_path = Path(arg.split("=", 1)[1])
        serve(load_config(config_path))
