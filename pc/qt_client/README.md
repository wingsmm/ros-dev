# xtark Console / PC Qt Client

`pc/qt_client` 是 PC / WSL2 侧的机器人联调入口。**默认入口**为新版机器人 Shell（机器人选择、工作区、摄像头、里程计对照等）。

> legacy 旧调试台已 **deprecated**，不再承载新功能；仅作历史对照，且需 `XTARK_ALLOW_LEGACY=1` 才能启动（见文末说明）。

## 启动

```bash
cd /mnt/d/Downloads/work/ros-dev/pc/qt_client
./run.sh
```

无 ROS 环境，仅验证 GUI / 机器人选择 / 摄像头 HTTP/MJPEG：

```bash
./run.sh --no-ros
```

（`--no-ros` 仅影响已废弃的 legacy 窗口；默认新 shell 不依赖 ROS2。）

## 日志

默认日志目录：`pc/qt_client/logs/`（相对路径始终以 `pc/qt_client` 为基准，不受启动目录影响）。

每日一个文件，多次启动同日追加，跨午夜自动切换：

```text
logs/xtark-console-YYYY-MM-DD.log
```

`.env` 可覆盖（示例见 `.env.example`）：

```dotenv
XTARK_LOG_DIR=logs
XTARK_LOG_LEVEL=INFO
XTARK_LOG_RETENTION_DAYS=30
```

WSL 下也可使用绝对路径，例如 `XTARK_LOG_DIR=/home/<user>/xtark-logs`。

配置优先级：进程环境变量 > `pc/qt_client/.env` > 默认值。默认保留最近 30 个自然日的 `xtark-console-*.log`；不匹配该命名规则的文件不会被自动删除。

可选开启三路 odom 采样落盘（与 `XTARK_LOG_LEVEL` 独立，默认关闭）：

```dotenv
XTARK_LOG_ODOM=1
XTARK_LOG_ODOM_INTERVAL=1.0
```

开启后，客户端按间隔记录 `odom_raw` / `odom_base` / `odom_laser` 的 `x,y,yaw` 与速度，便于事后对照；不会把整帧 JSON 或激光点云写入日志。配置在启动时注入内存，热路径不会每帧重读 `.env`；修改后需重启客户端，或调用 `reload_odom_telemetry_settings()`。

文件落盘经 `QueueHandler` 异步写入，避免主线程在 `/mnt/d` 上同步 `flush`；日志行里的 `thread=MainThread` 表示事件产生线程，不是写文件线程。

日志同时输出到控制台和文件。`INFO` 模式下不会记录高频 JSON `TX cmd_vel`、速度命令等调试信息；需要排查控车链路时，将 `XTARK_LOG_LEVEL=DEBUG` 写入 `.env` 后重启。

实时查看当天日志：

```bash
tail -f logs/xtark-console-$(date +%F).log
```

legacy 调试台的 UI 日志面板仍正常显示；文件落盘由统一 logging 系统处理。（仅在使用 deprecated legacy 窗口时适用。）

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
  ├─ CameraRos2Panel（独立 Camera Bridge，无 RViz2）
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

- **主功能**：HTTP/MJPEG → `CameraViewport` 低延迟预览（不依赖 ROS2）。
- **Camera Bridge**（本页独立，默认**手动**启动）：从 MJPEG 解码发布
  `sensor_msgs/Image` 到 `/camera/image_raw`（约 5fps）及 `base_link→camera_link`
  静态 TF，用于 `ros2 topic hz` 等数据链验收。
- **本页不提供 RViz2**：WSL2 下摄像头相关 RViz/OpenGL 不稳定（`failed to create drawable` /
  segfault），不作为验收项；看图用 Qt 预览。机器人页 RViz2 仍用于激光/TF。
- `config/xtark_camera.rviz` 仅保留给**原生 Linux** 手工调试，不在 WSL 默认流程使用。
- 进入摄像头页**只自动连 MJPEG**；`XTARK_AUTO_CAMERA_BRIDGE=1` 才在进入页时自动启 Bridge。

### 摄像头页验收

| 项目 | 验收 |
|------|------|
| Qt MJPEG 预览 | 是 |
| 手动启 Camera Bridge 后 `ros2 topic hz /camera/image_raw` | 是 |
| 摄像头页 RViz2 / Image display | **否**（不支持作验收） |

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

位置基准：`RobotSession` 在每次连接的第一帧 `odom_base` 锁定 session 原点
（`x0/y0/yaw0`，见 `core/odom_session_origin.py`），机器人页与 ROS2 `/odom`、
RViz2 使用同一套归一化位姿；HUD 仍显示车端原始 odom。

### ROS2 / RViz2 联调（机器人页）

折叠面板「ROS2 / RViz2 联调」；进入机器人页且已连车时可自动启动 Bridge（可用
`XTARK_AUTO_BRIDGE=0` 关闭）。RViz2 **仅手动**启动。

Bridge 发布（session 坐标 + `core/robot_frames.py` 外参）：

| 话题 | 来源 |
|------|------|
| `/scan` | JSON laser_scan |
| `/odom` | JSON odom_base（session 原点） |
| `/odom_raw` / `/odom_laser` | JSON 原始值 |
| `/tf` / `/tf_static` | odom→base_link、base_link→laser |

预配置：`config/xtark_robot.rviz`（Fixed Frame=`odom`，LaserScan + TF）。摄像头见摄像头页。

**RViz2 硬验收（机器人页）**：LaserScan、`/odom` 相关 TF tree。不含 Image。

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
- 调试时在 `XTARK_LOG_LEVEL=DEBUG` 下可看到 `RobotSession velocity`、JSON `TX cmd_vel` 等链路日志；默认 `INFO` 不会高速刷屏。

长期再接：

- `Ros1GatewayBackend`：连接机器人端应用层 ROS1 gateway。
- `Ros2NativeBackend`：WSL2/ROS2 成熟后原生发布/订阅。

页面层不要直接发 ROS，也不要直接打开 TCP socket。

机器人端相机脚本保持中性：

- Android 观察：`/image_raw/compressed`
- Qt/浏览器预览：`http://192.168.1.169:8080/stream?topic=/camera/image_raw`

控车需要底盘和 JSON 网关，使用 `qt_stack.sh start`，不要只启动 `dev/camera_stack.sh`。

## legacy 调试台（deprecated，冻结）

**不要在此添加新功能。** 新控制、遥测、地图比对、SLAM 相关能力一律进 `ui/` 新 shell，算法进程将来由 PC/WSL ROS2 sidecar 承担（见 `pc/docs/控制端与ROS2硬件平台架构方案.md`）。

仅在必须对照旧 ROS2 调试行为时，可临时启用：

```bash
XTARK_ALLOW_LEGACY=1 ./run.sh --legacy
```

未设置 `XTARK_ALLOW_LEGACY=1` 时，`--legacy` 会拒绝启动。启动时会打印 `DEPRECATED` 警告。

旧窗口曾集成的能力（供 sidecar 设计参考，已迁出到架构文档 §9.3）：

- TCP JSON 连接 xtark 底盘
- 进程内 `Ros2Publisher`：`/odom_base`、`/odom`、`/base_status`、TF、`/cmd_vel` 回调
- `RosStackManager`：RViz2、slam_toolbox、Nav2 定位/导航、map save
- legacy `CameraPanel`（HTTP/MJPEG，新版已用 `MjpegStreamController` 替代）

相关代码仍保留在 `legacy/`、`mapping/`、`gateway/ros2_pub.py`，**默认启动路径不 import 它们**。

## 目录结构

```text
qt_client/
├── app.py                    # 轻量入口：参数、QApplication、单实例锁
├── main_window.py            # 默认 Shell；legacy 仅 lazy import
├── run.sh
├── backends/                 # RobotBackend 抽象和 mock / ros1 / ros2 backend 骨架
├── core/                     # RobotSession / logging_config / 状态与几何
├── data/                     # robots.json
├── gateway/                  # JSON / ROS2 网关旧调试能力
├── legacy/                   # DEPRECATED LegacyWindow（冻结，勿扩写）
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
python -m py_compile app.py main_window.py core/logging_config.py
git diff --check
```
