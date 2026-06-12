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

## 9. 第一阶段验收记录

日期：2026-06-05

测试方式：

```text
终端 1：xtark_driver
终端 2：json_base_adapter，监听 0.0.0.0:8765
终端 3：PC 本地 pc/tools/xtark_json_keyboard.py
```

PC 端命令：

```bash
cd pc/tools
python xtark_json_keyboard.py --host 192.168.1.169 --port 8765 --speed 0.10 --turn 0.20
```

验收结果：

| 项目 | 结果 |
|------|------|
| PC 连接 xtark JSON 端口 | 通过 |
| JSON `cmd_vel` 控制底盘 | 通过，按 `i` 可低速前进 |
| 停车与超时保护 | 通过，松开后自动停车 |
| `odom_base` 反馈 | 通过，`x / y / yaw` 随运动变化 |
| 速度反馈 | 通过，已对 xtark `/odom` 缺少 twist 的情况做位姿差分估算 |
| `base_status` 反馈 | 通过，能回传 `online / estop / battery_v` |

阶段结论：

```text
第一阶段通过：
PC 可通过 TCP JSON 远程低速控制 xtark；
xtark 可回传 odom_base 和 base_status；
不改 xtark_driver、不改底盘串口、不改 STM32 / OpenCRP 协议。
```

## 10. 第二阶段任务

第二阶段先不急于写大功能，重点是把第一阶段的临时验证整理成稳定开发流程。

| 任务 | 目标 |
|------|------|
| 运行方式整理 | 已将车端 ROS1 适配包与 PC 工具目录分开；后续再考虑 launch / systemd |
| 反馈显示优化 | 已形成 PC Qt 调试台基线，控制、状态、日志分区显示 |
| 安全状态完善 | 明确低电压、急停、手动 / 自动模式的字段来源 |
| 控制权管理 | Qt 调试台已有控制状态显示；后续补多控制端互斥策略 |
| 参数固化 | Qt 调试台已支持 host / port / 速度参数保存；后续固化默认测试值 |
| RK3568 联调 | RK3568 继续做传感器盒，PC 同时接收 `/scan` 和 xtark `odom_base` |
| 建图链路验证 | PC 侧用 RK3568 `/scan` + xtark `odom_base` 验证建图 |
| 公司底盘抽象 | 保持 JSON 字段稳定，为后续公司小车适配做接口基线 |

第二阶段的核心目标：

```text
把“能控”推进到“可稳定开发和联调”，但暂不直接进入自主导航闭环。
```

当前进展：

```text
第二阶段已开始：
车端仅保留 xtark_json_bridge；
PC 端命令行工具移动到 pc/tools；
PC Qt 调试台 pc/qt_client 已作为第二阶段 1-5 的联调基线。
```

## 11. RK3568 联调计划

RK3568 联调先不让 RK 控车，也不急于上导航闭环。第一目标是让 PC 同时拿到两类数据：

```text
RK3568：/scan
xtark：odom_base / base_status
```

推荐数据流：

```text
RPLidar -> RK3568 sensor_stack / ROS2 -> /scan

xtark_driver -> xtark_json_bridge -> TCP JSON odom_base / base_status

PC:
  订阅 RK3568 的 /scan
  接收 xtark 的 JSON odom_base
  后续在 PC 上转成 ROS2 /odom_base 和 TF
```

阶段步骤：

| 步骤 | 目标 |
|------|------|
| 1. 独立确认 RK3568 | 确认 RK3568 Docker 里 `/scan` 稳定发布 |
| 2. 独立确认 xtark | 确认 PC Qt 调试台能收到 `odom_base / base_status` |
| 3. PC 汇聚数据 | PC 同时接收 RK `/scan` 和 xtark JSON 反馈 |
| 4. 转成 ROS2 | 在 PC 上做 `JSON odom_base -> ROS2 /odom_base` |
| 5. 补 TF | 发布 `odom -> base_link`、`base_link -> laser` |
| 6. RViz2 验证 | 先看 `/scan`、里程计方向、雷达安装方向是否一致 |
| 7. slam_toolbox | 低速遥控走一圈，验证 `/scan + odom + TF` 能否建图 |

第一轮只验收：

```text
PC 能同时看到 RK3568 /scan 和 xtark odom_base；
小车运动方向、yaw 方向、雷达方向基本一致；
不做 Nav2，不做自主导航，不加相机点云融合。
```

TF 初步约定：

```text
odom -> base_link     来自 xtark odom_base
base_link -> laser    来自外挂雷达安装位置，先手工测量静态发布
```

注意：

- RK3568 继续定位为传感器盒，优先保证 USB 传感器稳定。
- PC 是开发和算法验证中心，先承担 ROS2 汇聚、RViz2、slam_toolbox。
- xtark 只提供运动和里程计反馈，不改底盘串口，不改 `xtark_driver`。
- 这条链路跑通后，后续公司底盘只需要替换 `odom_base / cmd_vel` 的 JSON 对接端。
