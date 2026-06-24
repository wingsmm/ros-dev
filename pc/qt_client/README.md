# xtark Console / PC Qt Client

`pc/qt_client` 是 PC / WSL2 侧的机器人联调入口。当前采用“双入口”结构：

- 默认入口：新版机器人 Shell，用于机器人选择、机器人工作区、摄像头页等面向使用的页面。
- legacy 入口：旧调试台，保留 JSON、ROS2、建图、导航等调试能力。

## 启动

```bash
cd /mnt/d/Downloads/work/ros-dev/pc/qt_client
./run.sh
```

无 ROS 环境，仅验证 GUI / 机器人选择 / 摄像头 HTTP/MJPEG：

```bash
./run.sh --no-ros
```

启动旧调试台：

```bash
./run.sh --legacy
```

## 当前默认 Shell

```text
机器人选择页
  ├─ 添加机器人
  ├─ 编辑机器人
  ├─ 删除机器人
  └─ 连接机器人

机器人工作区
  ├─ 左侧飞入式导航
  ├─ 总览（占位）
  ├─ 摄像头（HTTP/MJPEG 已实现）
  ├─ 机器人（实时激光扫描 + 手动控制已实现）
  ├─ 里程计对照（三路 odom 轨迹对比 + 手动控制已实现）
  ├─ SLAM 地图（占位）
  ├─ GPS 地图（占位）
  ├─ 设置（占位）
  └─ 关于（占位）
```

机器人配置保存到：

```text
pc/qt_client/data/robots.json
```

## 摄像头页

新版工作区的“摄像头”页已实现 HTTP/MJPEG 看图 MVP：

```text
CameraPage
  ├─ RobotHudBar
  ├─ CameraToolbar
  ├─ CameraViewport
  └─ ManualControlStrip

MjpegStreamController
  ├─ CameraPage
  └─ legacy CameraPanel
```

默认 URL：

```text
http://192.168.1.169:8080/stream?topic=/camera/image_raw
```

说明：

- 当前 HTTP/MJPEG 是“先能看图”的临时方案。
- Android / ROS 长期契约仍是 `/image_raw/compressed`。
- 后续应通过 `ros1_bridge`、`ros1_gateway` 或 `ros2_native` backend 对齐 ROS 话题模型。

机器人端 Qt 全功能栈（摄像头 + 机器人 + 里程计对照）：

```bash
~/ros_ws/scripts/qt_stack.sh start
~/ros_ws/scripts/qt_stack.sh status
~/ros_ws/scripts/qt_stack.sh stop
```

与 `android_stack.sh` 互斥，不能同时运行。Windows 部署与控制：`xtark\scripts\qt_remote.bat`。

轻量模式（仅底盘 + JSON，无相机、无激光里程计）：

```bash
CAMERA_ENABLE=0 LASER_ODOM_ENABLE=0 qt_stack.sh start
```

相机/JSON 单模块调试见 `xtark/scripts/dev/`（非日常入口）。

## 机器人页

新版工作区的“机器人”页复用全局 `RobotHudBar` 和摄像头页已有的
`ManualControlStrip`，通过 JSON gateway 显示真实 `/scan`，不提供模拟激光：

```text
/scan -> json_base_adapter -> laser_scan JSON -> RobotSession -> LaserScanView
```

页面支持激光点/扇面、机器人和里程计原点、居中、拖动、缩放、朝向锁定，
以及按住运动、松手停止的七键手动控制（六向运动 + 停止）：

- 浅紫方块：本次机器人连接收到的第一帧 `odom_base` 所建立的相对原点。
- 蓝色凹箭头：机器人位置和朝向；锁定视角时固定朝上。
- 红/紫/蓝方块：激光回波端点，距离由近到远从红色过渡到蓝色。
- 半透明放射扇区：相邻激光束形成的距离渐变，不是导航路径。
- 蓝色连续轮廓：Qt 对相邻有效回波的辅助连线，便于观察墙体边缘。

当前 MEC + XAS 的 `/scan` 位于 `laser` 坐标系，真车静态外参约为
`base_footprint -> laser: x=0.05m, y=0, yaw=pi`。Qt 在绘制前把激光点变换到
底盘坐标系；机器人箭头仍使用底盘/里程计朝向。因此方向修正只需更新并重启 Qt，
不需要修改 JSON 协议或重新部署机器人端。

### 与 Android 的对齐结论

当前实现是“基本功能对齐”，不是像素级复制：

| 项目 | 对齐状态 | 说明 |
|------|----------|------|
| 真实激光、起点、机器人、点/射线/扇面 | 已对齐 | Qt 额外保留深色背景和亮蓝墙体轮廓；无数据/超时有明确提示 |
| 居中、拖动、缩放、朝向锁定 | 已对齐 | 桌面端使用鼠标拖动和滚轮缩放 |
| 六向按钮、松手停车 | 已对齐 | Qt 直接使用 ROS `Twist` 符号；最终 `/cmd_vel` 方向与 Android 一致 |
| SafeMode 告警衰减与 HUD 变红 | 代码基本对齐 | 默认关闭；前方扫描角与 XAS 外参的关系尚未真车确认 |
| 顶部停止 | 基本范围对齐 | 只发零速度；不是硬件急停，不提供 Android 导航计划暂停/恢复 |
| 摇杆、航点、GPS、Wi-Fi | 明确不实现 | 不属于当前 Qt 机器人页基本范围 |

安全生命周期：运动按钮按下后约 10Hz 重发；松开、窗口失焦、应用失活、页面隐藏、
离开机器人页或关闭页面时发送零速度。中间“停止”和顶部“停止”始终走
`RobotSession.stop_motion()`。

位置基准与 Android 相同：`RobotSession` 在每次连接的第一帧 `odom_base` 保存
`start_x/start_y`，机器人页使用 `current - start` 绘制紫色原点；原始 `last_odom`
仍供 HUD 使用。切换页面不重新归零，重启 Qt 或重新连接机器人后重新采集首帧。
heading 继续使用当前 odom yaw，不减首帧 yaw。

验收状态：代码和本地静态检查已完成；机器人端部署、真车六向运动、停车、激光方向
及告警扇区仍需现场验证。`./run.sh --no-ros` 只能检查界面，机器人页会显示
“等待激光数据”，不会生成 Mock 激光。

## 里程计对照页

实验观察页，不参与导航或 SLAM。同时在画布上对比三路位姿估计：

| JSON type | ROS 话题 | 轨迹颜色 |
|-----------|----------|----------|
| `odom_raw` | `/odom_raw` | 灰 |
| `odom_base` | `/odom` | 蓝 |
| `odom_laser` | `/odom_laser` | 橙 |

车端需使用带旁路消息的 JSON bridge；`qt_stack.sh` 默认一并启动 RF2O。

部署顺序：

1. Windows：`xtark\scripts\qt_remote.bat deploy`（或车端手动同步 `xtark_json_bridge` + `xtark_laser_odometry` 后 `catkin_make`）。
2. 停掉 `android_stack.sh`（若正在运行）。
3. 启动 Qt 栈：

```bash
~/ros_ws/scripts/qt_stack.sh start
~/ros_ws/scripts/qt_stack.sh status
~/ros_ws/scripts/qt_stack.sh logs
~/ros_ws/scripts/qt_stack.sh record   # 可选录包
~/ros_ws/scripts/qt_stack.sh stop
```

4. PC 侧 `./run.sh`，进入「里程计对照」页验收。

该栈拉起 roscore、bringup、JSON `:8765`、相机预览和 `rf2o -> /odom_laser`。
`record` 不随 `start` 自动执行。

页面操作：

- 小车静止后点「重新归零」：分别记录三路首帧 `x0/y0/yaw0`，平移并旋转到共同局部坐标。
- 灰/蓝/橙轨迹与末端箭头可单独开关；超时后仍绘制已有轨迹（半透明虚线），仅停止末端箭头并在顶栏标红。
- 底部复用 `ManualControlStrip`（六向 + 停止，无摇杆）。

`/odom_laser` 是估计值，不是真值；三路不一致只能说明估计器存在差异。

## 摄像头页远程控制

摄像头页当前仍应保持“观察 Android 后再决定如何抄”的状态，不要过早做成最终形态。底部 `ManualControlStrip` 已统一走 `RobotSession / RobotBackend`：

```text
ManualControlStrip
  -> RobotSession.send_velocity() / stop_motion() / emergency_stop()
  -> RobotBackend
```

当前控制语义：

- `MockRobotBackend`：只记录速度请求，用于 `--no-ros` UI 验证。
- `JsonGatewayBackend`：复用 legacy JSON 控制链路，用于真车远控。
- 运动按钮是 dead-man 模式：按住立即发速度，并以约 10Hz 持续发送；松开按钮或点击停止会调用 `stop_motion()`。
- 调试日志会打印 `RobotSession velocity`、`JSON velocity sent=True`、底层 `TX ...`，用于确认 Qt -> JSON 网关是否真的发出。

长期再接：

- `Ros1GatewayBackend`：连接机器人端应用层 ROS1 gateway。
- `Ros2NativeBackend`：WSL2/ROS2 成熟后原生发布/订阅。

页面层不要直接发 ROS，也不要直接打开 TCP socket。

机器人端相机脚本保持中性：

- Android 观察：`/image_raw/compressed`
- Qt/浏览器预览：`http://192.168.1.169:8080/stream?topic=/camera/image_raw`

控车需要底盘和 JSON 网关，使用 `qt_stack.sh start`，不要只启动 `dev/camera_stack.sh`。

## legacy 调试台

`./run.sh --legacy` 保留原有调试能力：

- TCP JSON 连接 xtark 底盘。
- 发布 ROS2 `/odom_base`、`/base_status`、TF。
- `/cmd_vel` 转 JSON 控制底盘。
- 启停 RViz2 / slam_toolbox / Nav2。
- legacy `CameraPanel` 继续可用，并复用新版 `MjpegStreamController`。

## 目录结构

```text
qt_client/
├── app.py                    # 轻量入口：参数、QApplication、单实例锁
├── main_window.py            # 默认 Shell / legacy 路由
├── run.sh
├── backends/                 # RobotBackend 抽象和 mock / ros1 / ros2 backend 骨架
├── core/                     # RobotSession / RobotConnectionState
├── data/                     # robots.json
├── gateway/                  # JSON / ROS2 网关旧调试能力
├── legacy/                   # LegacyWindow，旧调试台
├── mapping/                  # RViz2 / SLAM / Nav2 process manager
├── ui/
│   ├── assets/               # 从 Android 复制的图标资源
│   ├── dialogs.py
│   ├── models/               # RobotInfo / RobotStore
│   ├── pages/                # 机器人列表、表单、工作区、摄像头页
│   ├── widgets/              # Camera/HUD/Nav/ManualControl 等组件
│   ├── robot_shell_controller.py
│   └── shell.py
├── config/
├── maps/
└── logs/
```

## 验收建议

基础 GUI：

```bash
./run.sh --no-ros
```

检查：

- 默认进入机器人选择页。
- 添加/编辑/删除机器人弹窗可用。
- 连接机器人后进入工作区。
- 点击左上角导航按钮，左侧导航飞入。
- 点击“选择机器人”返回上一级。
- 点击“摄像头”自动连接并显示画面。
- 断开/重连按钮可用。

代码检查：

```bash
python -m py_compile app.py main_window.py
git diff --check
```
