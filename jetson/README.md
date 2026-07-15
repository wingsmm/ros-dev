# jetson

Jetson（`scripts/.env` 里的 `HOST`，当前多为 `172.0.0.82`）相关开发资产。三块：

```text
jetson/
  scripts/   与远端通信的入口（ssh / rsync）
  mirror/    远端 ~/qt/ 的同步区
  cockpit/   PC/VMware 上位机（永不部署到 Jetson）
```

> **产品状态：二代 ROS2 当前开发主线。** Unitree L1、点云对齐、Point-LIO、`lio_odom_adapter` 和 cockpit 一键定位已经形成短距离观测闭环。当前卡点是底盘改进，不是雷达、DDS 或 RViz；底盘恢复正常行走后再做 3～5 米验收、台阶识别与相机互补。

## 关系图

```text
        [PC / VMware]                            [Jetson  ~/qt/]

        cockpit/  ── SSH / ROS2 DDS ──────────►   car_web/   (副本, 来自同事)
           │                                      ros2_ws/   (L1 / LIO / adapter)
           │
        mirror/car_web/  ◄── pull ── rsync ────   car_web/
        mirror/ros2_ws/  ◄── pull / push ─────►  ros2_ws/
```

## 三个组件

| 目录 | 谁的代码 | 主开发在哪 | 同步方向 | 说明 |
|---|---|---|---|---|
| `scripts/jetson.sh` | 本仓库 | PC | — | connect / probe / pull / push / \<remote cmd\> |
| `mirror/car_web/` | 同事 Flask 副本 | 尽量对齐同事版本 | 双向（当前手工） | 相对同事仅端口 + `config/` 差异；不是 fork 分支 |
| `mirror/ros2_ws/` | 官方包 + 本项目 L1/LIO 适配 | 本仓库 | 改代码后 push / build | Unitree L1、Point-LIO、TF、cloud align、odom adapter 与运行脚本 |
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

本目录的仓库脚本从 Git Bash 或其他兼容 Bash 环境执行。项目运行、构建、DDS、RViz 和验收只认 Jetson 与 VMware 目标机。复杂远端 ROS2 命令应固化在仓库脚本中，不在 PowerShell 里临时拼接。

```bash
# 探远端环境（只读）
bash jetson/scripts/jetson.sh probe

# 同步
bash jetson/scripts/jetson.sh pull car_web        # 远端 ~/qt/car_web → 本地
bash jetson/scripts/jetson.sh pull ros2_ws        # 远端原版 → mirror（先对齐）
# 同步 ros2_ws（含 l1_static_tf.sh、l1_tf_bringup 等）
bash jetson/scripts/jetson.sh ros2 push        # dry-run
bash jetson/scripts/jetson.sh ros2 push --yes  # 真写；默认不带 --delete

# 交互式 ssh / 单条远端命令
bash jetson/scripts/jetson.sh
bash jetson/scripts/jetson.sh 'ros2 topic list'
```

## ROS2 / L1 现状（2026-07-14）

当前定位观测链路：

```text
unitree_lidar_ros2
  -> /unilidar/cloud + /unilidar/imu
  -> Point-LIO
  -> /aft_mapped_to_init + /cloud_registered
  -> lio_odom_adapter
  -> /odom + /odom_path + TF odom->base_link
  -> VMware cockpit / RViz
```

已确认：

- L1 原始点云和内置 IMU 正常发布。
- 点云卧放基准、车体对齐和现场 trim 已接入 cockpit。
- Point-LIO、`/odom`、`/odom_path` 和 `odom->base_link` 已在 Jetson/VMware 验证有数据。
- 约 35 cm 人工搬运时，物理位移可在 RViz 连续显示，估计位移约 34.9 cm。
- 该结果只证明短距离定位观测闭环，不代表导航级精度、回环或自主导航已经完成。

当前等待底盘改进。底盘能够稳定行走后，先完成 3～5 米直行、往返、转向和漂移验收，再进入台阶识别与相机互补。权威阶段说明见 [docs/宇树L1对接方案.md](docs/宇树L1对接方案.md)。历史 LIO 排障记录位于 `docs/archive/`，不是日常操作入口。

## Unitree L1 最小观测：Jetson 采点云 + VMware RViz2

```text
Jetson (~/qt/ros2_ws) 跑官方 unitree_lidar_ros2
  -> /unilidar/cloud  /unilidar/imu
VMware/PC rviz2
  -> Fixed Frame=unilidar_lidar，PointCloud2=/unilidar/cloud
```

2026-07-09 阶段一已通过：Jetson 侧 `/unilidar/cloud` 约 8.76 Hz、`/unilidar/imu` 约 246 Hz；VMware 观测端已看到 topic、Hz 和 RViz 点云。VMware 是当前 cockpit/RViz 唯一支持的观测环境。

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
