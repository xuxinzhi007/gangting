"""Host adapters: systemd, ini, logs, and RCON actions."""

import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import rcon
import sandbox
from parse import cpu_percent, cpu_sample, mark_online, memory_bytes, parse_chat, parse_ini, parse_players, parse_systemctl_show, parse_visits, public_config, quote_arg, uptime_from_monotonic

SERVICE_NAME = re_service = __import__("re").compile(r"^[a-zA-Z0-9_.@:-]+$")


class PanelError(Exception):
    pass


def _service_name(config):
    name = config.get("service") or "pzserver.service"
    if not SERVICE_NAME.match(name):
        raise PanelError("服务名不合法")
    return name


def _systemctl(config, verb, *args):
    command = ["systemctl", verb, _service_name(config), *args]
    if config.get("useSudo"):
        command = ["sudo", "-n", *command]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PanelError("这台机器上没有 systemctl") from exc
    except subprocess.TimeoutExpired as exc:
        raise PanelError("系统服务没有及时回应") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise PanelError(detail or "系统服务拒绝了这个操作")
    return result.stdout


_CPU_SAMPLE = None


def read_usage(config):
    usage = {
        "cpu": None,
        "memUsed": None,
        "memTotal": None,
        "diskUsed": None,
        "diskTotal": None,
        "gameMem": None,
    }
    global _CPU_SAMPLE
    try:
        sample = cpu_sample(Path("/proc/stat").read_text(encoding="utf-8"))
        if _CPU_SAMPLE is not None:
            usage["cpu"] = cpu_percent(_CPU_SAMPLE, sample)
        _CPU_SAMPLE = sample
    except (OSError, ValueError):
        pass
    try:
        usage["memUsed"], usage["memTotal"] = memory_bytes(Path("/proc/meminfo").read_text(encoding="utf-8"))
    except OSError:
        pass
    try:
        anchor = Path(config["iniPath"]).resolve().parent
        disk = shutil.disk_usage(anchor if anchor.exists() else "/")
        usage["diskUsed"] = disk.used
        usage["diskTotal"] = disk.total
    except OSError:
        pass
    try:
        status = read_status(config)
        pid = int(status.get("pid") or 0)
        if pid > 0 and status["running"]:
            for raw in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
                if raw.startswith("VmRSS:"):
                    usage["gameMem"] = int(raw.split()[1]) * 1024
                    break
    except (OSError, ValueError, PanelError):
        pass
    return usage


def read_status(config):
    text = _systemctl(
        config,
        "show",
        "-p", "ActiveState",
        "-p", "SubState",
        "-p", "ActiveEnterTimestampMonotonic",
        "-p", "MainPID",
        "--no-pager",
    )
    status = parse_systemctl_show(text)
    status["uptimeSec"] = 0
    if status["running"] and status["monotonicUsec"]:
        try:
            booted_for = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        except (OSError, ValueError):
            booted_for = 0
        status["uptimeSec"] = int(uptime_from_monotonic(status["monotonicUsec"], booted_for))
    return status


def read_config_view(config):
    path = Path(config["iniPath"])
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PanelError("读不到服务器配置") from exc
    values = parse_ini(text)
    return public_config(values)


def save_directory(config):
    server = Path(config["iniPath"]).stem
    return Path(config["iniPath"]).resolve().parent.parent / "Saves" / "Multiplayer" / server


def zomboid_root(config):
    return Path(config["iniPath"]).resolve().parent.parent


def _file_row(label, path):
    path = Path(path)
    row = {"label": label, "name": path.name, "exists": False, "kind": "", "bytes": None, "mtime": ""}
    try:
        if not path.exists():
            return row
        info = path.stat()
    except OSError:
        return row
    row["exists"] = True
    row["kind"] = "目录" if path.is_dir() else "文件"
    row["bytes"] = None if path.is_dir() else info.st_size
    row["mtime"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(info.st_mtime))
    return row


def server_files(config):
    folder = Path(config["iniPath"]).resolve().parent
    server = Path(config["iniPath"]).stem
    log_path = (config.get("logPath") or "").strip()
    rows = [
        _file_row("服务器配置", folder / f"{server}.ini"),
        _file_row("沙盒", sandbox_file(config)),
        _file_row("出生点", folder / f"{server}_spawnpoints.lua"),
        _file_row("出生区域", folder / f"{server}_spawnregions.lua"),
        _file_row("控制台日志", log_path or folder / "missing-log"),
        _file_row("存档", save_directory(config)),
    ]
    backups = []
    root = zomboid_root(config) / "backups"
    if root.is_dir():
        for child in sorted(root.iterdir(), key=lambda item: item.name, reverse=True):
            if child.is_dir() and child.name.startswith(f"{server}-"):
                backups.append(child.name)
            if len(backups) >= 12:
                break
    return {
        "files": rows,
        "backups": backups,
        "note": "这里只列出服务器自己的文件，不改模组，也不打开配置正文。击杀榜不是官方存档里的项目。聊天在「记录」。",
    }


def backup_world(config):
    source = save_directory(config)
    if not source.is_dir():
        raise PanelError("还没有存档目录")
    root = zomboid_root(config) / "backups"
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = root / f"{source.name}-{stamp}"
    if dest.exists():
        raise PanelError("这一秒的备份已经有了")
    try:
        shutil.copytree(source, dest, symlinks=False)
    except OSError as exc:
        raise PanelError("备份没有写完") from exc
    return dest.name


def sandbox_file(config):
    folder = Path(config["iniPath"]).resolve().parent
    return folder / f"{Path(config['iniPath']).stem}_SandboxVars.lua"


def read_sandbox(config):
    path = sandbox_file(config)
    if not path.is_file():
        raise PanelError("还没有沙盒文件")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PanelError("读不到沙盒文件") from exc
    return sandbox.parse_sandbox(text)


def write_sandbox(config, updates):
    path = sandbox_file(config)
    if not path.is_file():
        raise PanelError("还没有沙盒文件")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PanelError("读不到沙盒文件") from exc
    rewritten, changed = sandbox.apply_sandbox(text, updates)
    if not changed:
        return []
    backup = path.with_name(path.name + ".bak")
    temporary = path.with_name(path.name + ".tmp")
    try:
        backup.write_bytes(path.read_bytes())
        temporary.write_bytes(rewritten.encode("utf-8"))
        temporary.replace(path)
    except OSError as exc:
        raise PanelError("沙盒文件没有写入") from exc
    return changed


def read_saved_positions(config):
    database = save_directory(config) / "players.db"
    if not database.is_file():
        raise PanelError("还没有存档，地图上没有人")
    uri = database.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=3)
    except sqlite3.Error as exc:
        raise PanelError("存档正被服务器占用，这次没读到坐标") from exc
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "networkPlayers" not in tables:
            raise PanelError("存档里没有玩家坐标表")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(networkPlayers)")}
        name_col = next((item for item in ("username", "name") if item in columns), None)
        if not name_col or not {"x", "y", "z"} <= columns:
            raise PanelError("存档里的玩家表没有坐标")
        dead = "isDead" in columns
        saved = []
        if "username" in columns and "name" in columns:
            chosen = "username, name, x, y, z" + (", isDead" if dead else "")
            for row in connection.execute(f"SELECT {chosen} FROM networkPlayers"):
                account, character, x, y, z = row[0], row[1], row[2], row[3], row[4]
                saved.append({
                    "name": character or account or "",
                    "account": account or "",
                    "x": x,
                    "y": y,
                    "z": z,
                    "dead": bool(row[5]) if dead else False,
                })
            return saved
        chosen = f"{name_col}, x, y, z" + (", isDead" if dead else "")
        for row in connection.execute(f"SELECT {chosen} FROM networkPlayers"):
            saved.append({
                "name": row[0] or "",
                "account": row[0] or "",
                "x": row[1],
                "y": row[2],
                "z": row[3],
                "dead": bool(row[4]) if dead else False,
            })
        return saved
    except sqlite3.Error as exc:
        raise PanelError("存档正被服务器占用，这次没读到坐标") from exc
    finally:
        connection.close()


def read_map(config, online_names):
    return mark_online(read_saved_positions(config), online_names)


def vehicle_rows(database, bounds, limit=1200):
    path = Path(database)
    if not path.is_file():
        return [], False
    minx, maxx, miny, maxy = bounds
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=3)
    except sqlite3.Error as exc:
        raise PanelError("存档正被服务器占用，这次没读到车辆") from exc
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "vehicles" not in tables:
            return [], False
        columns = {row[1] for row in connection.execute("PRAGMA table_info(vehicles)")}
        if not {"x", "y"} <= columns:
            return [], False
        ident = "id" if "id" in columns else "rowid"
        query = (
            f"SELECT {ident}, x, y FROM vehicles "
            "WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ? LIMIT ?"
        )
        rows = []
        for vehicle_id, x, y in connection.execute(query, (minx, maxx, miny, maxy, limit)):
            if x is None or y is None:
                continue
            rows.append({"id": vehicle_id, "x": x, "y": y})
        return rows, len(rows) >= limit
    except sqlite3.Error as exc:
        raise PanelError("存档正被服务器占用，这次没读到车辆") from exc
    finally:
        connection.close()


def read_vehicles(config, bounds):
    return vehicle_rows(save_directory(config) / "vehicles.db", bounds)


def read_activity(config):
    root = Path(config["iniPath"]).resolve().parent.parent / "Logs"
    if not root.is_dir():
        return [], []
    visit_file = _newest(root, "_connections.txt")
    chat_file = _newest(root, "_chat.txt")
    visits = parse_visits(_tail(visit_file, 80)) if visit_file else []
    chat = parse_chat(_tail(chat_file, 80)) if chat_file else []
    return visits, chat


def _newest(directory, suffix):
    files = [item for item in directory.glob(f"*{suffix}") if item.is_file()]
    if not files:
        return None
    return max(files, key=lambda item: item.stat().st_mtime)


def read_logs(config, lines=120):
    lines = max(20, min(int(lines), 400))
    log_path = (config.get("logPath") or "").strip()
    if log_path:
        path = Path(log_path)
        if path.is_dir():
            files = sorted(path.glob("*.txt"), key=lambda item: item.stat().st_mtime)
            path = files[-1] if files else None
        if path and path.is_file():
            return _tail(path, lines)
    return _journal(config, lines)


def _tail(path, lines):
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            block = min(size, lines * 400)
            handle.seek(size - block)
            data = handle.read().decode("utf-8", errors="replace")
    except OSError as exc:
        raise PanelError("读不到日志") from exc
    return data.splitlines()[-lines:]


def _journal(config, lines):
    command = [
        "journalctl", "-u", _service_name(config),
        "-n", str(lines), "--no-pager", "-o", "cat",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise PanelError("读不到日志") from exc
    if result.returncode != 0:
        raise PanelError((result.stderr or "读不到日志").strip())
    return result.stdout.splitlines()


def _rcon(config, command):
    try:
        return rcon.execute(
            config.get("rconHost") or "127.0.0.1",
            config.get("rconPort") or 27015,
            config.get("rconPassword") or "",
            command,
        )
    except rcon.RconError as exc:
        raise PanelError(str(exc)) from exc


def list_players(config):
    text = _rcon(config, "players")
    return parse_players(text), text


def save_world(config):
    return _rcon(config, "save")


def run_command(config, line):
    return _rcon(config, line)


def send_message(config, message):
    text = quote_arg(message.strip(), "消息")
    if len(text) > 200:
        raise PanelError("消息太长了")
    return _rcon(config, f'servermsg "{text}"')


def kick_player(config, username, reason):
    name = quote_arg(username, "玩家名")
    command = f'kickuser "{name}"'
    if reason and reason.strip():
        why = quote_arg(reason.strip(), "原因")
        command += f' -r "{why}"'
    return _rcon(config, command)


def change_power(config, action):
    if action not in ("start", "stop", "restart"):
        raise PanelError("不认识这个操作")
    if action in ("stop", "restart"):
        try:
            _rcon(config, "save")
        except PanelError:
            # A stopped server has no management port. The power change still proceeds.
            pass
    _systemctl(config, action)
    return action
