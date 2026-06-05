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

先启动原生底盘驱动：

```bash
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
roslaunch xtark_driver xtark_bringup.launch
```

再启动适配节点：

```bash
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

## 安全

- 默认 `cmd_timeout_sec=0.5`，超过时间未收到控制指令会自动发布 0 速度。
- 第一轮测试请低速：`linear_x <= 0.10`，`angular_z <= 0.20`。
- 不要绕过 `xtark_driver` 直接写底盘串口。
