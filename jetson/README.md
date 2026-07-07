# jetson

Jetson 82 (`nvidia@172.0.0.82`) 相关的所有开发资产。三块：

```text
jetson/
  scripts/   与远端通信的入口（ssh / rsync）
  mirror/    远端 ~/qt/ 的同步区
  cockpit/   PC/WSL 上位机（永不部署到 Jetson）
```

## 关系图

```text
        [PC / WSL]                                [Jetson 82  ~/qt/]

        cockpit/  ── HTTP / ROS2 DDS ─────────►   car_web/   (副本, 来自同事)
           │                                      ros2_ws/   (自己写)
           │
        mirror/car_web/  ◄── pull ── rsync ────   car_web/
        mirror/ros2_ws/  ── push ── rsync ─────►  ros2_ws/
```

## 三个组件

| 目录 | 谁的代码 | 主开发在哪 | 同步方向 | 说明 |
|---|---|---|---|---|
| `scripts/jetson.sh` | 本仓库 | PC | — | connect / probe / pull / push / \<remote cmd\> |
| `mirror/car_web/` | 同事 Flask 副本 | 尽量对齐同事版本 | 双向（当前手工） | 相对同事仅端口 + `config/` 差异；不是 fork 分支 |
| `mirror/ros2_ws/` | 自己 | PC (WSL 里 ROS2 Humble) | 本地 → 远端 | WSL 写 → push → Jetson 编译运行 |
| `cockpit/` | 自己 | PC (WSL) | 无 | 控制 / SLAM / 算法；见 [cockpit/README.md](cockpit/README.md) |

## `.env`（不入库，不做示例）

| 文件 | 谁读它 | 内容 |
|---|---|---|
| `scripts/.env` | `scripts/jetson.sh`（ssh/rsync 用） | `HOST` `USER` `PORT` `PASSWORD` `KEY` |
| `cockpit/.env` | cockpit 应用运行时 | `ROS_DOMAIN_ID` `CMD_VEL_TOPIC` `CONTROL_ACTION_TOPIC` 等 |

两份 `.env` 互相独立，不互相读取、不嵌套、不共享变量：

- `scripts/.env` 只给同目录的 `jetson.sh` 用，用来连接 Jetson。
- `cockpit/.env` 只给本地 Qt cockpit 用，用来设置 ROS2 DDS / topic / UI 参数。

单人开发，不留 `.env.example`；缺 key 时按 `jetson.sh` / cockpit 代码里的报错提示补即可。

## 常用命令

本目录的运维入口统一用 **WSL / Git Bash** 执行。不要在 PowerShell 里直接拼
`source ... && colcon ...`、SSH 远端长命令或 ROS2 命令；PowerShell 最多只作为
启动 WSL 的外壳：

```powershell
wsl -d Ubuntu-22.04 -- bash -lc "cd /mnt/d/Downloads/work/ros-dev && bash jetson/scripts/jetson.sh probe"
```

进入 WSL 后推荐直接使用下面这些命令：

```bash
# 探远端环境（只读）
bash jetson/scripts/jetson.sh probe

# 双向同步
bash jetson/scripts/jetson.sh pull car_web        # 远端 ~/qt/car_web → 本地
bash jetson/scripts/jetson.sh push ros2_ws        # 本地 → 远端 (dry-run)
bash jetson/scripts/jetson.sh push ros2_ws --yes  # 真写；默认不带 --delete

# ROS2 干跑控制链路（等价于 push/build/bridge_stack 常用动作）
bash jetson/scripts/jetson.sh ros2 push           # dry-run
bash jetson/scripts/jetson.sh ros2 deploy         # push --yes + Jetson colcon build
bash jetson/scripts/jetson.sh ros2 start
bash jetson/scripts/jetson.sh ros2 status
bash jetson/scripts/jetson.sh ros2 logs
bash jetson/scripts/jetson.sh ros2 stop

# 交互式 ssh / 单条远端命令
bash jetson/scripts/jetson.sh
bash jetson/scripts/jetson.sh 'ros2 topic list'
```

## ROS2 干跑控制链路部署

`mirror/ros2_ws/` 的权威验证环境是 Jetson `~/qt/ros2_ws`。WSL 本机
`colcon build` 只能作为推送前的低成本冒烟检查，不能替代远端验收。

当前第一阶段只验证控制链路：

```text
PC / WSL cockpit
  -> ROS2 /cmd_vel
Jetson ~/qt/ros2_ws
  -> cmd_vel_car_web_bridge
  -> /vehicle/control_action
```

部署和验收顺序：

```bash
# 1. 预览同步内容；只同步 mirror/ros2_ws，不推 cockpit
bash jetson/scripts/jetson.sh ros2 push

# 2. 确认无误后写入 Jetson ~/qt/ros2_ws 并编译
bash jetson/scripts/jetson.sh ros2 deploy

# 3. 启动 / 检查 / 查看日志
bash jetson/scripts/jetson.sh ros2 start
bash jetson/scripts/jetson.sh ros2 status
bash jetson/scripts/jetson.sh ros2 logs
```

如果要先让 Jetson 自己做一次干跑闭环，可执行：

```bash
bash jetson/scripts/jetson.sh ros2 verify
```

真正的跨机验收仍然是：Jetson bridge 保持运行，PC/WSL 启动
`jetson/cockpit`，按键发布 `/cmd_vel`，Jetson 日志或
`/vehicle/control_action` 回显看到：

```text
FORWARD / BACKWARD / TURN_LEFT / TURN_RIGHT / STOP
```

## 行尾 / 编码规范

- 全部走 LF + UTF-8，`.bat` / `.ps1` 例外为 CRLF。
- 靠 `.gitattributes`（git 层）+ `.editorconfig`（编辑器层）双护栏。
- 远端源头本身可能带 CRLF/BOM（Windows 编辑的遗留），已一次性用 python 洗过一次；下次 `pull` 又脏就再洗，不折腾行尾自动化。

## 目录约束

- 远端 `~/newCarProject` 和 `~/ros2_ws` **一根手指都不碰**（那是同事的目标接口）。所有工作都发生在 Jetson `~/qt/` 下。
- `cockpit/` **不推**到 Jetson，任何时候都别 push 它。
- `mirror/` 下的中间产物（`__pycache__` / `.venv` / `log/` / `build/` / `install/`）不入库，见 `.gitignore`。
