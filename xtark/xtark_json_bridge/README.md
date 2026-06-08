# xtark_json_bridge

JSON 底盘协议到 xtark ROS1 接口的适配包。

目标是不改 `xtark_driver`、不碰 `/dev/ttyTHS1`，只在 ROS1 topic 层做转换：

```text
JSON cmd_vel -> ROS1 /cmd_vel
ROS1 /odom /voltage -> JSON odom_base / base_status
```

## 运行位置

建议部署到 xtark Nano：

```text
~/ros_ws/src/xtark_json_bridge/
```

## 启动

推荐 `xtark/scripts/run_xtark.sh`（见 [DEPLOY.md](DEPLOY.md)）：

```bash
~/ros_ws/scripts/run_xtark.sh start    # 后台一键
~/ros_ws/scripts/run_xtark.sh bringup  # 前台终端 1
~/ros_ws/scripts/run_xtark.sh json     # 前台终端 2
```

手工等价命令：

```bash
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
roslaunch xtark_driver xtark_bringup.launch
roslaunch xtark_json_bridge json_base_adapter.launch
```

## TCP JSON

默认监听：

```text
0.0.0.0:8765
```

一行一个 JSON：

```json
{"type":"cmd_vel","linear_x":0.10,"linear_y":0.00,"angular_z":0.00}
```

停止：

```json
{"type":"cmd_vel","linear_x":0.00,"linear_y":0.00,"angular_z":0.00}
```

## 外部控制端

PC / RK3568 上的命令行工具已放到仓库根目录 `pc/tools/`，不随 ROS1 包部署到 xtark。

第二阶段推荐优先使用 `pc/qt_client/` 图形调试台；`pc/tools/` 保留为命令行备用和快速验证工具。

键盘遥控：

```bash
cd pc/tools
python xtark_json_keyboard.py --host 192.168.1.169 --port 8765 --speed 0.15 --turn 0.4
```

流程：

```text
键盘 -> JSON cmd_vel -> xtark_json_bridge -> ROS1 /cmd_vel -> xtark_driver
```

按键逻辑与 `xtark_ctl/xtark_twist_keyboard.py` 一致：每次有效按键发送一条 JSON；按住键时靠终端连发。同连接可打印 `odom_base` 反馈，默认最多 2 Hz。

只看控制、不打印反馈：

```bash
cd pc/tools
python xtark_json_keyboard.py --host 192.168.1.169 --port 8765 --speed 0.15 --turn 0.4 --no-feedback
```

## 安全

- 默认 `cmd_timeout_sec=0.5`，超过时间未收到控制指令会自动发布 0 速度。
- 第一轮测试请低速：`linear_x <= 0.10`，`angular_z <= 0.20`。
- 不要绕过 `xtark_driver` 直接写底盘串口。

## 验收状态

2026-06-05 第一阶段已通过：

```text
PC -> JSON cmd_vel -> xtark_json_bridge -> /cmd_vel -> xtark_driver -> 底盘
xtark /odom /voltage -> JSON odom_base / base_status -> PC
```

已验证：

- PC 本地键盘可低速控制 xtark 前进。
- `odom_base` 的 `x / y / yaw` 能随小车运动变化。
- 当 xtark `/odom` 的 twist 为 0 时，适配节点会用位姿差分估算 `linear_x / linear_y / angular_z`。
- `base_status` 能回传 `online / estop / battery_v`。
