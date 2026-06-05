# xtark JSON 控制适配方案

## 1. 目标

用 xtark 小车验证“外部 JSON 控制协议 + 底盘运动反馈”的思路。

本方案不改 xtark 原有底盘驱动，不改 STM32 / OpenCRP 串口协议，不抢底盘串口。只在 ROS1 层增加一个适配程序：

```text
JSON cmd_vel -> ROS1 /cmd_vel -> xtark_driver -> 底盘
xtark_driver /odom /imu /voltage -> JSON odom_base / base_status
```

这样 xtark 可以作为公司小车接入前的学习和验证平台。

## 2. 当前确认的 xtark 能力

远端小车：

| 项 | 值 |
|----|----|
| 主机 | `xtark-robot` |
| IP | `192.168.1.169` |
| 用户 | `xtark` |
| 系统 | Ubuntu 18.04.5 LTS / Jetson Nano / ROS Melodic |
| 工作区 | `~/ros_ws` |

源码与配置确认：

| 能力 | xtark 现有实现 |
|------|----------------|
| 底盘驱动 | `xtark_driver` |
| 控制入口 | 订阅 ROS1 `/cmd_vel` |
| 控制消息 | `geometry_msgs/Twist` |
| 前后速度 | `linear.x` |
| 横移速度 | `linear.y`，麦轮 / 全向底盘可用 |
| 转向速度 | `angular.z` |
| 里程计反馈 | 发布 `/odom_raw`，EKF 后发布 `/odom` |
| IMU | 发布 `/imu` |
| 电压 | 发布 `/voltage` |
| 底盘串口 | `/dev/ttyTHS1` |
| 控制频率 | `50 Hz` |

结论：xtark 已经具备 JSON 协议需要的“速度控制入口”和“运动反馈出口”。

## 3. 推荐架构

```text
PC / RK3568 / 强主机
  ├─ 发送 JSON cmd_vel
  └─ 接收 JSON odom_base / base_status

        TCP / WebSocket / 其他通信

xtark Nano
  └─ json_base_adapter
       ├─ JSON cmd_vel -> ROS1 /cmd_vel
       ├─ ROS1 /odom -> JSON odom_base
       ├─ ROS1 /imu -> JSON imu_base，可选
       └─ ROS1 /voltage -> JSON base_status

xtark_driver
  ├─ /cmd_vel -> /dev/ttyTHS1 -> 底盘
  └─ /dev/ttyTHS1 -> /odom /imu /voltage
```

## 4. JSON 到 ROS1 的映射

### 4.1 控制：`cmd_vel`

JSON：

```json
{
  "type": "cmd_vel",
  "linear_x": 0.20,
  "linear_y": 0.00,
  "angular_z": 0.00
}
```

映射到 ROS1：

```text
/cmd_vel.linear.x  <- linear_x
/cmd_vel.linear.y  <- linear_y
/cmd_vel.angular.z <- angular_z
```

说明：

- `linear_y` 对 xtark 麦轮底盘有意义。
- 如果后续平台是差速底盘，`linear_y` 置 0 或忽略。
- 适配程序需要做限速和超时停车。

### 4.2 运动反馈：`odom_base`

ROS1 `/odom` 映射为 JSON：

```json
{
  "type": "odom_base",
  "x": 1.25,
  "y": 0.08,
  "yaw": 0.12,
  "linear_x": 0.19,
  "linear_y": 0.00,
  "angular_z": 0.01
}
```

字段来源：

```text
x / y / yaw       <- /odom.pose.pose
linear_x          <- /odom.twist.twist.linear.x
linear_y          <- /odom.twist.twist.linear.y
angular_z         <- /odom.twist.twist.angular.z
```

### 4.3 状态反馈：`base_status`

ROS1 `/voltage` 可映射为：

```json
{
  "type": "base_status",
  "online": true,
  "estop": false,
  "battery_v": 24.3,
  "mode": "auto",
  "error_code": 0
}
```

第一版如果没有急停和模式信息，可以先固定：

```text
online = true
estop = false
mode = "auto"
error_code = 0
```

## 5. 适配程序放哪里

第一版建议放在 xtark Nano 上运行：

```text
~/ros_ws/src/xtark_json_bridge/
```

原因：

- 能直接访问 ROS1 `/cmd_vel`、`/odom`、`/imu`、`/voltage`。
- 不需要 PC 安装 ROS Melodic。
- 外部只通过 JSON 与 xtark 通信。

也可以放在 PC 上运行，但 PC 需要加入 ROS1 网络，并正确配置：

```text
ROS_MASTER_URI=http://192.168.1.169:11311
ROS_IP=<PC 局域网 IP>
```

## 6. 第一版验证步骤

1. 启动 xtark 原生底盘驱动：

```bash
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
roslaunch xtark_driver xtark_bringup.launch
```

2. 确认原生 ROS1 接口：

```bash
rostopic hz /odom
rostopic echo /imu -n 1
rostopic echo /voltage -n 1
```

3. 启动 JSON 适配程序。

4. 外部发送低速 JSON：

```json
{"type":"cmd_vel","linear_x":0.10,"linear_y":0.00,"angular_z":0.00}
```

5. 观察小车低速前进，并确认收到 `odom_base`。

6. 发送停止：

```json
{"type":"cmd_vel","linear_x":0.00,"linear_y":0.00,"angular_z":0.00}
```

## 7. 风险与注意

- 第一轮必须低速测试，建议 `linear_x <= 0.10 m/s`，`angular_z <= 0.20 rad/s`。
- 适配程序必须实现控制超时停车，建议 300-500 ms。
- 不要绕过 `xtark_driver` 直接写 `/dev/ttyTHS1`。
- 不要在没有急停确认的情况下做自主导航闭环。
- xtark 是 ROS1 / Melodic，最终公司小车可以不使用 ROS，但 JSON 字段保持一致。

## 8. 当前结论

xtark 可以作为 JSON 底盘协议的验证平台。实现方式不是改底盘硬件，而是在 Nano 上增加 `JSON <-> ROS1` 适配层。验证通过后，同一套 JSON 字段可以迁移到公司小车底盘对接中。
