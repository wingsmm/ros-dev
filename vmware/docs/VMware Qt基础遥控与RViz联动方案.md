# VMware Qt 基础遥控与 RViz 联动方案

本文面向实施 agent / 苦力使用。目标是在现有 VMware Qt 纯客户端基础上，新增一个**最小、安全、可验收**的手动遥控面板，并保证小车移动时 RViz 中 `/odom`、`/scan`、TF、深度相关显示仍按当前方向和坐标系正常刷新。

## 结论

可以做，而且改动不大：VMware Qt 继续保持纯客户端，不 SSH、不远程启动小车脚本，只在 VM 本地发布 ROS1 `/cmd_vel`。

推荐做成独立小阶段：

1. VM Qt 新增 `vmware/qt/ui/teleop_panel.py`。
2. VM Qt 新增一个很薄的 ROS1 `/cmd_vel` publisher。
3. UI 提供 `前进 / 后退 / 左转 / 右转 / 停止` 五个按钮。
4. RViz 仍由现有模式显示，移动时重点看「雷达/里程计」模式下 `/odom`、`/scan`、TF 是否实时变化。

不要把导航、地图、自动避障、路径规划、摇杆、航点一起塞进来。

## 当前状态

已经实现的 VMware Qt 能力：

| 能力 | 状态 |
|------|------|
| 连接小车 ROS Master | 已有 |
| 本地检查 topic | 已有 |
| 本地启动 RViz | 已有 |
| 雷达/里程计 RViz | 已有 |
| 深度轻量 / 诊断 / 增强 | 已有或已规划实现 |
| Qt 内置遥控 | **未实现，本方案新增** |

小车侧仍然是手动启动 `pc_stack`：

```bash
~/ros_ws/scripts/pc_stack.sh radar2d-start
# 或
~/ros_ws/scripts/pc_stack.sh full-start
```

只要小车侧 bringup 正常订阅 `/cmd_vel`，VM Qt 发布 `geometry_msgs/Twist` 即可控制小车。

## 非目标

本阶段明确不要做：

- 不做 SSH 远程启停小车脚本。
- 不做导航、建图、Cartographer、move_base。
- 不做自动避障、路径规划、目标点导航。
- 不做摇杆、航点、地图保存。
- 不修改 `pc/qt_client` 架构，不引入 JSON gateway / ROS2 bridge。
- 不把 Qt 的停止按钮描述成硬件急停。
- 不调整已有节点方向；当前 `/cmd_vel` 符号、RViz 坐标方向以小车现有 bringup 和 TF 为准。

## UI 设计

新增文件：

```text
vmware/qt/ui/teleop_panel.py
```

面板建议放在主窗口 RViz 控制区或状态区下方，保持单页控制台，不做新页面。

### 按钮

最小按钮：

```text
      前进
左转  停止  右转
      后退
```

语义建议：

| 按钮 | Twist |
|------|-------|
| 前进 | `linear.x = +v` |
| 后退 | `linear.x = -v` |
| 左转 | `angular.z = +w` |
| 右转 | `angular.z = -w` |
| 停止 | `linear.x = 0, linear.y = 0, angular.z = 0` |

注意：这里的「左 / 右」建议先做**原地转向**，不要做横移。`pc/qt_client` 里已有六向控制（左移/右移/左转/右转），但本阶段按用户需求先做五键最小版。若后续确认底盘需要 MEC 横移，再新增「左移 / 右移」两个按钮，不要复用「左转 / 右转」文案造成误解。

### 交互

参考 `pc/qt_client/ui/widgets/manual_control_strip.py` 的行为，而不是复制其 JSON / ROS2 链路：

- 运动按钮采用 dead-man 语义：**按住才运动，松开即停止**。
- 按下后立即发布一次速度，并用 `QTimer` 约 10Hz 重复发布。
- 松开按钮时发布零速度。
- 点击「停止」时发布零速度，建议连续发布 3 次。
- 窗口失焦、应用失活、面板隐藏、窗口关闭时必须自动发布零速度。
- 默认不启用键盘控制；如果实现键盘，也必须只在 Qt 窗口获焦且非输入框时生效。

### 速度默认值

默认速度要保守：

```text
linear.x = 0.10 m/s
angular.z = 0.25 rad/s
repeat_hz = 10
```

可在 `config/vmware_client.env` 中预留配置：

```dotenv
CMD_VEL_TOPIC=/cmd_vel
TELEOP_LINEAR_SPEED=0.10
TELEOP_ANGULAR_SPEED=0.25
TELEOP_REPEAT_HZ=10
TELEOP_ENABLE_KEYBOARD=0
```

不要默认给大速度。真车第一次验收必须低速、空旷、有人看车。

## ROS 发布链路

推荐新增一个很薄的 core 模块：

```text
vmware/qt/core/teleop_publisher.py
```

职责：

- 初始化 ROS1 publisher：`/cmd_vel`，类型 `geometry_msgs/Twist`。
- 提供 `publish_velocity(linear_x, linear_y, angular_z)`。
- 提供 `stop()`，发布零速度。
- Master 不可达或 `rospy` 初始化失败时，向 UI 返回明确错误，不让按钮假装可用。

实现建议：

- 优先使用 VM 的 ROS1 Python 环境：`rospy` + `geometry_msgs.msg.Twist`。
- 不要用 shell 循环 `rostopic pub` 做持续遥控；它不好停止，也不适合按钮 dead-man。
- `rospy.init_node` 只能初始化一次。可以在主窗口启动时懒初始化，也可以首次按遥控按钮时初始化。
- 如果当前进程已经初始化过 ROS node，要复用，不要重复初始化。

## 需要修改的文件

### 必改

- `vmware/qt/ui/teleop_panel.py`
  - 新增五键 UI。
  - 发出 `velocity_requested(float, float, float)` 和 `stop_requested()` signal。
  - 内部处理按住、松开、失焦、隐藏、关闭时停车。

- `vmware/qt/core/teleop_publisher.py`
  - 新增 ROS1 `/cmd_vel` publisher。
  - 只发布 `geometry_msgs/Twist`，不做导航或避障。

- `vmware/qt/main_window.py`
  - 创建 `TeleopPanel`。
  - 连接 panel signal 到 publisher。
  - Master 不可达时禁用或提示遥控不可用。
  - 关闭窗口时调用 `teleop.stop()`。

- `vmware/qt/core/env.py`
  - 增加 `CMD_VEL_TOPIC`、`TELEOP_LINEAR_SPEED`、`TELEOP_ANGULAR_SPEED`、`TELEOP_REPEAT_HZ`、`TELEOP_ENABLE_KEYBOARD` 配置读取。

- `vmware/qt/config/vmware_client.env.example`
  - 补充上述遥控配置示例。

- `vmware/qt/README.md`
  - 增加基础遥控说明、启动条件、安全边界、验收步骤。

### 可选

- `vmware/qt/ui/status_panel.py`
  - 增加 `/cmd_vel` publisher 状态或 Master 可达提示。

- `vmware/qt/core/ros1_probe.py`
  - 增加 `/cmd_vel` subscriber 检查：

```bash
rostopic info /cmd_vel
```

注意这里检查的是小车侧是否有 subscriber。Qt 自己发布 `/cmd_vel` 后，有 publisher 不代表底盘会动；真正关键是 subscriber 是否存在。

## RViz 移动显示要求

移动时优先用「雷达/里程计」模式验收：

```text
Fixed Frame: odom
Displays:
  - Grid
  - TF
  - LaserScan /scan
  - Odometry /odom
```

验收时观察：

- 小车前进/后退时，`/odom` 位置应变化。
- 左转/右转时，`/odom` yaw 应变化。
- `/scan` 随车运动实时刷新，不应卡死。
- TF 不报 `No transform` 或明显方向错误。

如果深度增强模式中点云“竖到天上”，不要先改 `/cmd_vel`。那通常是点云 frame 与 `base_link/odom` 的 TF 链不完整或光学坐标系外参问题。基础遥控只负责让车动，点云姿态另按 TF 方案处理。

## 小车侧启动要求

基础遥控需要小车侧有底盘 bringup 和 `/cmd_vel` subscriber。推荐使用：

```bash
~/ros_ws/scripts/pc_stack.sh radar2d-start
```

或：

```bash
~/ros_ws/scripts/pc_stack.sh full-start
```

如果只启动 `camera-start`，必须确认该 profile 也包含底盘 bringup 并订阅 `/cmd_vel`。否则 Qt 发布了 `/cmd_vel`，小车也不会动。

## 验收步骤

### 1. 代码静态验收

VM：

```bash
cd ~/ros-dev/vmware/qt
python3 -m py_compile app.py main_window.py core/*.py ui/*.py
```

要求无语法错误。

### 2. 无车 / Master 不可达验收

VM 直接启动：

```bash
./run.sh
```

要求：

- Qt 正常打开。
- Master 不可达时，遥控按钮禁用或点击后明确提示。
- 不出现“按钮可点但实际静默失败”的假成功。

### 3. 架空轮或空旷低速验收

小车：

```bash
~/ros_ws/scripts/pc_stack.sh radar2d-start
rostopic echo /cmd_vel
```

VM：

```bash
cd ~/ros-dev/vmware/qt
./run.sh
```

在 Qt 中按住按钮并松开，检查：

- 按住前进：`linear.x > 0`，约 10Hz 重复。
- 松开前进：立即出现零速度。
- 按住后退：`linear.x < 0`。
- 按住左转：`angular.z > 0`。
- 按住右转：`angular.z < 0`。
- 点击停止：连续或立即出现零速度。

### 4. RViz 联动验收

Qt 中选择「雷达/里程计」并启动 RViz。

通过条件：

- 前进/后退时 RViz 中 `/odom` 轨迹或姿态实时变化。
- 左转/右转时 RViz 中机器人朝向实时变化。
- `/scan` 持续刷新。
- 停止后 `/cmd_vel` 为零，小车停止。

## 风险与注意事项

- 这是普通速度控制，不是硬件急停。
- 真实小车第一次测试必须低速、空旷、有人盯车。
- Qt 失焦、切到 RViz、关闭窗口时必须发零速度。
- 不要把 RViz 显示正常等同于安全控制可靠；控制链路要用 `/cmd_vel` echo 单独验收。
- 不要在没有 `/cmd_vel` subscriber 的情况下说“遥控已通”。
- 不要为了让深度点云好看而在本阶段改 TF 或点云节点；那是另一个问题。

## 推荐提交边界

建议独立提交：

```text
vmware qt: add basic cmd_vel teleop panel
```

不要和深度增强、点云 TF、地图导航混在一个提交里。这样出问题时可以快速判断是遥控链路还是显示链路。
