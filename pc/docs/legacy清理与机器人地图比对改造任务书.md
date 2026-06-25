# legacy 清理与机器人/地图比对改造任务书

本文只覆盖当前优先做的两个部分：

```text
1. legacy 第一阶段清理
2. 新架构上的“机器人”工作区 / “地图比对”模块改造
```

## 当前收口决定（2026-06-25）

本轮修改先停在以下位置：

```text
已做/可继续验收：
- legacy 入口退役与冻结。
- 机器人页 ROS2 Bridge：scan / odom / TF 发布。
- 机器人页 RViz2：仅用于 LaserScan、odom、TF 验证。
- 摄像头页 Qt MJPEG 预览。
- 摄像头页 Camera Bridge：手动发布 /camera/image_raw，用 ros2 topic 验证数据链。

暂停/不再继续投入：
- 摄像头页 RViz2 / Image display。
- 地图比对页面继续改造。
- /map、slam_toolbox、Nav2、地图保存。
```

原因：

- WSL2 下 RViz2 摄像头/OpenGL 路径已复现 `failed to create drawable` / `SIGSEGV`，不是 qt-client Python 侧能可靠修复的问题。
- 摄像头主显示应回到 Qt 内置 MJPEG 预览；ROS2 图像只作为数据链验证。
- 地图比对页当前先保持现状，不在本轮继续做 UX 或架构扩展，避免与 origin / frame / ROS2 数据链问题交叉放大。

本轮代码验收不应要求：

```text
RViz2 显示摄像头 Image
地图比对页新功能完成
slam_toolbox / Nav2 / /map 可用
```

这两步的目标不是马上接入完整 ROS2 SLAM，也不是立即物理删除所有 legacy 代码，而是先把旧入口退役、迁出可复用经验，再把当前新 Qt shell 里的机器人工作区和地图比对能力整理成后续承载面。机器人页面改造阶段应直接打通 **xtark 采集数据 -> PC / WSL ROS2 topics -> RViz2** 的验证链路；完整 SLAM / Nav2 后置。

## 0. 总体原则

### 0.1 正确顺序

推荐先做：

```text
legacy 第一阶段清理
        ↓
机器人工作区 / 地图比对模块新架构改造 + ROS2/RViz2 基础打通
        ↓
PC / WSL ROS2 sidecar 完善
        ↓
SLAM / map / Nav 接入
```

不要反过来先做“大地图 UI”或“完整 ROS2 SLAM 接入”。但机器人页面改造时应当先把 scan / odom / TF 发布到 ROS2，并能在 RViz2 里看到。这样后续 SLAM 才有可验证的数据基础。

### 0.2 术语边界

```text
qt-client GUI：负责控制、展示、交互、日志、状态观察。
PC / WSL / ROS2 工作站：负责 bridge、SLAM、Nav、RViz2、map save 等算法进程。
xtark / RK3568 / Jetson：尽量作为硬件采集平台和基础安全控制平台。
legacy：旧 Qt 调试窗口，不再作为新功能承载面。
```

## 1. legacy 第一阶段清理

### 1.1 背景

当前 `pc/qt_client` 仍保留旧调试窗口：

```text
pc/qt_client/app.py
pc/qt_client/main_window.py
pc/qt_client/legacy/legacy_window.py
```

现状要点：

- `app.py` 仍支持 `--legacy`。
- `main_window.py` 顶层导入 `LegacyWindow`。
- `legacy_window.py` 仍包含旧 ROS2 调试链路：
  - `mapping.ros_stack.RosStackManager`
  - `gateway.ros2_pub`
  - `StackPanel`
  - `NavPanel`
  - `LogPanel`
  - `ControlPanel`
  - `CameraPanel`
- legacy 中仍有可复用经验：
  - RViz2 启停
  - slam 启停
  - map save
  - localization / nav 启动
  - ROS2 调试日志

第一阶段清理的重点是：**退役入口、冻结旧 UI、迁出经验**。不是一上来粗暴删除所有 legacy 文件。

### 1.2 目标

完成后应达到：

- 默认启动只进入新 Qt shell。
- 新功能不再进入 `legacy_window.py`。
- 后续“机器人/地图比对”模块改造不依赖 legacy。
- legacy 里的 ROS2 / RViz2 / slam / map save 经验被记录到新方案中。
- 保留有限 fallback 能力，方便必要时人工回看旧行为。

### 1.3 修改范围

优先关注：

```text
pc/qt_client/app.py
pc/qt_client/main_window.py
pc/qt_client/legacy/legacy_window.py
pc/qt_client/legacy/__init__.py
pc/qt_client/README.md
pc/docs/
```

只做审计和经验迁移，不急删：

```text
pc/qt_client/mapping/ros_stack.py
pc/qt_client/gateway/ros2_pub.py
pc/qt_client/config/slam_toolbox_xtark.yaml
pc/qt_client/config/nav2_xtark.yaml
pc/qt_client/ui/widgets/stack_panel.py
pc/qt_client/ui/widgets/nav_panel.py
pc/qt_client/ui/widgets/log_panel.py
pc/qt_client/ui/widgets/status_panel.py
pc/qt_client/ui/widgets/control_panel.py
pc/qt_client/ui/widgets/camera_panel.py
```

说明：上面这些文件可能包含旧经验或仍被其他页面复用。第一阶段不要按文件名直接删除。

### 1.4 实施步骤

#### 步骤 1：给 legacy 明确打标

建议：

- 在 `legacy/legacy_window.py` 顶部注释中标明 deprecated。
- 在 `README.md` 中说明 legacy 只作为历史调试窗口。
- 在新方案文档中记录 legacy 不再承载新功能。

#### 步骤 2：软隐藏 legacy 入口

建议策略：

- 默认启动路径保持新 shell。
- `--legacy` 不再出现在普通使用文档中。
- 如果保留 `--legacy`，启动时必须打印明显 warning。
- 可选：将 `--legacy` 改为需要环境变量确认，例如 `XTARK_ALLOW_LEGACY=1`，防止误用。

注意：如果短期还需要旧窗口对照，不要直接删除 `--legacy`。

#### 步骤 3：解除默认路径对 legacy 的强耦合

当前 `main_window.py` 顶层导入：

```python
from legacy.legacy_window import LegacyWindow
```

建议后续改为 lazy import，只在 `legacy_ui=True` 时导入旧窗口。这样默认新 shell 启动不需要加载 legacy 依赖。

验收点：

- 不使用 `--legacy` 时，新 shell 启动不应依赖 `legacy_window.py`。
- `legacy_window.py` 中的 ROS2 旧依赖不应影响默认启动。

#### 步骤 4：迁出 legacy 中可复用经验

需要从 legacy 里提取并记录：

- RViz2 启动方式。
- slam 启动方式。
- map save 命令和输出路径。
- localization / nav 启动参数。
- 旧 ROS2 pub / bridge 的 topic 约定。
- 旧日志中对排错有价值的信息。

迁移目标不是复制旧 UI，而是形成后续 PC / WSL ROS2 sidecar 的设计输入。

推荐记录位置：

```text
pc/docs/控制端与ROS2硬件平台架构方案.md
pc/docs/legacy清理与机器人地图比对改造任务书.md
后续新建的 PC / WSL ROS2 sidecar 文档
```

#### 步骤 5：冻结 legacy 新功能入口

后续新增需求不得进入：

```text
pc/qt_client/legacy/
```

如确实需要复用旧逻辑，应迁移为独立 service / sidecar / backend，而不是继续扩写 legacy window。

### 1.5 验收标准

必须满足：

- 默认运行 qt-client 进入新 shell。
- 不使用 `--legacy` 时，不加载旧 ROS2 调试窗口。
- README 或文档明确 legacy 已 deprecated。
- legacy 中 RViz2 / slam / map save / nav 的可复用经验已记录。
- 新“机器人/地图比对”改造任务不依赖 legacy。

建议验证：

```text
python -m py_compile pc/qt_client/app.py pc/qt_client/main_window.py pc/qt_client/legacy/__init__.py
git diff --check -- pc/qt_client/app.py pc/qt_client/main_window.py pc/qt_client/legacy/
```

当前 `pc/qt_client/tests/` 无测试文件时，不要用 `unittest discover` 代替验收。

### 1.6 不要做什么

第一阶段不要做：

- 不要一刀切删除整个 `pc/qt_client/legacy/`。
- 不要删除 `mapping/ros_stack.py` 和 `gateway/ros2_pub.py`，除非确认经验已迁出且新替代方案可用。
- 不要把旧 StackPanel / NavPanel 直接塞进新 shell。
- 不要继续给 legacy 加地图、SLAM、导航新功能。
- 不要让 legacy 清理顺手改动 Android 栈或机器人端脚本。

### 1.7 第一阶段完成记录（2026-06-24）

已落地：

- [x] `legacy/legacy_window.py`、`legacy/__init__.py` 标明 deprecated / frozen
- [x] 默认 `./run.sh` 仅进新 shell；`main_window.py` 对 `LegacyWindow` **lazy import**
- [x] `--legacy` 需 `XTARK_ALLOW_LEGACY=1`，启动打印 `DEPRECATED` 警告；`--help` 不展示 `--legacy`
- [x] README 与架构文档 §9.3 记录 legacy ROS2 可复用经验
- [x] 明确冻结：`pc/qt_client/legacy/` 不再接受新功能
- [x] legacy 拒绝路径在 `QApplication` / `QLockFile` 之前 gate，避免占锁未释放
- [x] `app.py` 警告文案使用 ASCII，避免编码乱码

未做（留待 sidecar / 新架构替代后）：物理删除 `legacy/`、`mapping/ros_stack.py` 等。

**第二部分（机器人工作区 / 地图比对模块改造）尚未开始。**

## 2. 机器人工作区 / 地图比对模块新架构改造

### 2.1 背景

当前新 Qt shell 已经有机器人工作区结构：

```text
pc/qt_client/ui/pages/robot_workspace_page.py
pc/qt_client/ui/pages/robot_page.py
pc/qt_client/ui/pages/odom_compare_page.py
pc/qt_client/ui/widgets/robot_hud_bar.py
pc/qt_client/ui/widgets/robot_side_nav.py
pc/qt_client/ui/widgets/odom_compare_view.py
pc/qt_client/core/odom_compare_controller.py
pc/qt_client/core/robot_session.py
pc/qt_client/core/robot_telemetry_binder.py
```

当前工作区已经有：

- `robot` 页面。
- `odom_compare` 页面。
- `camera` 页面。
- `slam_map` / `gps_map` 占位页。
- HUD 状态条。
- 侧边导航。
- `RobotSession` 统一连接、遥控、遥测。
- `RobotTelemetryBinder` 负责把 session 遥测绑定到 UI。

这说明新架构承载面已经存在，下一步不应再回到 legacy，而应在这套 shell 上整理“机器人”和“地图比对”。

### 2.2 目标

完成后应达到：

- “机器人”工作区成为后续 Qt 主线承载面。
- 当前 odom compare / 地图比对能力纳入新工作区，不依赖 legacy。
- 里程计、激光里程计、后续 ROS2 map pose / slam pose 可以逐步接入同一比对框架。
- 当前功能仍可用于验证 xtark 采集链路。
- 机器人页面直接打通 PC / WSL ROS2 基础链路：xtark 的 scan / odom / TF 能发布为 ROS2 标准话题，并能在 RViz2 中显示。
- 为后续 PC / WSL ROS2 sidecar 输出的 map / pose / trajectory 预留接口。

### 2.2.1 机器人页面新增功能

“机器人”页面应新增一个独立区域，建议命名为：

```text
ROS2 / RViz2 联调
```

第一版功能只做数据链和可视化闭环，不做完整 SLAM / Nav2：

```text
xtark JSON gateway
        ↓
RobotSession / sidecar input
        ↓
PC / WSL ROS2 bridge sidecar
        ↓
/scan / odom topics / tf / tf_static
        ↓
RViz2
```

页面建议展示：

- ROS2 环境状态：
  - `rclpy` 是否可导入。
  - ROS2 distro / domain id。
  - sidecar 是否运行。
- xtark 数据源状态：
  - JSON gateway 是否连接。
  - 最近一次 `laser_scan` 时间。
  - 最近一次 `odom_base` / `odom_raw` / `odom_laser` 时间。
- ROS2 发布状态：
  - `/scan` 发布频率。
  - `/odom_raw` 发布频率。
  - `/odom` 发布频率。
  - `/odom_laser` 发布频率。
  - `/tf` / `/tf_static` 是否已发布。
- RViz2 控制：
  - 启动 RViz2。
  - 停止 RViz2。
  - 显示 RViz2 进程状态。
  - 显示最近错误，例如缺 `rclpy`、缺 `numpy`、缺 `rviz2`、无 `/scan`。

页面第一版按钮建议：

```text
[启动 ROS2 Bridge] [停止]
[启动 RViz2]      [停止]
[刷新 topic 状态]
```

可选但推荐：

```text
[复制诊断命令]
```

复制内容类似：

```bash
ros2 topic list
ros2 topic hz /scan
ros2 topic hz /odom_raw
ros2 run tf2_tools view_frames
rviz2
```

重要边界：

- RViz2 可以从机器人页面启动，但应由独立 manager / sidecar 管理，不复用 legacy `StackPanel`。
- ROS2 bridge 可以由机器人页面调度，但不应跑在 Qt GUI 主线程里。
- 机器人页面只显示 sidecar 状态和结果，不直接在 UI 线程里 `spin` ROS2。
- 第一版不启动 `slam_toolbox`，不启动 Nav2，不发布 `/map`。

### 2.3 模块边界

推荐边界：

```text
RobotWorkspacePage
    负责页面组织、HUD、侧边导航、session 注入。

RobotPage
    负责机器人状态总览、基础控制、遥测摘要、ROS2/RViz2 联调入口。

OdomComparePage / 后续 MapComparePage
    负责轨迹/位姿/地图比对视图。

OdomCompareController
    负责数据流归一、零点、轨迹缓存、超时状态。

OdomCompareView
    负责绘制，不直接接触 gateway / ROS2 / socket。

RobotSession
    负责连接、命令、遥测信号。

RobotTelemetryBinder
    负责 session 到 UI 的绑定。

Ros2BridgeSidecar / Ros2BridgeManager（建议新增）
    负责把 xtark JSON 采集数据发布到 PC / WSL ROS2 标准话题，并上报 topic/错误状态。

RvizProcessManager（建议新增）
    负责启动/停止 RViz2，不依赖 legacy StackPanel。
```

不要让页面直接依赖：

```text
legacy_window.py
mapping.ros_stack.py
gateway.ros2_pub.py
ROS2 node spin loop
```

允许页面通过独立 manager 调度：

```text
ROS2 bridge sidecar lifecycle
RViz2 process lifecycle
topic status refresh
diagnostic command copy
```

### 2.4 建议实现路线

#### 步骤 1：整理“机器人”工作区职责

检查并明确：

```text
robot_workspace_page.py
robot_page.py
robot_hud_bar.py
robot_side_nav.py
robot_telemetry_panel.py
manual_control_strip.py
```

目标：

- 工作区只做页面组织和 session 注入。
- 机器人页只做状态总览和基础操作。
- 手动遥控能力复用统一控件。
- HUD 与详情面板都从 `RobotTelemetryBinder` 获得数据。
- ROS2/RViz2 联调区域放在 `robot` 页面或机器人工作区内的独立子面板，不进入 legacy。

#### 步骤 1.5：打通 ROS2 / RViz2 基础链路

新增 PC / WSL ROS2 bridge sidecar，第一版只负责把 xtark 采集数据发布为标准 ROS2 话题，并让 RViz2 能看到。

建议发布：

```text
/scan
/odom_raw
/odom
/odom_laser
/tf
/tf_static
/robot_status
/battery
/camera/image_raw   # 摄像头页 Camera Bridge：MJPEG 解码 rgb8，约 5fps；非机器人 Bridge
```

session 原点（`core/odom_session_origin.py`）：连接后首帧 `odom_base` 的 `x0/y0/yaw0`；
`/odom` 与 Qt 机器人页使用同一归一化位姿。外参与 frame 名统一在 `core/robot_frames.py`。

**页面分工**：机器人页 Bridge → scan/odom/TF + **RViz2（激光/TF）**；摄像头页
`CameraRos2BridgeManager` → `/camera/image_raw` + TF，**无 RViz2 入口**。

最低验收：

```text
ros2 topic list      机器人 Bridge：/scan /odom_raw /odom /odom_laser
ros2 topic hz /scan  有稳定频率
ros2 topic hz /camera/image_raw  摄像头页手动启 Camera Bridge 且 :8080 有流时有频率
RViz2（仅机器人页） LaserScan + odom→base_link→laser TF（xtark_robot.rviz）
摄像头页             Qt MJPEG 预览 + topic 验收；RViz2 不作验收（WSL2 OpenGL 不稳定）
Qt 页面              bridge 运行状态与最近错误
```

实现建议：

- 新增独立 sidecar / manager，不在 Qt GUI 主线程 `spin` ROS2。
- 机器人 Bridge 输入复用 `RobotSession` JSON 遥测；RViz2 仅机器人页手动启停。
- 摄像头图像由**摄像头页** `CameraRos2BridgeManager` 拉 HTTP MJPEG，默认手动启动。
- WSL2 下不在摄像头页提供 RViz2；主看图用 Qt 预览，ROS2 作数据链验证。
- 如果缺依赖，例如 `No module named 'numpy'`、`rclpy` 不存在、`rviz2` 不存在，机器人页面要显示明确错误。

本步骤不做：

- 不启动 `slam_toolbox`。
- 不启动 Nav2。
- 不发布 `/map`。
- 不做地图保存。

#### 步骤 2：把当前 odom compare 作为地图比对的第一阶段

现阶段不要急着做完整 `/map` 渲染。先把当前 odom compare 明确为“地图比对”的基础验证页。

建议 UI 语义：

```text
页面名：地图比对 / 里程计对照
当前阶段：对比 odom_base、odom_raw、odom_laser
后续阶段：接入 ROS2 slam pose、map pose、scan overlay
```

可先保留内部 page id：

```text
odom_compare
```

避免为了改名造成大量无价值 churn。

#### 步骤 3：补清楚数据源模型

当前数据源：

```text
odom_base   机器人融合 / base odom
odom_raw    编码器原始 odom
odom_laser  激光里程计 odom
```

后续预留：

```text
slam_pose
map_pose
ros2_odom
scan_overlay
map_grid
```

建议 controller 内部不要写死 UI 文案，改成更清晰的数据源注册/状态模型，方便未来加 ROS2 sidecar 输出。

#### 步骤 4：修正地图比对 UX

当前比对页的一个关键行为是：未归零时不画轨迹。这是合理机制，但需要更清楚的 UI 提示。

建议：

- 未归零时，在画布上显示“请先重新归零后开始比对”。
- 归零按钮旁显示当前 origin 状态。
- 数据在线但未归零时，明确区分“有数据”和“未开始记录轨迹”。
- 轨迹为空时不要让用户误以为绘制坏了。

#### 步骤 5：为后续 ROS2 map 接入预留接口

只预留接口，不接真实 ROS2 SLAM。

可以设计但不实现重逻辑：

```text
MapCompareSource
MapPoseSample
MapGridSnapshot
ScanOverlayFrame
```

或者先在文档/注释中定义输入结构，等 PC / WSL ROS2 sidecar 完成后再接。

#### 步骤 6：保持控制链路安全

地图比对页里的手动控制必须继续走：

```text
ManualControlStrip
    ↓
RobotSession
    ↓
RobotBackend
    ↓
xtark JSON gateway
```

不要绕过 session 直接发 socket 或 ROS2 命令。

### 2.5 建议修改文件

优先修改：

```text
pc/qt_client/ui/pages/robot_workspace_page.py
pc/qt_client/ui/pages/robot_page.py
pc/qt_client/ui/pages/odom_compare_page.py
pc/qt_client/ui/widgets/odom_compare_view.py
pc/qt_client/core/odom_compare_controller.py
pc/qt_client/core/robot_telemetry_binder.py
pc/qt_client/core/ros2_bridge_sidecar.py        # 建议新增
pc/qt_client/core/rviz_process_manager.py       # 建议新增
pc/qt_client/ui/widgets/ros2_bridge_panel.py    # 建议新增
```

可能涉及：

```text
pc/qt_client/ui/widgets/robot_hud_bar.py
pc/qt_client/ui/widgets/robot_side_nav.py
pc/qt_client/ui/widgets/robot_telemetry_panel.py
pc/qt_client/ui/widgets/manual_control_strip.py
pc/qt_client/core/robot_session.py
pc/qt_client/tests/
```

暂不应涉及：

```text
pc/qt_client/legacy/
pc/qt_client/mapping/ros_stack.py
pc/qt_client/gateway/ros2_pub.py
xtark/scripts/
android/
```

### 2.6 验收标准

功能验收：

- 默认进入新 Qt shell。
- 能打开机器人工作区。
- `robot` 页面状态正常。
- `robot` 页面提供 ROS2 bridge 与 RViz2 状态区。
- xtark 的 `laser_scan` 能发布到 ROS2 `/scan`。
- xtark 的 `odom_base` / `odom_raw` / `odom_laser` 能发布到 ROS2 odom topics。
- TF 至少包含 `odom -> base_link` 和 `base_link -> laser`。
- RViz2 能显示 `/scan` 与 TF tree。
- 缺少 ROS2 依赖时，页面显示明确错误，不静默失败。
- `odom_compare` 页面仍能接收：
  - `odom_base`
  - `odom_raw`
  - `odom_laser`
- 点击重新归零后，轨迹能正常绘制。
- 未归零时 UI 明确提示，不再像“绘制坏了”。
- 手动控制仍通过 session/backend 发送。
- 关闭页面或切换机器人时，不出现重复 signal 绑定或异常。

架构验收：

- 新模块不 import `legacy_window.py`。
- 新模块不直接依赖 `RosStackManager`。
- 新模块可以通过新 manager 启动 RViz2，但不得复用 legacy `StackPanel` / `RosStackManager`。
- 新模块不启动 `slam_toolbox` / Nav2。
- 页面只消费 session / binder / controller 输出。
- 为后续 ROS2 map / pose 接入留有接口或清晰扩展点。

测试建议：

```text
python -m py_compile pc/qt_client/app.py pc/qt_client/main_window.py
python -m py_compile pc/qt_client/ui/pages/robot_workspace_page.py
python -m py_compile pc/qt_client/ui/pages/odom_compare_page.py
python -m py_compile pc/qt_client/ui/widgets/odom_compare_view.py
python -m unittest discover -s pc/qt_client/tests -v
```

如能做 Qt offscreen 测试，建议增加：

- 未归零状态渲染提示。
- zero 后轨迹追加。
- 页面切换后 signal 不重复。
- 没有 session 时页面仍可显示占位状态。

### 2.7 不要做什么

本阶段不要做：

- 不要接入真实 `/map`。
- 不要启动 `slam_toolbox`。
- 不要接 Nav2。
- 不要让 Qt GUI 直接跑 ROS2 node 主循环。
- 不要把 legacy 的 StackPanel / NavPanel 直接搬到新 shell。
- 不要删除 Android 功能。
- 不要改 xtark 机器人端栈。
- 不要重命名 `json_gateway` 或替换已验证控制链路。

## 3. 两部分完成后的交付物

完成这两个部分后，应交付：

```text
1. legacy 已退役入口，且可复用经验已迁出。
2. 新 Qt shell 中“机器人”工作区职责清晰。
3. 当前地图比对 / 里程计对照模块可作为后续 ROS2 map 接入的承载面。
4. 默认运行路径不依赖 legacy。
5. 文档说明后续 PC / WSL ROS2 sidecar 应如何接入。
```

完成后，下一阶段才进入：

```text
PC / WSL ROS2 数据接入 sidecar
RViz2 验证 scan / odom / tf
slam_toolbox 建图
qt-client GUI 接 map / pose / scan / trajectory
```

## 4. 给执行者的简短结论

这两个任务的核心不是“做新地图”，而是先把地基打平：

```text
legacy 不再干扰主线。
新机器人工作区成为唯一承载面。
当前 odom compare 成为地图比对的第一阶段验证工具。
算法仍放在 qt-client 所在 PC / WSL / ROS2 工作站侧。
硬件平台只负责采集和基础安全控制。
```
