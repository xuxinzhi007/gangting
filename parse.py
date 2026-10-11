"""Pure parsers for ini files, player lists, and systemd status."""

import re

def parse_ini(text):
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def public_config(values):
    mods = [item for item in values.get("Mods", "").split(";") if item]
    workshops = [item for item in values.get("WorkshopItems", "").split(";") if item]
    pairs = []
    for index, mod_id in enumerate(mods):
        pairs.append({
            "id": mod_id,
            "workshop": workshops[index] if index < len(workshops) else "",
        })
    return {
        "publicName": values.get("PublicName") or "家用服务器",
        "map": values.get("Map") or "",
        "port": values.get("DefaultPort") or "",
        "udpPort": values.get("UDPPort") or "",
        "maxPlayers": values.get("MaxPlayers") or "",
        "open": values.get("Open", "").lower() == "true",
        "public": values.get("Public", "").lower() == "true",
        "hasPassword": bool(values.get("Password")),
        "mods": pairs,
        "rules": server_rules(values),
    }


def _shown_flag(values, key, on, off):
    raw = values.get(key)
    if raw is None or raw == "":
        return None
    return on if raw.lower() == "true" else off


def server_rules(values):
    specs = (
        ("PVP", "玩家对战", "开着", "关着"),
        ("PauseEmpty", "没人时", "会暂停", "继续跑"),
        ("GlobalChat", "公屏", "开着", "关着"),
        ("VoiceEnable", "语音", "开着", "关着"),
        ("SleepAllowed", "睡觉", "允许", "不允许"),
    )
    rules = []
    for key, label, on, off in specs:
        shown = _shown_flag(values, key, on, off)
        if shown:
            rules.append({"label": label, "value": shown})
    rules.append({
        "label": "进服密码",
        "value": "有" if values.get("Password") else "没有",
    })
    return rules


_TIME = re.compile(r"^\[([^\]]+)\]\s*(.*)$")
_EVENT = re.compile(r'event="([^"]+)"')
_USERNAME = re.compile(r'username="([^"]*)"')
_NOISE = ("ItemPickInfo", "shared-descriptor", "not consistent", "ThumpPacket")


def _split_time(line):
    match = _TIME.match(line.strip())
    if not match:
        return "", line.strip()
    return match.group(1), match.group(2).strip()


def parse_visits(lines):
    events = []
    for raw in lines or []:
        when, body = _split_time(raw)
        found = _EVENT.search(body)
        if not found:
            continue
        kind = found.group(1)
        if kind == "fully-connected":
            action = "进来了"
        elif kind == "disconnect":
            action = "离开了"
        else:
            continue
        user = _USERNAME.search(body)
        events.append({
            "time": when,
            "name": user.group(1).strip() if user else "",
            "action": action,
        })
    return events[-16:]


def parse_chat(lines):
    items = []
    for raw in lines or []:
        when, body = _split_time(raw)
        if not body:
            continue
        lowered = body.lower()
        if lowered.startswith("[info]") or "disconnecting player" in lowered:
            continue
        items.append({"time": when, "text": body[:240]})
    return items[-20:]


def mark_online(saved, online_names):
    online = set(online_names or [])
    known = set()
    marked = []
    for row in saved or []:
        item = {
            "name": row.get("name") or "",
            "account": row.get("account") or "",
            "x": row.get("x"),
            "y": row.get("y"),
            "z": row.get("z"),
            "dead": bool(row.get("dead")),
            "online": False,
        }
        names = {item["name"], item["account"]}
        item["online"] = bool(names & online)
        known.update(names)
        marked.append(item)
    for name in online_names or []:
        if name not in known:
            marked.append({"name": name, "account": name, "x": None, "y": None, "z": None, "dead": False, "online": True})
    return marked


def quiet_lines(lines):
    kept = [line for line in lines or [] if not any(part in line for part in _NOISE)]
    return kept[-60:]


def parse_players(text):
    players = []
    for raw in (text or "").splitlines():
        line = raw[:-1] if raw.endswith("\r") else raw
        if line.startswith("-"):
            name = line[1:]
            if name:
                players.append(name)
    return players


def parse_systemctl_show(text):
    fields = {}
    for raw in text.splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        fields[key.strip()] = value.strip()
    state = fields.get("ActiveState", "unknown")
    mono = fields.get("ActiveEnterTimestampMonotonic") or "0"
    try:
        monotonic = int(mono)
    except ValueError:
        monotonic = 0
    return {
        "state": state,
        "sub": fields.get("SubState", ""),
        "running": state == "active",
        "failed": state == "failed",
        "monotonicUsec": monotonic if state == "active" else 0,
        "pid": fields.get("MainPID") or "",
    }


def uptime_from_monotonic(monotonic_usec, proc_uptime_seconds):
    if not monotonic_usec:
        return 0
    started = monotonic_usec / 1_000_000
    return max(0, proc_uptime_seconds - started)


def cpu_percent(previous, current):
    total_delta = current[0] - previous[0]
    idle_delta = current[1] - previous[1]
    if total_delta <= 0:
        return None
    return round((total_delta - idle_delta) * 100 / total_delta, 1)


def cpu_sample(stat_text):
    line = ""
    for raw in stat_text.splitlines():
        if raw.startswith("cpu "):
            line = raw
            break
    numbers = [int(part) for part in line.split()[1:]]
    if len(numbers) < 4:
        raise ValueError("cpu")
    idle = numbers[3] + (numbers[4] if len(numbers) > 4 else 0)
    return sum(numbers), idle


def memory_bytes(meminfo_text):
    values = {}
    for raw in meminfo_text.splitlines():
        key, _, rest = raw.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0]) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None, None
    return total - available, total
    if not monotonic_usec:
        return 0
    return max(0, proc_uptime_seconds - (monotonic_usec / 1_000_000))


def format_uptime(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "不到 1 分钟"
    minutes = seconds // 60
    days, minutes = divmod(minutes, 60 * 24)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if minutes:
        parts.append(f"{minutes} 分钟")
    return " ".join(parts)


def quote_arg(value, label, max_len=64):
    text = str(value or "")
    if not text or len(text) > max_len or any(ch in text for ch in "\r\n\"\\"):
        raise ValueError(f"{label}不能包含引号或换行")
    return text
