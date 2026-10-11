# 岗亭

仓库名用 `gangting`。只给家里这一台官方专用服务器的管理员用。网页把进程、玩家、存档坐标和官方控制台命令做成可以点的后台。不安装模组，也不往游戏目录里放脚本。

## 在小主机上跑

```bash
sudo mkdir -p /opt/zomboid-home-panel
sudo cp -r panel.py host.py rcon.py parse.py static /opt/zomboid-home-panel/
sudo cp config.example.json /opt/zomboid-home-panel/config.json
sudo chown -R xinzhi:xinzhi /opt/zomboid-home-panel
```

编辑 `config.json`：面板密码至少 8 位，`rconPassword` 用 `servertest.ini` 里的 `RCONPassword`。不要把 `config.json` 提交到仓库。

让运行面板的用户可以开关这一台服务，并且能读日志：

```bash
sudo usermod -aG systemd-journal xinzhi
```

`/etc/sudoers.d/pz-home-panel`：

```
xinzhi ALL=(root) NOPASSWD: /bin/systemctl start pzserver.service, /bin/systemctl stop pzserver.service, /bin/systemctl restart pzserver.service, /bin/systemctl show pzserver.service *
```

```bash
python3 /opt/zomboid-home-panel/panel.py
```

浏览器打开 `http://192.168.124.77:3010`。这个端口只在家里用，不要做到路由器的公网转发。

小主机上的这一份跑在 `/home/zomboid/home-panel`，用 `zomboid` 这个用户读配置和日志。游戏进程没有被重启。

本机演示不连接游戏服：`python panel.py --demo`，密码是 `demo-home`。演示页会标明样本数据。

桌面上的工作副本就是这个目录。同步到小主机时，不要覆盖 `/home/zomboid/home-panel/config.json`。地图上的玩家和车辆来自存档里的上次坐标，不是人正在走动的那一帧。
