# xtark_json_bridge

JSON 底盘协议到 xtark ROS1 接口的适配包。

目标是不改 `xtark_driver`、不碰 `/dev/ttyTHS1`，只在 ROS1 topic 层做转换：

```text
JSON cmd_vel -> ROS1 /cmd_vel
ROS1 /odom /voltage /scan -> JSON odom_base / base_status / laser_scan / scan_warning
```

## 运行位置

建议部署到 xtark Nano：

```text
~/ros_ws/src/xtark_json_bridge/
```

## 启动

推荐 `xtark/scripts/json_stack.sh`（见 [DEPLOY.md](DEPLOY.md)）：

```bash
~/ros_ws/scripts/json_stack.sh start    # 后台一键
~/ros_ws/scripts/json_stack.sh bringup  # 前台终端 1
~/ros_ws/scripts/json_stack.sh json     # 前台终端 2
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

## 下行反馈

除 `odom_base`、`base_status` 外，适配节点还广播：

### scan_warning（10Hz，完整 /scan 计算）

```json
{"type":"scan_warning","stamp_ms":1780000000000,"front_min_m":1.24,"stale":false}
```

### laser_scan（默认 10Hz，可配置 stride 抽样）

```json
{
  "type": "laser_scan",
  "stamp_ms": 1780000000000,
  "frame_id": "laser",
  "angle_min": -2.356,
  "angle_max": 2.356,
  "angle_increment": 0.0087,
  "range_min": 0.25,
  "range_max": 12.0,
  "ranges": [1.24, 1.25, null, 2.18]
}
```

- `laser_scan_stride` 抽样后 `angle_increment` 同步放大。
- `NaN` / `Inf` / 超范围距离序列化为 JSON `null`。
- `scan_warning` 始终使用完整分辨率 `/scan`，与 `laser_scan` 独立。
- `laser_scan` 保留原始 `frame_id` 和扫描角，不在网关内伪装成底盘坐标。
- 当前 MEC + XAS 外参约为 `base_footprint -> laser: x=0.05m, y=0, yaw=pi`；Qt 机器人页负责在绘制前应用该静态外参。

配置项见 `config/json_base_adapter.yaml`：

```yaml
laser_scan_send_rate_hz: 10.0
laser_scan_stride: 1
scan_stale_sec: 1.0
```

Qt 机器人页专用启动脚本：`xtark/scripts/robot_control_stack.sh`（仅 bringup + JSON，不含摄像头/导航）。

`scan_warning` 当前按原始扫描角 `+-40 deg` 计算，与 Android `WarningSystem` 的基础扇区一致，
但尚未加入 Android 使用的当前转速修正，也没有套用 `laser -> base_footprint` 外参。
因此 MEC + XAS 的真实“车头前方”告警扇区必须在真车上确认；确认前 Qt 默认配置保持
`warning_enabled=false`、`warning_safemode=false`。

## 外部控制端

PC / RK3568 上的命令行工具已放到仓库根目录 `pc/tools/`，不随 ROS1 包部署到 xtark。

第二阶段推荐优先使用 `pc/qt_client/` 图形调试台；`pc/tools/` 保留为命令行备用和快速验证工具。

键盘遥控：

```bash
cd pc/tools
python xtark_json_keyboard.py --host 192.168.1.168 --port 8765 --speed 0.15 --turn 0.4
```

流程：

```text
键盘 -> JSON cmd_vel -> xtark_json_bridge -> ROS1 /cmd_vel -> xtark_driver
```

按键逻辑与 `xtark_ctl/xtark_twist_keyboard.py` 一致：每次有效按键发送一条 JSON；按住键时靠终端连发。同连接可打印 `odom_base` 反馈，默认最多 2 Hz。

只看控制、不打印反馈：

```bash
cd pc/tools
python xtark_json_keyboard.py --host 192.168.1.168 --port 8765 --speed 0.15 --turn 0.4 --no-feedback
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

2026-06-23 Qt “机器人”页扩展状态：`laser_scan`、独立启动脚本和 Qt 接收/绘制代码已完成，
但尚未在本记录中证明远端部署、真车激光方向、六向控制和 `scan_warning` 前方扇区。
