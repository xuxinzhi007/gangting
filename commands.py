"""Build Project Zomboid console commands from a fixed catalog.

The browser picks a command id and fills fields. It never sends the
command string, so a request cannot smuggle extra console text.
"""

from parse import quote_arg

ACCESS_LEVELS = ("user", "priority", "observer", "gm", "moderator", "admin")
PERKS = (
    "Woodwork", "Doctor", "Electricity", "PlantScavenging", "Sprinting", "Lightfoot",
    "Sneak", "SmallBlade", "SmallBlunt", "Blunt", "MetalWelding", "Blacksmith",
    "Farming", "Husbandry", "Axe", "LongBlade", "Spear", "Maintenance", "Aiming",
    "Reloading", "Fitness", "Strength", "Nimble", "Cooking", "Mechanics", "Tailoring",
    "Masonry", "Pottery", "Glassmaking", "Carving", "Fishing", "Trapping", "Butchering",
    "Tracking",
)
LOG_TYPES = (
    "General", "Network", "Multiplayer", "Voice", "Packet", "NetworkFileDebug", "Lua",
    "Mod", "Sound", "Zombie", "Combat", "Objects", "Fireplace", "Radio", "MapLoading",
    "Clothing", "Animation", "Asset", "Script", "Shader", "Input", "Recipe", "ActionSystem",
    "IsoRegion", "UniTests", "FileIO", "Ownership", "Death", "Damage", "Statistic",
    "Vehicle", "Checksum",
)
LOG_LEVELS = ("Trace", "Debug", "General", "Warning", "Error")
WORLDGEN = ("status", "start", "recheck", "stop")
STATS_TARGETS = ("none", "file", "console", "all")

_TOKEN = r"^[A-Za-z][A-Za-z0-9_]*$"
_ITEM = r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$"
_STEAM = r"^\d{10,20}$"
_IP = r"^\d{1,3}(\.\d{1,3}){3}$"
_OPTION = r"^[A-Za-z][A-Za-z0-9]*$"
_COORDS = r"^-?\d{1,6},-?\d{1,6},-?\d{1,3}$"
_LUA = r"^[A-Za-z0-9_./-]{1,80}$"


def _text(fields, name, label, required=False, limit=64):
    value = str(fields.get(name) or "").strip()
    if not value:
        if required:
            raise ValueError(f"先填写{label}")
        return ""
    return quote_arg(value, label, limit)


def _choice(fields, name, label, options, required=True):
    value = str(fields.get(name) or "").strip()
    if not value:
        if required:
            raise ValueError(f"先选择{label}")
        return ""
    if value not in options:
        raise ValueError(f"{label}不在可选范围里")
    return value


def _number(fields, name, label, low, high, required=True):
    raw = str(fields.get(name) or "").strip()
    if not raw:
        if required:
            raise ValueError(f"先填写{label}")
        return None
    if not raw.isdigit():
        raise ValueError(f"{label}要填整数")
    value = int(raw)
    if value < low or value > high:
        raise ValueError(f"{label}要在 {low} 到 {high} 之间")
    return value


def _flag(fields, name):
    return bool(fields.get(name))


def _pattern(fields, name, label, pattern, required=True):
    import re
    value = str(fields.get(name) or "").strip()
    if not value:
        if required:
            raise ValueError(f"先填写{label}")
        return ""
    if not re.match(pattern, value):
        raise ValueError(f"{label}的格式不对")
    return value


def _player(fields, name="username"):
    return _text(fields, name, "玩家名", required=True)


def _access(fields):
    level = _choice(fields, "level", "权限", ACCESS_LEVELS)
    return f'setaccesslevel "{_player(fields)}" "{level}"', False


def _save(_fields):
    return "save", False


def _quit(_fields):
    return "quit", False


def _reloadoptions(_fields):
    return "reloadoptions", False


def _showoptions(_fields):
    return "showoptions", False


def _check_mods(_fields):
    return "checkModsNeedUpdate", False


def _players(_fields):
    return "players", False


def _list(_fields):
    return "list", False


def _help(fields):
    name = _pattern(fields, "command", "命令名", _TOKEN, required=False)
    return (f'help "{name}"' if name else "help"), False


def _servermsg(fields):
    text = _text(fields, "text", "消息", required=True, limit=200)
    return f'servermsg "{text}"', False


def _changeoption(fields):
    option = _pattern(fields, "option", "选项名", _OPTION)
    value = _text(fields, "value", "新的值", required=True, limit=200)
    return f'changeoption {option} "{value}"', False


def _stats(fields):
    target = _choice(fields, "target", "输出位置", STATS_TARGETS)
    period = _number(fields, "period", "间隔秒数", 0, 3600, required=False)
    if period is None:
        return f"stats {target}", False
    return f"stats {target} {period}", False


def _log(fields):
    kind = _choice(fields, "type", "日志类别", LOG_TYPES)
    level = _choice(fields, "level", "级别", LOG_LEVELS)
    return f'log "{kind}" "{level}"', False


def _reloadlua(fields):
    name = _pattern(fields, "filename", "脚本名", _LUA)
    if ".." in name:
        raise ValueError("脚本名不能包含 ..")
    return f'reloadlua "{name}"', False


def _reloadall(_fields):
    return "reloadalllua", False


def _worldgen(fields):
    action = _choice(fields, "action", "动作", WORLDGEN)
    return f"worldgen {action}", False


def _adduser(fields):
    name = _player(fields)
    password = _text(fields, "password", "密码", required=True, limit=80)
    return f'adduser "{name}" "{password}"', True


def _setpassword(fields):
    name = _player(fields)
    password = _text(fields, "password", "密码", required=True, limit=80)
    return f'setpassword "{name}" "{password}"', True


def _whitelist_remove(fields):
    return f'removeuserfromwhitelist "{_player(fields)}"', False


def _add_steam(fields):
    return f'addsteamid "{_pattern(fields, "steamid", "SteamID", _STEAM)}"', False


def _remove_steam(fields):
    return f'removesteamid "{_pattern(fields, "steamid", "SteamID", _STEAM)}"', False


def _kick(fields):
    command = f'kickuser "{_player(fields)}"'
    reason = _text(fields, "reason", "原因", limit=80)
    if reason:
        command += f' -r "{reason}"'
    return command, False


def _ban(fields):
    command = f'banuser "{_player(fields)}"'
    if _flag(fields, "ip"):
        command += " -ip"
    reason = _text(fields, "reason", "原因", limit=80)
    if reason:
        command += f' -r "{reason}"'
    return command, False


def _unban(fields):
    return f'unbanuser "{_player(fields)}"', False


def _banid(fields):
    return f'banid {_pattern(fields, "steamid", "SteamID", _STEAM)}', False


def _unbanid(fields):
    return f'unbanid {_pattern(fields, "steamid", "SteamID", _STEAM)}', False


def _banip(fields):
    return f'banip {_pattern(fields, "ip", "IP", _IP)}', False


def _unbanip(fields):
    return f'unbanip {_pattern(fields, "ip", "IP", _IP)}', False


def _voice(fields):
    state = "-true" if _flag(fields, "blocked") else "-false"
    return f'voiceban "{_player(fields)}" {state}', False


def _clear_symbols(fields):
    return f'removemapsymbolsforuser "{_player(fields)}"', False


def _teleport_spot(fields):
    _player(fields)
    _pattern(fields, "coords", "坐标", _COORDS)
    raise ValueError("这台服务器不能把指定玩家传到坐标，只能把一名在线玩家传到另一名在线玩家身边")


def _teleport_player(fields):
    return f'teleportplayer "{_player(fields, "username")}" "{_player(fields, "target")}"', False


def _teleport_to(fields):
    return f'teleportto {_pattern(fields, "coords", "坐标", _COORDS)}', False


def _toggle(verb):
    def build(fields):
        state = "-true" if _flag(fields, "enabled") else "-false"
        return f'{verb} "{_player(fields)}" {state}', False
    return build


def _additem(fields):
    count = _number(fields, "count", "数量", 1, 100)
    item = _pattern(fields, "item", "物品编号", _ITEM)
    return f'additem "{_player(fields)}" "{item}" {count}', False


def _removeitem(fields):
    count = _number(fields, "count", "数量", 0, 100)
    item = _pattern(fields, "item", "物品编号", _ITEM)
    return f'removeitem "{item}" {count}', False


def _addkey(fields):
    key_id = _text(fields, "keyId", "钥匙编号", required=True, limit=32)
    name = _text(fields, "keyName", "钥匙名称", limit=40)
    command = f'addkey "{_player(fields)}" "{key_id}"'
    if name:
        command += f' "{name}"'
    return command, False


def _addvehicle(fields):
    script = _pattern(fields, "script", "车辆编号", _ITEM)
    where = _text(fields, "where", "玩家或坐标", required=True, limit=40)
    if "," in where:
        _pattern({"coords": where}, "coords", "坐标", _COORDS)
        return f'addvehicle "{script}" "{where}"', False
    return f'addvehicle "{script}" "{quote_arg(where, "玩家名")}"', False


def _addxp(fields):
    perk = _choice(fields, "perk", "技能", PERKS)
    amount = _number(fields, "amount", "经验", 1, 100000)
    return f'addxp "{_player(fields)}" {perk}={amount}', False


def _horde(fields):
    count = _number(fields, "count", "数量", 1, 80)
    return f'createhorde {count} "{_player(fields)}"', False


def _named(verb):
    def build(fields):
        return f'{verb} "{_player(fields)}"', False
    return build


def _bare(verb):
    def build(_fields):
        return verb, False
    return build


def _time_speed(fields):
    period = _number(fields, "period", "流速", 0, 200)
    return f"setTimeSpeed {period}", False


def _rain(fields):
    amount = _number(fields, "intensity", "强度", 1, 100, required=False)
    if amount is None:
        return "startrain", False
    return f'startrain "{amount}"', False


def _storm(fields):
    hours = _number(fields, "hours", "持续小时", 1, 24, required=False)
    if hours is None:
        return "startstorm", False
    return f'startstorm "{hours}"', False


def _spec(command_id, group, label, official, help_text, builder, fields=(), danger=False):
    return {
        "id": command_id,
        "group": group,
        "label": label,
        "official": official,
        "help": help_text,
        "danger": danger,
        "fields": list(fields),
        "build": builder,
    }


def _field(name, label, kind, **extra):
    field = {"name": name, "label": label, "kind": kind}
    field.update(extra)
    return field


SPECS = (
    _spec("save", "服务器", "立即存档", "save", "把当前世界写进磁盘。", _save),
    _spec("showoptions", "服务器", "查看选项", "showoptions", "把正在生效的服务器选项读回来。", _showoptions),
    _spec("changeoption", "服务器", "改一项选项", "changeoption", "只改这一项。沙盒规则不在这里。", _changeoption, (
        _field("option", "选项名", "text", placeholder="SleepAllowed"),
        _field("value", "新的值", "text", placeholder="true"),
    ), danger=True),
    _spec("reloadoptions", "服务器", "重新读取配置", "reloadoptions", "重新读取 ini，并推给已经在线的人。", _reloadoptions, danger=True),
    _spec("checkmods", "服务器", "检查模组更新", "checkModsNeedUpdate", "结果写在服务器日志里。", _check_mods),
    _spec("stats", "服务器", "统计输出", "stats", "决定统计写到文件、控制台，或关掉。", _stats, (
        _field("target", "输出位置", "select", options=STATS_TARGETS),
        _field("period", "间隔秒数", "number", required=False, min=0, max=3600),
    )),
    _spec("loglevel", "服务器", "日志级别", "log", "只调整一类日志的详细程度。", _log, (
        _field("type", "类别", "select", options=LOG_TYPES),
        _field("level", "级别", "select", options=LOG_LEVELS),
    )),
    _spec("reloadlua", "服务器", "重载一个脚本", "reloadlua", "文件名按服务器上的脚本路径填。", _reloadlua, (
        _field("filename", "脚本名", "text", placeholder="server/Items/MyItem.lua"),
    ), danger=True),
    _spec("reloadalllua", "服务器", "重载全部脚本", "reloadalllua", "会把服务器上的 Lua 全部重载一次。", _reloadall, danger=True),
    _spec("worldgen", "服务器", "世界生成", "worldgen", "官方写了四个动作：查看、开始、复查、停止。", _worldgen, (
        _field("action", "动作", "select", options=WORLDGEN),
    ), danger=True),
    _spec("quit", "服务器", "存档并退出", "quit", "游戏服自己存档后退出。人会被断开。", _quit, danger=True),
    _spec("players", "账号", "在线名单", "players", "再读一次当前在线的人。", _players),
    _spec("list", "账号", "列出账号", "list", "官方没有写这个命令的参数。", _list),
    _spec("help", "账号", "命令说明", "help", "不填就列出全部，填了就看这一条。", _help, (
        _field("command", "命令名", "text", required=False, placeholder="kickuser"),
    )),
    _spec("servermsg", "账号", "发给所有人", "servermsg", "在游戏里给所有在线的人发一条公告。", _servermsg, (
        _field("text", "内容", "text", placeholder="十分钟后重启"),
    )),
    _spec("setaccesslevel", "账号", "设置权限", "setaccesslevel", "这台服务器认这些等级：user、priority、observer、gm、moderator、admin。普通玩家用 user。", _access, (
        _field("username", "玩家名", "player"),
        _field("level", "权限", "select", options=ACCESS_LEVELS),
    ), danger=True),
    _spec("adduser", "账号", "添加账号", "adduser", "白名单服用来建账号。密码不会回显。", _adduser, (
        _field("username", "玩家名", "text"),
        _field("password", "密码", "password"),
    )),
    _spec("setpassword", "账号", "修改密码", "setpassword", "改这个账号的密码。密码不会回显。", _setpassword, (
        _field("username", "玩家名", "text"),
        _field("password", "新密码", "password"),
    )),
    _spec("unwhitelist", "账号", "移出白名单", "removeuserfromwhitelist", "这个人不能再凭白名单进入。", _whitelist_remove, (
        _field("username", "玩家名", "text"),
    ), danger=True),
    _spec("addsteamid", "账号", "允许 SteamID", "addsteamid", "把这个 SteamID 加进允许列表。", _add_steam, (
        _field("steamid", "SteamID", "text"),
    )),
    _spec("removesteamid", "账号", "移除 SteamID", "removesteamid", "从允许列表里拿掉这个 SteamID。", _remove_steam, (
        _field("steamid", "SteamID", "text"),
    ), danger=True),
    _spec("kickuser", "处罚", "踢出", "kickuser", "立刻断开这个人，可以选择写原因。", _kick, (
        _field("username", "玩家名", "player"),
        _field("reason", "原因", "text", required=False),
    ), danger=True),
    _spec("banuser", "处罚", "封禁账号", "banuser", "可以同时封 IP。", _ban, (
        _field("username", "玩家名", "player"),
        _field("ip", "同时封 IP", "check"),
        _field("reason", "原因", "text", required=False),
    ), danger=True),
    _spec("unbanuser", "处罚", "解除账号封禁", "unbanuser", "按玩家名解除。", _unban, (
        _field("username", "玩家名", "text"),
    )),
    _spec("banid", "处罚", "封禁 SteamID", "banid", "人下线了也能封。", _banid, (
        _field("steamid", "SteamID", "text"),
    ), danger=True),
    _spec("unbanid", "处罚", "解除 SteamID 封禁", "unbanid", "按 SteamID 解除。", _unbanid, (
        _field("steamid", "SteamID", "text"),
    )),
    _spec("banip", "处罚", "封禁 IP", "banip", "Build 42.19 起对直连恢复了这条。", _banip, (
        _field("ip", "IP", "text", placeholder="192.168.1.20"),
    ), danger=True),
    _spec("unbanip", "处罚", "解除 IP 封禁", "unbanip", "按 IP 解除。", _unbanip, (
        _field("ip", "IP", "text"),
    )),
    _spec("voiceban", "处罚", "语音开关", "voiceban", "勾上是禁言，取消勾选是恢复。", _voice, (
        _field("username", "玩家名", "player"),
        _field("blocked", "禁止语音", "check"),
    )),
    _spec("clearsymbols", "处罚", "清掉地图标记", "removemapsymbolsforuser", "删掉这个人画给大家看的地图标记。", _clear_symbols, (
        _field("username", "玩家名", "player"),
    ), danger=True),
    _spec("teleportspot", "传送", "传到这个坐标", "teleport", "服务器自己的说明里，传送到坐标没有玩家名。专用服务器没有自己的角色，所以这条不会移动你选中的人。", _teleport_spot, (
        _field("username", "玩家名", "player"),
        _field("coords", "坐标", "text", placeholder="10646,9654,0"),
    ), danger=True),
    _spec("teleportplayer", "传送", "传到另一名玩家", "teleportplayer", "控制台没有自己的角色，所以要写两个人。", _teleport_player, (
        _field("username", "被传送的人", "player"),
        _field("target", "目标玩家", "player"),
    )),
    _spec("teleportto", "传送", "传到坐标", "teleportto", "三个数用英文逗号分开。这条移动的是控制台自己的角色；专用服务器没有这个角色时，用上面的「传到另一名玩家」。", _teleport_to, (
        _field("coords", "坐标", "text", placeholder="10646,9654,0"),
    )),
    _spec("godmode", "状态", "无敌", "godmode", "勾上开启，取消勾选关闭。", _toggle("godmode"), (
        _field("username", "玩家名", "player"),
        _field("enabled", "开启", "check"),
    )),
    _spec("invisible", "状态", "对僵尸隐身", "invisible", "勾上开启，取消勾选关闭。", _toggle("invisible"), (
        _field("username", "玩家名", "player"),
        _field("enabled", "开启", "check"),
    )),
    _spec("noclip", "状态", "穿墙", "noclip", "勾上开启，取消勾选关闭。", _toggle("noclip"), (
        _field("username", "玩家名", "player"),
        _field("enabled", "开启", "check"),
    )),
    _spec("additem", "发放", "给物品", "additem", "编号要写模块.物品，区分大小写，例如 Base.Axe。", _additem, (
        _field("username", "玩家名", "player"),
        _field("item", "物品编号", "text", placeholder="Base.Axe"),
        _field("count", "数量", "number", min=1, max=100),
    )),
    _spec("removeitem", "发放", "移除物品", "removeitem", "这条作用在控制台自己身上。数量 0 表示这一类全删。", _removeitem, (
        _field("item", "物品编号", "text", placeholder="Base.Axe"),
        _field("count", "数量", "number", min=0, max=100),
    ), danger=True),
    _spec("addkey", "发放", "给钥匙", "addkey", "钥匙编号按游戏里的 keyId 填。", _addkey, (
        _field("username", "玩家名", "player"),
        _field("keyId", "钥匙编号", "text"),
        _field("keyName", "名称", "text", required=False),
    )),
    _spec("addvehicle", "发放", "生成车辆", "addvehicle", "位置填玩家名，或填 x,y,z。", _addvehicle, (
        _field("script", "车辆编号", "text", placeholder="Base.Van"),
        _field("where", "玩家或坐标", "text", placeholder="xiaoxin"),
    )),
    _spec("addxp", "发放", "给经验", "addxp", "技能用内部名。木工是 Woodwork，不是 Carpentry。", _addxp, (
        _field("username", "玩家名", "player"),
        _field("perk", "技能", "select", options=PERKS),
        _field("amount", "经验", "number", min=1, max=100000),
    )),
    _spec("createhorde", "世界", "生成尸潮", "createhorde", "出现在这名玩家旁边。这台小主机一次最多 80 只。", _horde, (
        _field("count", "数量", "number", min=1, max=80),
        _field("username", "玩家名", "player"),
    ), danger=True),
    _spec("removezombies", "世界", "清除僵尸", "removezombies", "官方没有写参数。会按服务器自己的默认方式清除。", _bare("removezombies"), danger=True),
    _spec("chopper", "世界", "直升机", "chopper", "在一名随机玩家附近触发直升机。", _bare("chopper")),
    _spec("gunshot", "世界", "枪声", "gunshot", "在一名随机玩家附近放一声枪响。", _bare("gunshot")),
    _spec("lightning", "世界", "闪电", "lightning", "落在这名玩家的位置。", _named("lightning"), (
        _field("username", "玩家名", "player"),
    )),
    _spec("thunder", "世界", "雷声", "thunder", "在这名玩家的位置打雷。", _named("thunder"), (
        _field("username", "玩家名", "player"),
    )),
    _spec("settimespeed", "世界", "时间流速", "setTimeSpeed", "数字越大，游戏里的时间过得越快。例子是 10。这不是把时钟拨到几点。", _time_speed, (
        _field("period", "流速", "number", min=0, max=200),
    ), danger=True),
    _spec("startrain", "世界", "开始下雨", "startrain", "强度 1 到 100，留空就用游戏默认。", _rain, (
        _field("intensity", "强度", "number", required=False, min=1, max=100),
    )),
    _spec("stoprain", "世界", "停止下雨", "stoprain", "把雨停掉。", _bare("stoprain")),
    _spec("startstorm", "世界", "开始暴风雨", "startstorm", "时长按游戏内小时。留空就用游戏默认。", _storm, (
        _field("hours", "持续小时", "number", required=False, min=1, max=24),
    )),
    _spec("stopweather", "世界", "停止天气", "stopweather", "把当前天气停掉。", _bare("stopweather")),
)

BY_ID = {spec["id"]: spec for spec in SPECS}


def catalog():
    shown = []
    for spec in SPECS:
        shown.append({
            "id": spec["id"],
            "group": spec["group"],
            "label": spec["label"],
            "official": spec["official"],
            "help": spec["help"],
            "danger": spec["danger"],
            "fields": spec["fields"],
        })
    return shown


def build(command_id, fields):
    spec = BY_ID.get(str(command_id or ""))
    if spec is None:
        raise ValueError("没有这条命令")
    if not isinstance(fields, dict):
        raise ValueError("命令参数不对")
    line, secret = spec["build"](fields)
    return {"line": line, "secret": secret, "danger": spec["danger"], "label": spec["label"]}
