# cockpit - PC/WSL Jetson Qt 控制台

`jetson/cockpit/` 是跑在 PC/WSL 上的 Qt 上位机，不部署到 Jetson。

当前阶段只做一条干跑控制链路：

```text
PC / WSL cockpit Qt
  -> ROS2 /cmd_vel
Jetson ~/qt/ros2_ws
  -> cmd_vel_car_web_bridge
  -> /vehicle/control_action
```

本阶段不调用 `car_web`，不碰串口电机代码，不驱动真实硬件；只验证
`cockpit -> ROS2 DDS -> Jetson ros2_ws -> 动作转译`。

## 目录

```text
cockpit/
  app.py                         Qt 入口
  main_window.py                 主窗口
  run.sh                         source ROS2 Humble 后启动 Qt
  .env                           本地运行配置
  requirements.txt               PC/WSL 本地 Qt 依赖
  logs/                          本地日志目录
  core/
    config.py                    读取 .env
    logging_config.py            控制台 + 文件日志
    ros2_probe.py                ROS2 DDS 图 / topic 连接性检查
    ros2_control.py              Qt worker：发布 /cmd_vel，订阅动作回显
  ui/
    status_panel.py              连接状态面板
    teleop_panel.py              五键 dead-man 遥控面板
    topic_panel.py               Topic 诊断面板
  scripts/
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

日志文件写入：

```text
logs/jetson-cockpit-YYYY-MM-DD.log
```

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

本机 WSL 可以做语法、import、`colcon build` 这类低成本冒烟检查，但它不是
这条链路的最终验收。最终要证明的是：

```text
PC / WSL cockpit
  -> ROS2 DDS /cmd_vel
Jetson ~/qt/ros2_ws
  -> cmd_vel_car_web_bridge
  -> /vehicle/control_action
```

因此正式验收顺序是：

1. 只把 `jetson/mirror/ros2_ws/` 推到 Jetson `~/qt/ros2_ws`。
2. 在 Jetson 上 `colcon build --packages-select cmd_vel_car_web_bridge`。
3. 在 Jetson 上启动 `~/qt/ros2_ws/scripts/bridge_stack.sh start`。
4. PC/WSL 启动 cockpit Qt，通过按钮或键盘发 `/cmd_vel`。
5. Jetson 日志或 `/vehicle/control_action` 看到五个动作回显。

`cockpit/` 只运行在 PC/WSL，本目录任何时候都不部署到 Jetson。

## 本机冒烟

复杂 ROS2 命令不要在 PowerShell 里拼一行；按 `remote/` 的约定，放进 WSL
脚本执行。本脚本只用于推远端前快速发现明显问题：

```powershell
wsl -d Ubuntu-22.04 -- bash /mnt/d/Downloads/work/ros-dev/jetson/cockpit/scripts/verify_cmd_vel_bridge.sh
```

预期最后一行：

```text
VERIFY_CMD_VEL_BRIDGE_OK
```

如果本机冒烟通过，只说明包和本机 DDS 闭环基本可用；是否能控制 Jetson 侧
dry-run bridge，仍以远端部署后的跨机测试为准。

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
