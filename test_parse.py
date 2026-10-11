import unittest

from parse import cpu_percent, cpu_sample, format_uptime, memory_bytes, parse_ini, parse_players, parse_systemctl_show, public_config, quote_arg


INI = """
# comment
PublicName=萌新生存服
Map=Muldraugh, KY
Mods=B42Trans_CN;B42ModTrans_CN
WorkshopItems=3556544454;3556540080
DefaultPort=16261
UDPPort=16262
MaxPlayers=16
Open=true
Public=true
Password=
RCONPassword=secret-value
"""


class ParseTests(unittest.TestCase):
    def test_public_config_hides_rcon_password(self):
        shown = public_config(parse_ini(INI))
        self.assertEqual(shown["publicName"], "萌新生存服")
        self.assertEqual(shown["mods"][0]["workshop"], "3556544454")
        self.assertNotIn("secret-value", str(shown))
        self.assertFalse(shown["hasPassword"])
        self.assertEqual(shown["rules"][-1], {"label": "进服密码", "value": "没有"})
        self.assertNotIn("玩家对战", [item["label"] for item in shown["rules"]])

    def test_visits_and_chat_keep_the_clock_and_name(self):
        from parse import parse_chat, parse_visits, quiet_lines
        visits = parse_visits([
            '[11-10-26 15:22:44.121] event="receive-packet" message="client-connect" username="xiaoxin" connection-type="Steam".',
            '[11-10-26 15:24:16.802] event="fully-connected" message="" username="xiaoxin" connection-type="Steam".',
            '[11-10-26 15:38:21.161] event="RakNet" message="connection-lost" username="xiaoxin" connection-type="Disconnected".',
            '[11-10-26 15:38:21.181] event="disconnect" message="receive-disconnect" username="xiaoxin" connection-type="Disconnected".',
        ])
        self.assertEqual([(item["name"], item["action"]) for item in visits], [
            ("xiaoxin", "进来了"),
            ("xiaoxin", "离开了"),
        ])
        chat = parse_chat(['[11-10-26 21:16:02.1] General: 林夏: 我到镇口了'])
        self.assertIn("镇口", chat[0]["text"])
        quiet = quiet_lines(["SERVER STARTED", "ItemPickInfo -> skip", "RCON listening"])
        self.assertEqual(quiet, ["SERVER STARTED", "RCON listening"])

    def test_online_player_without_a_save_is_listed_without_coordinates(self):
        from parse import mark_online
        marked = mark_online(
            [{"name": "xiaoxin", "x": 10600, "y": 9700, "z": 0}],
            ["xiaoxin", "林夏"],
        )
        self.assertTrue(marked[0]["online"])
        self.assertEqual(marked[0]["name"], "xiaoxin")
        self.assertIsNone(marked[1]["x"])
        self.assertEqual(marked[1]["name"], "林夏")

    def test_players_keep_the_character_after_the_dash(self):
        text = "Players connected (1):\n-阿宁\n"
        self.assertEqual(parse_players(text), ["阿宁"])
        self.assertEqual(parse_players("- 阿宁"), [" 阿宁"])

    def test_systemctl_monotonic_clock_is_kept(self):
        text = "ActiveState=active\nSubState=running\nActiveEnterTimestampMonotonic=910000000\nMainPID=12\n"
        status = parse_systemctl_show(text)
        self.assertTrue(status["running"])
        self.assertEqual(status["monotonicUsec"], 910000000)

    def test_inactive_unit_has_no_start(self):
        status = parse_systemctl_show("ActiveState=inactive\nActiveEnterTimestampMonotonic=0\n")
        self.assertFalse(status["running"])
        self.assertEqual(status["monotonicUsec"], 0)

    def test_uptime_uses_the_boot_clock(self):
        from parse import uptime_from_monotonic
        self.assertEqual(int(uptime_from_monotonic(910_000_000, 1000)), 90)
        self.assertEqual(uptime_from_monotonic(0, 1000), 0)

    def test_uptime_matches_the_day_hour_minute_reading(self):
        self.assertEqual(format_uptime(1 * 86400 + 10 * 3600 + 16 * 60), "1 天 10 小时 16 分钟")
        self.assertEqual(format_uptime(30), "不到 1 分钟")

    def test_quote_rejects_broken_quotes(self):
        with self.assertRaises(ValueError):
            quote_arg('say "hi"', "消息")
        self.assertEqual(quote_arg("今晚重启", "消息"), "今晚重启")
        self.assertEqual(quote_arg("a" * 80, "密码", 80), "a" * 80)


class CommandTests(unittest.TestCase):
    def test_catalog_covers_the_console_and_hides_builders(self):
        from commands import build, catalog
        shown = catalog()
        self.assertGreater(len(shown), 40)
        self.assertIn("kickuser", [item["official"] for item in shown])
        self.assertNotIn("build", shown[0])

    def test_kick_and_password_commands_are_built_not_echoed(self):
        from commands import build
        kicked = build("kickuser", {"username": "xiaoxin", "reason": "挂机"})
        self.assertEqual(kicked["line"], 'kickuser "xiaoxin" -r "挂机"')
        self.assertFalse(kicked["secret"])
        access = build("setaccesslevel", {"username": "xiaoxin", "level": "moderator"})
        self.assertEqual(access["line"], 'setaccesslevel "xiaoxin" "moderator"')
        player = build("setaccesslevel", {"username": "xiaoxin", "level": "user"})
        self.assertEqual(player["line"], 'setaccesslevel "xiaoxin" "user"')
        with self.assertRaises(ValueError):
            build("setaccesslevel", {"username": "xiaoxin", "level": "none"})
        with self.assertRaises(ValueError):
            build("teleportspot", {"username": "xiaoxin", "coords": "10646,9654,0"})
        moved = build("teleportplayer", {"username": "xiaoxin", "target": "林夏"})
        self.assertEqual(moved["line"], 'teleportplayer "xiaoxin" "林夏"')
        speed = build("settimespeed", {"period": "10"})
        self.assertEqual(speed["line"], "setTimeSpeed 10")
        hidden = build("setpassword", {"username": "xiaoxin", "password": "new-pass"})
        self.assertTrue(hidden["secret"])
        self.assertIn("new-pass", hidden["line"])
        with self.assertRaises(ValueError):
            build("createhorde", {"count": "500", "username": "xiaoxin"})
        with self.assertRaises(ValueError):
            build("kickuser", {"username": 'a"b'})


class VehicleTests(unittest.TestCase):
    def test_vehicle_rows_stay_inside_the_window_and_skip_the_blob(self):
        import sqlite3
        import tempfile
        from pathlib import Path

        from host import vehicle_rows

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "vehicles.db"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE vehicles (id INTEGER PRIMARY KEY, wx INTEGER, wy INTEGER, x FLOAT, y FLOAT, data BLOB)"
            )
            connection.execute("INSERT INTO vehicles (wx, wy, x, y, data) VALUES (1, 1, 10620, 9730, ?)", (b"secret-blob",))
            connection.execute("INSERT INTO vehicles (wx, wy, x, y, data) VALUES (2, 2, 20000, 20000, ?)", (b"far",))
            connection.commit()
            connection.close()
            rows, capped = vehicle_rows(database, (10600, 10700, 9700, 9800))
        self.assertFalse(capped)
        self.assertEqual(rows, [{"id": 1, "x": 10620, "y": 9730}])
        self.assertNotIn("data", rows[0])


class SandboxTests(unittest.TestCase):
    def test_sandbox_keeps_untouched_lines_and_patches_one_value(self):
        from sandbox import apply_sandbox, parse_sandbox

        original = "\n".join([
            "SandboxVars = {",
            "    VERSION = 6,",
            "    -- 1 = Insane",
            "    -- 4 = Normal",
            "    Zombies = 4,",
            "    ZombieLore = {",
            "        Speed = 2,",
            "    },",
            "}",
            "",
        ])
        fields = {item["path"]: item for item in parse_sandbox(original)}
        self.assertEqual(fields["Zombies"]["options"][0]["label"], "Insane")
        self.assertEqual(fields["ZombieLore.Speed"]["value"], 2)
        rewritten, changed = apply_sandbox(original, {"Zombies": "1", "ZombieLore.Speed": "2"})
        self.assertEqual(changed, ["Zombies"])
        self.assertIn("    Zombies = 1,", rewritten)
        self.assertIn("        Speed = 2,", rewritten)
        self.assertIn("    -- 4 = Normal", rewritten)
        with self.assertRaises(ValueError):
            apply_sandbox(original, {"VERSION": "7"})


class UsageTests(unittest.TestCase):
    def test_cpu_and_memory(self):
        self.assertEqual(cpu_percent((100, 80), (200, 100)), 80.0)
        self.assertIsNone(cpu_percent((10, 10), (10, 10)))
        sample = cpu_sample("cpu  10 0 20 60 10 0 0 0\ncpu0 1 0 0 1 0 0 0 0\n")
        self.assertEqual(sample, (100, 70))
        used, total = memory_bytes("MemTotal: 8000000 kB\nMemAvailable: 2000000 kB\n")
        self.assertEqual(total, 8000000 * 1024)
        self.assertEqual(used, 6000000 * 1024)


class FileTests(unittest.TestCase):
    def test_backup_copies_the_save_directory(self):
        import tempfile
        from pathlib import Path
        import host

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            ini = root / "Zomboid" / "Server" / "servertest.ini"
            ini.parent.mkdir(parents=True)
            ini.write_text("PublicName=x\n", encoding="utf-8")
            save = root / "Zomboid" / "Saves" / "Multiplayer" / "servertest"
            save.mkdir(parents=True)
            (save / "players.db").write_bytes(b"db")
            config = {"iniPath": str(ini), "logPath": str(root / "Zomboid" / "server-console.txt")}
            listed = host.server_files(config)
            self.assertTrue(any(row["label"] == "存档" and row["exists"] for row in listed["files"]))
            self.assertNotIn("RCONPassword", str(listed))
            name = host.backup_world(config)
            copied = root / "Zomboid" / "backups" / name / "players.db"
            self.assertEqual(copied.read_bytes(), b"db")
            self.assertIn(name, host.server_files(config)["backups"])


if __name__ == "__main__":
    unittest.main()
