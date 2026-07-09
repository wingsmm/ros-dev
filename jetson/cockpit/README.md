# cockpit - PC/VMware Jetson Qt 控制台

`jetson/cockpit/` 是跑在 PC 观测端的 Qt 上位机，不部署到 Jetson。当前 L1/RViz 观测闭环只认 VMware/VM 侧验证；WSL 曾出现 DDS multicast/discovery 问题，不作为阶段一验收路径。

当前阶段：

```text
PC / VMware cockpit Qt
  -> ROS2 /cmd_vel（干跑遥控）
  -> 雷达观测面板：选视图 + 启动本机 RViz2 + topic/Hz/port 状态

Jetson ~/qt/ros2_ws
  -> cmd_vel_car_web_bridge
  -> unitree_lidar_ros2 -> /unilidar/cloud + /unilidar/imu
```

本阶段不调用 `car_web` 电机、不驱动真实运动；雷达可视化走观测端本机 RViz2（当前已在 VM `172.0.0.87` 验证，预置 `config/unilidar.rviz`），不在 Qt 内嵌渲染点云。

## 目录

```text
cockpit/
  app.py                         Qt 入口
  main_window.py                 主窗口
  run.sh                         source ROS2 Humble 后启动 Qt
  .env                           本地运行配置
  requirements.txt               PC/VM 本地 Qt 依赖
  logs/                          本地日志目录
  core/
    config.py                    读取 .env
    logging_config.py            控制台 + 文件日志
    ros2_probe.py                ROS2 DDS 图 / topic 连接性检查
    ros2_control.py              Qt worker：发布 /cmd_vel，订阅动作回显
  ui/
    status_panel.py              连接状态面板
    lidar_panel.py               雷达观测：RViz2 一键启动 + Hz/port
    teleop_panel.py              五键 dead-man 遥控面板
    topic_panel.py               Topic 诊断面板
  config/
    unilidar.rviz                预置基础雷达/odom 视图（Grid + TF + Odometry + Path + PointCloud2）
  scripts/
    start_unilidar_rviz.sh       无 Qt 时一键 RViz2
    stop_unilidar_rviz.sh
    verify_cmd_vel_bridge.sh     WSL 本机冒烟脚本（不替代远端验收）
    cmd_vel_sender.py            CLI 调试：发一次 /cmd_vel
    control_action_echo.py       CLI 调试：监听 /vehicle/control_action
```

## 运行 Qt Cockpit

```bash
cd jetson/cockpit
bash run.sh
```

如果直接执行权限已保留，也可以：

```bash
./run.sh
```

## 配置

本地配置写在 `.env`：

这份 `.env` 只属于 cockpit，不读取 `../.env`，也不配置 Jetson SSH/IP。
Jetson 的部署、编译、启动、停止统一交给 `jetson/scripts/jetson.sh` 读取
同目录的 `jetson/scripts/.env` 处理。

| 变量 | 默认 | 说明 |
|---|---|---|
| `ROS_DOMAIN_ID` | `0` | ROS2 DDS domain |
| `CMD_VEL_TOPIC` | `/cmd_vel` | cockpit 发布的速度 topic |
| `CONTROL_ACTION_TOPIC` | `/vehicle/control_action` | Jetson dry-run bridge 回显 topic |
| `TELEOP_LINEAR_SPEED` | `1.0` | 前进 / 后退线速度值 |
| `TELEOP_ANGULAR_SPEED` | `1.0` | 左转 / 右转角速度值 |
| `TELEOP_REPEAT_HZ` | `10` | 按住运动时重发频率 |
| `TELEOP_ENABLE_KEYBOARD` | `1` | 是否启用键盘遥控 |
| `JETSON_COCKPIT_LOG_DIR` | `logs` | 本地日志目录 |
| `JETSON_COCKPIT_LOG_LEVEL` | `INFO` | 日志等级 |
| `LIDAR_CLOUD_TOPIC` | `/unilidar/cloud` | 雷达点云 topic |
| `LIDAR_IMU_TOPIC` | `/unilidar/imu` | 雷达 IMU topic |
| `LIDAR_FIXED_FRAME` | `odom` | RViz Fixed Frame |
| `LIDAR_RVIZ_CONFIG` | `config/unilidar.rviz` | RViz2 配置 |

日志文件写入：

```text
logs/jetson-cockpit-YYYY-MM-DD.log
```

## 雷达观测（L1 原始点云）

L1 对接的主入口文档是 [../docs/宇树L1对接方案.md](../docs/宇树L1对接方案.md)。本节只说明 cockpit / 观测端怎么打开 RViz 和怎么判断 DDS 是否通。当前 L1/RViz 验证只认 VMware/VM 观测端。

阶段一只看官方原始点云：

```text
Jetson unitree_lidar_ros2 -> /unilidar/cloud + /unilidar/imu
VMware rviz2              -> Fixed Frame=unilidar_lidar
```

Qt cockpit 不是必须链路；它只是本地启动 RViz 和显示诊断状态的壳。要排查时，可以直接在 VM 里跑 `rviz2 -d config/unilidar.rviz`。

**方式 A：cockpit 内一键**

```bash
cd jetson/cockpit
bash run.sh
```

雷达观测面板：

- 选择 **雷达/里程计** → `config/unilidar_mapping.rviz`
- 选择 **原始点云** → `config/unilidar.rviz`（阶段一应使用 `Fixed Frame=unilidar_lidar`）
- **启动 RViz (观测端本地)** / **停止 RViz**
- 一行摘要；需要时再展开 **高级诊断** → 刷新

**方式 B：仅脚本（无 Qt）**

```bash
cd jetson/cockpit
export ROS_DOMAIN_ID=0
bash scripts/start_unilidar_rviz.sh
# 关闭：bash scripts/stop_unilidar_rviz.sh
```

也可以完全绕过 Qt：

```bash
cd /mnt/d/Downloads/work/ros-dev/jetson/cockpit
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
ros2 topic list
timeout 12 ros2 topic hz /unilidar/cloud
rviz2 -d config/unilidar.rviz
```

验收：VMware/VM 观测端 `ros2 topic list` 能看到 `/unilidar/cloud`，`/unilidar/cloud` 接近 9Hz，`/unilidar/imu` 高频；RViz 不手动 Add Display 即可看到点云，遮挡雷达有变化。

### 阶段一验收状态（2026-07-09）

阶段一已通过。Jetson 侧 L1 正常：

```text
/dev/unilidar_lidar -> ttyCH341USB0
/unilidar/cloud publisher=unitree_lidar_ros2_node, ~8.76Hz
/unilidar/imu ~246Hz
Jetson ROS_DOMAIN_ID=0, ROS_LOCALHOST_ONLY=0
```

VM `172.0.0.87` 作为观测端已完成闭环：

```text
可见 /unilidar/cloud 和 /unilidar/imu
/unilidar/cloud ~8.8Hz
/unilidar/imu ~246Hz
RViz: config/unilidar.rviz
Fixed Frame: unilidar_lidar
PointCloud2: /unilidar/cloud
RViz 目视点云已确认
```

WSL 侧曾出现 DDS 发现问题，因此不作为阶段一验收路径：

```text
WSL eth1=172.0.0.52/24
Jetson=172.0.0.82
ip route get 172.0.0.82 -> dev eth1 src 172.0.0.52
ros2 topic list -> only /parameter_events, /rosout
```

`ros2 multicast` 双向测试也未收到：

```text
WSL ros2 multicast send    -> Jetson receive: not received
Jetson ros2 multicast send -> WSL receive: not received
```

因此 WSL 问题不是 L1 硬件、串口、SSH、colcon 或 RViz 配置问题，而是 Windows/WSL 与 Jetson 之间的 ROS2 DDS discovery/multicast 环境问题。它不作为阶段一阻塞项；`jetson/cockpit` 的 L1/RViz 现阶段只在 VMware/VM 观测端验证。后续若要让 cockpit 在 WSL 里稳定一键看点云，再单独恢复 multicast 或改用 FastDDS Discovery Server。

### L1 安装方向（卧放）与坐标轴对齐（重要）

宇树 L1 的坐标系定义以官方文档为准（示意图/说明见 [L1 Overview & Use](https://support.unitree.com/home/zh/L1_SDK/L1_Overview_Use)）。

如果 L1 **卧放**安装，实车上常见现象是：在 RViz 里看 `unilidar_lidar` 的三色轴时，
**蓝色 Z 轴**可能指向车头（“Z 轴超前”）。这会导致点云/障碍的“前后左右”与车体直觉不一致。

**不要靠猜**，用 RViz 直接确认：

- Fixed Frame 临时设为 `unilidar_lidar`
- 打开 `Axes_lidar`（`unilidar.rviz` 已包含），观察车头方向对应 `X(红)/Y(绿)/Z(蓝)` 哪根轴

处理原则（避免乱改）：

- **阶段 2（只看原始点云）**：优先用 `Fixed Frame=unilidar_lidar`，不依赖 `odom/base_link` TF，先把点云“能看见”跑通。
- **阶段 2.5（雷达/里程计联动）**：当你需要 `Fixed Frame=odom`（点云跟随 `/odom` 移动）时，必须保证 TF 链完整：
  `odom -> base_link -> unilidar_lidar`。
  若确认存在“Z 轴超前”，应只在 **静态 TF**（`base_link -> unilidar_lidar`）里加旋转，把雷达前方轴对齐到 `base_link` 的 **X** 轴；
  不要改 topic 名称、不要改驱动发布逻辑。

### LIO / 里程计观测（阶段 2.5，对齐 vmware 雷达/里程计）

Jetson 端完整移动观测栈由 `ros2 start` 统一拉起：

```bash
bash jetson/scripts/jetson.sh ros2 deploy   # 首次或改代码后
bash jetson/scripts/jetson.sh ros2 start
```

cockpit 选择 **「雷达/里程计」**，再点 **「启动 RViz (WSL 本地)」**，加载 `config/unilidar_mapping.rviz`：

```text
Fixed Frame: odom
Odometry: /odom
Path: /path
PointCloud2: /cloud_registered
TF: odom -> base_link -> unilidar_lidar
Grid
```

这里的 `/odom` 由 Jetson 侧 `lio_odom_adapter` 从 Point-LIO 的
`/aft_mapped_to_init` 适配而来。底盘不可用时，真实移动观测来自 L1 点云 + L1 内置 IMU，不用 `/cmd_vel` 伪造 odom。
静止验收：`/path` 不乱飞，`/odom`/配准点云有输出。再手动慢速搬车看 path 是否连续。

## 遥控模式

遥控面板参考 `vmware/qt` 的基础遥控模式，保持同一套按键语义：

- 按住运动、松开停止。
- 运动期间约 10Hz 重发当前 `/cmd_vel`。
- 左 / 右是原地转向。
- 窗口失焦、隐藏、关闭时发送停止。
- `K` / `Space` 为停止。

| 动作 | 鼠标按钮 | 键盘 | `/cmd_vel` |
|---|---|---|---|
| 前进 | 前进 | `W` / `I` / `↑` | `linear.x = 1.0`, `angular.z = 0.0` |
| 后退 | 后退 | `S` / `↓` | `linear.x = -1.0`, `angular.z = 0.0` |
| 左转 | 左转 | `A` / `Q` / `J` / `←` | `linear.x = 0.0`, `angular.z = 1.0` |
| 右转 | 右转 | `D` / `E` / `L` / `→` | `linear.x = 0.0`, `angular.z = -1.0` |
| 停止 | 停止 | `K` / `Space` | `linear.x = 0.0`, `angular.z = 0.0` |

Jetson 侧 dry-run bridge 会把 `/cmd_vel` 转译为：

```text
FORWARD / BACKWARD / TURN_LEFT / TURN_RIGHT / STOP
```

并发布：

```text
/vehicle/control_action  std_msgs/String
```

## 连接性检查

界面参考 `vmware/qt` 的「环境状态 / Topic 诊断」，但 ROS2 没有 ROS1 Master，
所以这里检查的是 DDS graph：

- 「刷新状态」：查询 `ros2 node list`，并检查关键 topic。
- 「检查环境」：显示 `ROS_DOMAIN_ID`、`ros2`、`rclpy`、node list、topic list。
- 「检查关键 topic」：
  - `/cmd_vel` 应该有 subscriber，表示 Jetson 侧 dry-run bridge 正在订阅。
  - `/vehicle/control_action` 应该有 publisher，表示 Jetson 侧 dry-run bridge 正在回显动作。

注意：远端能力仍只在 `jetson/mirror/ros2_ws` 里实现，当前只有
`/cmd_vel -> FORWARD/BACKWARD/TURN_LEFT/TURN_RIGHT/STOP` 的简单转译。
cockpit 只做本地 Qt 控制台、DDS 连接性观察和调试入口。

## CLI 调试工具

CLI 只是 smoke test，不是 cockpit 主入口：

```bash
cd jetson/cockpit
source /opt/ros/humble/setup.bash

python3 scripts/cmd_vel_sender.py forward
python3 scripts/cmd_vel_sender.py backward
python3 scripts/cmd_vel_sender.py left
python3 scripts/cmd_vel_sender.py right
python3 scripts/cmd_vel_sender.py stop

python3 scripts/control_action_echo.py
```

## 验收边界

`cockpit/` 只运行在 PC/WSL，不部署到 Jetson。雷达驱动编译与 topic 验证**只认远端 Jetson**；本机 WSL 不做 `mirror/ros2_ws` 的 `colcon build` 作为雷达验收依据。

### 改哪里要部署

| 改动位置 | 要不要上 82 | 怎么生效 |
|----------|-------------|----------|
| 只改 `jetson/cockpit/`（`.rviz`、Qt 面板、`scripts/*.sh`） | **不用** | `cd jetson/cockpit && bash run.sh`，重开 RViz |
| 改 `jetson/mirror/ros2_ws/`（yaml、脚本、ROS2 包） | **要 deploy** | `jetson.sh ros2 deploy` → `jetson.sh ros2 restart` |
| 只想重启 LIO 层调试 | 不改代码时不用 build | `jetson.sh ros2 lio-stop` → `jetson.sh ros2 lio-start` |

```bash
bash jetson/scripts/jetson.sh ros2 deploy
bash jetson/scripts/jetson.sh ros2 restart
```

### 控制链路（干跑）

```text
PC / VMware cockpit -> /cmd_vel
Jetson ~/qt/ros2_ws -> cmd_vel_car_web_bridge -> /vehicle/control_action
```

验收：cockpit 发五向指令，Jetson 日志或 `/vehicle/control_action` 回显
`FORWARD / BACKWARD / TURN_LEFT / TURN_RIGHT / STOP`。

部署：`bash jetson/scripts/jetson.sh ros2 deploy` + `ros2 start`。

### 雷达观测（L1 原始点云）

```text
Jetson 82 -> /unilidar/cloud + /unilidar/imu
VMware/VM -> cockpit 雷达面板 / rviz2（config/unilidar.rviz）
```

验收：

1. 观测端 `ros2 topic list` 能看到 `/unilidar/cloud` 和 `/unilidar/imu`。
2. cockpit 选择「原始点云」后点「启动 RViz (观测端本地)」（或 `scripts/start_unilidar_rviz.sh`），无需手配 Display。
2. RViz 点云可见，遮挡雷达有变化；左侧 Displays 无红色异常项。
3. 面板或 CLI：cloud ~9Hz、imu 高频。

`/odom`、`/odom_path`、`/cloud_registered`、TF 链完整性属于后续 LIO / TF 阶段，不作为 L1 原始点云阶段的验收条件。观测端可用 `ros2 topic hz /unilidar/cloud` 辅助确认；最终以 Jetson 侧频率、观测端 topic discovery、RViz 目视三者共同为准。

## 本机冒烟（仅控制 bridge 包）

复杂 ROS2 命令不要在 PowerShell 里拼一行；按 `remote/` 的约定，放进 WSL
脚本执行。本脚本只用于推远端前快速发现明显问题：

```powershell
wsl -d Ubuntu-22.04 -- bash /mnt/d/Downloads/work/ros-dev/jetson/cockpit/scripts/verify_cmd_vel_bridge.sh
```

预期最后一行：

```text
VERIFY_CMD_VEL_BRIDGE_OK
```

如果本机冒烟通过，只说明 bridge 包语法/本机 DDS 基本可用；跨机控制与雷达观测仍以远端 Jetson + WSL RViz 为准。

## 当前边界

不要在本阶段做这些事：

- 不调用 `car_web` HTTP API。
- 不引入 `requests` 做控制。
- 不碰前轮、扒手、升降、调平或串口电机代码。
- 不做导航、SLAM、自动避障。
- 不把 cockpit 部署到 Jetson。

Jetson 侧 ROS2 包在：

```text
jetson/mirror/ros2_ws/src/cmd_vel_car_web_bridge/
```
