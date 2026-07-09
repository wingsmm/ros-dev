# jetson

Jetson（`scripts/.env` 里的 `HOST`，当前多为 `172.0.0.82`）相关开发资产。三块：

```text
jetson/
  scripts/   与远端通信的入口（ssh / rsync）
  mirror/    远端 ~/qt/ 的同步区
  cockpit/   PC/VMware 上位机（永不部署到 Jetson）
```

> **2026-07-08 回退说明**：自研「雷达整链」（bridge + unilidar_stack + Point-LIO + adapter）方向做错，已撤出工作区。  
> - 远端 `~/qt/ros2_ws` 已恢复为从 `~/ros2_ws` 拷回的**原版**（仅官方/同事侧包，**无** `scripts/`）。  
> - 本地改过的完整链路已迁到仓库根 `other/ros2_ws/`（`.gitignore` 忽略，不入库）。  
> - `jetson/mirror/ros2_ws` 已 `pull` 对齐远端原版。  
> 日常不要再把 `jetson.sh ros2 start` 当成完整观测栈入口（远端已无 `scripts/ros2_stack.sh`）。

## 关系图

```text
        [PC / VMware]                            [Jetson  ~/qt/]

        cockpit/  ── HTTP / ROS2 DDS ─────────►   car_web/   (副本, 来自同事)
           │                                      ros2_ws/   (当前=原版镜像)
           │
        mirror/car_web/  ◄── pull ── rsync ────   car_web/
        mirror/ros2_ws/  ◄── pull / push ─────►  ros2_ws/
```

## 三个组件

| 目录 | 谁的代码 | 主开发在哪 | 同步方向 | 说明 |
|---|---|---|---|---|
| `scripts/jetson.sh` | 本仓库 | PC | — | connect / probe / pull / push / \<remote cmd\> |
| `mirror/car_web/` | 同事 Flask 副本 | 尽量对齐同事版本 | 双向（当前手工） | 相对同事仅端口 + `config/` 差异；不是 fork 分支 |
| `mirror/ros2_ws/` | 原版（unitree / point_lio / 示例包） | 以远端为准 | **先 pull 对齐**；改代码后再 push | 自研整链不在此目录，见 `other/ros2_ws` |
| `cockpit/` | 自己 | PC / VMware | 无 | 控制 / SLAM / 算法；L1/RViz 当前只认 VMware 观测端验证，见 [cockpit/README.md](cockpit/README.md) |

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

# 同步
bash jetson/scripts/jetson.sh pull car_web        # 远端 ~/qt/car_web → 本地
bash jetson/scripts/jetson.sh pull ros2_ws        # 远端原版 → mirror（先对齐）
bash jetson/scripts/jetson.sh push ros2_ws        # dry-run
bash jetson/scripts/jetson.sh push ros2_ws --yes  # 真写；默认不带 --delete

# 交互式 ssh / 单条远端命令
bash jetson/scripts/jetson.sh
bash jetson/scripts/jetson.sh 'ros2 topic list'
```

## ROS2 / L1 现状（2026-07-08 回退后）

`mirror/ros2_ws/src/` 当前只有原版包：

```text
my_motor_ctrl / my_py_pkg          # 示例
unitree_lidar_ros2 / unitree_lidar_sdk
point_lio_ros2                     # 官方 Point-LIO（有则用官方 launch，勿自造整栈）
```

自研整链（`ros2_stack.sh`、`cmd_vel_car_web_bridge`、`lio_odom_adapter` 等）在 `other/ros2_ws/`，**不是**当前 `mirror` 入口。

雷达第一阶段建议按[宇树官方文档](https://support.unitree.com/home/zh/L1_SDK/L1_Use_unilidar_ros2)在 Jetson 上直接 `ros2 launch` 官方包，本仓库只做同步与观测，不再维护自造 `ros2 start` 全栈。

相关问题排查笔记（**参考用，非日常入口**）：[docs/l1-lio-drift-triage-task.md](docs/l1-lio-drift-triage-task.md)。

## Unitree L1 最小观测：Jetson 采点云 + VMware RViz2

```text
Jetson (~/qt/ros2_ws) 跑官方 unitree_lidar_ros2
  -> /unilidar/cloud  /unilidar/imu
VMware/PC rviz2
  -> Fixed Frame=unilidar_lidar，PointCloud2=/unilidar/cloud
```

2026-07-09 阶段一已通过：Jetson 侧 `/unilidar/cloud` 约 8.76 Hz、`/unilidar/imu` 约 246 Hz；VM `172.0.0.87` 作为观测端已看到 topic、Hz 和 RViz 点云。WSL 曾出现 DDS multicast/discovery 问题，不作为 L1 阶段一验收路径；后续 cockpit 体验若要回到 WSL，再单独修 WSL/Windows DDS。

### 固定串口别名（推荐）：`/dev/unilidar_lidar`

USB 串口名（`/dev/ttyUSB*` / `ttyCH341USB*`）可能因重启/拔插/插口变更而漂移。建议用 udev 生成稳定别名 `/dev/unilidar_lidar`，并在 launch 参数里使用该路径。

在 Jetson 上执行（需要 sudo）：

```bash
sudo -v

sudo tee /etc/udev/rules.d/99-unilidar.rules >/dev/null <<'EOF'
# Unitree L1 (CH340) stable symlink
# Bound to physical USB path 1-2.4 (ttyCH341USB0 as of 2026-07-08)
SUBSYSTEM=="tty", KERNEL=="ttyCH341USB*", KERNELS=="1-2.4", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="unilidar_lidar", GROUP="dialout", MODE="0660"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
sleep 1
ls -la /dev/unilidar_lidar
```

说明：

- 该规则按 **CH340/CH341 (1a86:7523)** + **物理 USB 口路径 `KERNELS=="1-2.4"`** 绑定。若换插口，需要用 `udevadm info -a -n /dev/ttyCH341USBx` 重新确认对应的 `KERNELS=="1-2.X"`。

卧放安装时坐标轴可能与「竖直装」文档不一致（例如 Z 朝前），见 [cockpit/README.md](cockpit/README.md) 相关节。

## 行尾 / 编码规范

- 全部走 LF + UTF-8，`.bat` / `.ps1` 例外为 CRLF。
- 靠 `.gitattributes`（git 层）+ `.editorconfig`（编辑器层）双护栏。
- 远端源头本身可能带 CRLF/BOM（Windows 编辑的遗留），已一次性用 python 洗过一次；下次 `pull` 又脏就再洗，不折腾行尾自动化。

## 目录约束

- 远端 `~/newCarProject` 和 `~/ros2_ws` **一根手指都不碰**（那是同事的目标接口）。所有工作都发生在 Jetson `~/qt/` 下。
- `cockpit/` **不推**到 Jetson，任何时候都别 push 它。
- `mirror/` 下的中间产物（`__pycache__` / `.venv` / `log/` / `build/` / `install/`）不入库，见 `.gitignore`。
