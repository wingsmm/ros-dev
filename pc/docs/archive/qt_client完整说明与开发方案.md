# xtark 上位机客户端：完整说明与开发方案

本文档说明 `pc/qt_client`（xtark Console）的定位、与 ROS 手机 App 的差异、当前能力、缺口，以及分阶段开发路线。与 `建图联调现状与问题记录.md`、`WSL2统一栈运行与调试.md` 配套阅读。

---

## 0. 2026-06-17 当前实现快照

`pc/qt_client` 已从单文件主窗口演进为“新版 Shell + legacy 调试台”双入口结构。

默认启动：

```bash
./run.sh
./run.sh --no-ros
```

进入新版 Shell：

```text
机器人选择页
  ├─ 添加/编辑/删除机器人
  ├─ 连接机器人（当前默认 mock backend）
  └─ 进入机器人工作区

机器人工作区
  ├─ 左侧飞入式导航
  ├─ 总览（占位）
  ├─ 摄像头（已实现 HTTP/MJPEG MVP）
  ├─ 机器人（占位）
  ├─ SLAM 地图（占位）
  ├─ GPS 地图（占位）
  ├─ 设置（占位）
  └─ 关于（占位）
```

旧调试台仍保留：

```bash
./run.sh --legacy
```

当前架构：

```text
app.py
  └─ main_window.create_main_window()
       ├─ ShellMainWindow（默认）
       │    └─ RobotShellController
       │         └─ RobotSession -> RobotBackend
       └─ LegacyWindow（--legacy）
```

相机当前状态：

- 新版 `CameraPage` 已接入机器人工作区。
- `CameraPage` 与 legacy `CameraPanel` 复用 `MjpegStreamController`。
- 当前 HTTP/MJPEG 默认 URL：`http://192.168.1.168:8080/stream?topic=/camera/image_raw`。
- 已实测 `./run.sh --no-ros` 下进入摄像头页自动出图，FPS 约 25。
- 长期仍应通过 `ros1_bridge` / backend 对齐 Android 的 `/image_raw/compressed` ROS 话题模型。

控制桥接原则：

- 页面层统一只调用 `RobotSession`，不要直接发 ROS、JSON 或 socket。
- 短期真车控制优先接 `JsonGatewayBackend`，复用 legacy JSON 控制链路。
- 手动遥控采用 dead-man 模式：按住立即发速度，并以约 10Hz 通过 `RobotSession` 连续发送；松开按钮或点击停止调用 `stop_motion()`。
- 调试日志需能看到 `RobotSession velocity`、`JSON velocity sent=True`、底层 `TX ...`，用于定位 Qt / TCP / 机器人端链路断点。
- 中期补机器人端 `Ros1GatewayBackend`，让 ROS1 复杂性留在机器人端。
- 长期再接 `Ros2NativeBackend` / `ros1_bridge`，对齐 Android ROS 话题语义。

推荐数据流：

```text
CameraPage / OverviewPage / RobotControlPage
  -> ManualControlStrip
  -> RobotSession
  -> RobotBackend
  -> Mock / JSON / ROS1 Gateway / ROS2 Native
```

机器人端日常入口推荐：

```bash
~/ros_ws/scripts/robot_stack.sh start
~/ros_ws/scripts/robot_stack.sh status
~/ros_ws/scripts/robot_stack.sh stop
```

该脚本一把拉起底盘、相机和 JSON 网关；只观察相机时才单独用 `camera_stack.sh`。

后文部分路线和模块名保留历史设计语境；若与本节冲突，以本节和当前代码为准。

---

## 1. 我们在做什么

`qt_client` 不是手机 App 的移植版，而是 **WSL2 统一栈的日常入口**，同时承担两个角色：

- **GUI 程序**：连接、状态显示、遥控、建图栈 / 导航栈启停。
- **ROS 网关**：JSON ↔ ROS2（`/odom_base`、`/odom`、TF、`/cmd_vel` → JSON）。

### 1.1 系统架构

```text
┌─────────────────────────────────────────────────────────────────┐
│  RK3568 底盘                                                     │
│  JSON :8765  ──odom/cmd_vel/status──►                          │
│  /scan (雷达)                                                    │
└───────────────┬─────────────────────────────┬───────────────────┘
                │                             │
                ▼                             ▼
┌─────────────────────────── WSL2 / PC ───────────────────────────┐
│  qt_client (Qt GUI)                                              │
│    ├─ gateway/json_client.py    TCP JSON 客户端                  │
│    ├─ gateway/ros2_pub.py       JSON ↔ ROS2 桥                   │
│    ├─ mapping/ros_stack.py      SLAM / Nav2 / RViz 进程编排      │
│    └─ ui/widgets/*              控制面板、建图/导航面板          │
│                                                                  │
│  ROS2 栈（子进程）                                               │
│    slam_toolbox | map_server | AMCL | Nav2 | rviz2              │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 与手机 App 的本质区别

| 维度 | 手机 App（android_apps / RobotCA） | 咱们 qt_client |
|------|-----------------------------------|----------------|
| 运行环境 | Android，手机当 ROS 节点 | PC + WSL2 + Qt |
| 连底盘 | 直连 ROS Master（ROS1） | TCP JSON → 再桥 ROS2 |
| 导航栈 | `move_base`（ROS1） | **Nav2**（ROS2 Humble） |
| 地图存储 | world_canvas 云服务 | 本地 `maps/*.pgm` + `.yaml` |
| 栈管理 | **不管** SLAM/导航进程 | GUI **一键启停**整条栈 |
| 可视化 | App 内嵌地图/激光/相机 | 主要靠外开 RViz2 |

**结论：** 咱们在「栈编排 + JSON 网关 + Nav2 + 麦轮」上已经**超过**老手机 App；在「一体化可视化 + 触屏交互体验」上**明显落后**。开发方向应是：**补齐体验短板，而不是照搬手机架构**。

### 1.3 参考源码

| 仓库 | 用途 | 说明 |
|------|------|------|
| [rosjava/android_apps](https://github.com/rosjava/android_apps) | 建图导航 | 含 `make_a_map`、`map_nav`、`map_manager`、`teleop` |
| [SCCapstone/RobotCA](https://github.com/SCCapstone/RobotCA) | 遥控 | 摇杆、激光、HUD、多机管理（已停维护） |

---

## 2. 当前能力清单

### 2.1 已实现且可用

| 模块 | 能力 | 关键文件 |
|------|------|----------|
| 连接 | TCP JSON，Host/Port，连接状态 | `gateway/json_client.py` |
| 遥控 | 按钮 + WASD/QE 横移，10 Hz 发 cmd_vel | `ui/widgets/control_panel.py`, `app.py` |
| 网关 | JSON → `/odom`、`/odom_base`、TF、`/base_status` | `gateway/ros2_pub.py` |
| 建图 | 启停 slam_toolbox、RViz2、一键建图栈 | `mapping/ros_stack.py` |
| 存图 | `map_saver_cli` → `maps/`，自动填导航路径 | `mapping/ros_stack.py`, `ui/widgets/stack_panel.py` |
| 导航 | map_server + AMCL + Nav2 分步/一键启停 | `mapping/ros_stack.py`, `ui/widgets/nav_panel.py` |
| 安全 | 导航时禁手动；急停取消 Nav2 目标 | `app.py`, `gateway/ros2_pub.py` |
| 互斥 | SLAM ↔ 导航自动互停 | `mapping/ros_stack.py` |
| 配置 | xtark 专用 SLAM/Nav2 YAML（麦轮 DWB） | `config/slam_toolbox_xtark.yaml`, `config/nav2_xtark.yaml` |

### 2.2 已实现但体验不足

- 设目标点、初始位姿：**必须开 RViz2 手动点**。
- 看地图/激光/路径：**没有内嵌视图**，全靠 RViz。
- 选地图：手输 yaml 路径，**无文件浏览器/列表**。
- 导航状态：只有「进程运行中」，**无进度/失败原因**。
- 建图前检查：文档有 checklist，**GUI 未自动化**。

### 2.3 联调阶段阻塞项

当前地图能证明「系统跑通」，**不宜直接当最终导航图**。根因主要是（详见 `建图联调现状与问题记录.md` 第 8 节）：

1. USB 雷达设备名不固定（A1）
2. DDS 跨设备不稳定（A2）
3. 雷达外参未实测（B1）
4. 底盘 odom 未标定（B2）
5. 建图运动策略与地图覆盖率（C1）

**开发新功能前，应优先完成 B 阶段标定**，否则 GUI 做得再漂亮，地图和导航质量仍上不去。

---

## 3. 与手机 App 的功能差距

### 3.1 android_apps（建图导航）

| 功能 | 手机 App | 咱们 | 备注 |
|------|:--------:|:----:|------|
| 遥控开车建图 | ✅ 虚拟摇杆 | ✅ 按钮+键盘+横移 | 咱们支持麦轮 |
| 保存地图 | ✅ world_canvas | ✅ 本地 map_saver | 存储方式不同 |
| 加载地图导航 | ✅ 列表选图 | ✅ yaml 路径启动 | 咱们缺列表 UI |
| 设导航目标 | ✅ 地图长按拖拽 | ⚠️ 仅 RViz | **核心差距** |
| 设初始位姿 | ✅ 地图长按拖拽 | ⚠️ 仅 RViz | **核心差距** |
| 内嵌地图/激光/路径 | ✅ | ❌ | **核心差距** |
| 摄像头 | ✅ | ✅ Phase 0 | PC 当前通过 HTTP/MJPEG 看图；长期仍需 ROS 话题对齐 |
| 启停 SLAM/Nav2 | ❌ | ✅ | 咱们优势 |
| Nav2 全栈 | ❌ | ✅ | 咱们优势 |

### 3.2 RobotCA + teleop（遥控）

| 功能 | 手机 App | 咱们 | 备注 |
|------|:--------:|:----:|------|
| 摇杆遥控 | ✅ | ❌ | Phase 4 |
| 倾斜传感器 | ✅ | ❌ | 暂不做 |
| 激光显示 | ✅ | ❌ | Phase 2 |
| 摄像头 | ✅ | ✅ Phase 0 | 新版 CameraPage 已实现 HTTP/MJPEG MVP |
| HUD 仪表盘 | ✅ | 部分 | 有连接/状态，无速度表 |
| 多机器人管理 | ✅ | ❌ | 暂不做 |
| 自主路点/随机走 | ✅ | ❌ | 用 Nav2 替代 |
| JSON 底盘协议 | ❌ | ✅ | 咱们优势 |
| Nav2 cmd_vel 回传 | ❌ | ✅ | 咱们优势 |

### 3.3 差距矩阵（开发优先级参考）

| 功能 | android_apps | RobotCA | 咱们 | 建议阶段 |
|------|:---:|:---:|:---:|----------|
| 虚拟摇杆 | ✅ | ✅ | ❌ | Phase 4 |
| 内嵌地图显示 | ✅ | 部分 | ❌ | **Phase 2** |
| 地图点选目标/位姿 | ✅ | 部分 | ❌ | **Phase 3** |
| 激光实时显示 | ✅ | ✅ | ❌ | Phase 2 |
| 摄像头 | ✅ | ✅ | ❌ | Phase 5 |
| 地图列表管理 | ✅ | ❌ | ❌ | Phase 1 |
| 启停 SLAM/Nav2 | ❌ | ❌ | ✅ | 保持 |
| JSON 底盘桥 | ❌ | ❌ | ✅ | 保持 |
| 麦轮横移 | ❌ | ❌ | ✅ | 保持 |

---

## 4. 开发原则

1. **先质量、后体验**：标定/DDS 不过，不做大 UI 投入。
2. **复用 ROS，少重复造轮子**：内嵌视图订阅现有 topic，不另起 SLAM/Nav2。
3. **RViz 作后备**：内嵌地图初期与 RViz 并行，不一次替换。
4. **最小可用增量**：每阶段可独立验收、可回退。
5. **不移植 rosjava**：不做 Android/ROS1；坚持 Qt + ROS2 + JSON。
6. **不引入 world_canvas**：继续本地 `maps/` 文件体系。

---

## 5. 分阶段开发方案

### 5.1 总览

```text
Phase 0  联调收尾（标定 + 地图质量）     ← 当前最优先，无新 GUI 大功能
Phase 1  工程化（自检 + 地图管理）       ← 约 1~2 周
Phase 2  内嵌可视化（地图 + 激光）      ← 约 2~3 周，体验分水岭
Phase 3  GUI 导航交互（点目标/位姿）    ← 约 1~2 周，对齐手机 App 核心
Phase 4  遥控增强（摇杆 + 状态反馈）    ← 约 1 周
Phase 5  可选（相机、导航进度、多点）    ← 按需
```

---

### Phase 0：联调收尾（必须先做）

**目标：** 产出一张可用于 Nav2 的地图，打通真机导航验收。

**任务（来自 `建图联调现状与问题记录.md` 第 8 节）：**

| 步骤 | 内容 | 产出 |
|------|------|------|
| A1 | udev 固定雷达设备名 | 雷达稳定 `/scan` |
| A2 | DDS/网络固化 | 跨设备 topic 稳定 |
| B1 | 实测 `base_link → laser` 外参 | 更新 `gateway/ros2_pub.py` 静态 TF |
| B2 | odom 直行/横移/转角标定 | 必要时 scale 修正 |
| C1 | 按标准流程重建图并保存 | `maps/` 下可用导航图 |
| — | Nav2 真机低速导航验收 | 文档记录通过标准 |

**验收标准：**

- `/scan` ≥ 10 Hz，`/odom` 稳定，TF 链完整。
- 保存地图 `known ratio` 明显提升（相对当前约 15%）。
- Nav2 能完成：设初始位姿 → 设目标 → 车到点（低速）。

**本阶段不改大架构**，顶多：

- 根据 B1 改 `ros2_pub.py` 里激光外参。
- 根据 B2 在网关侧加 odom scale（有标定数据再做）。

---

### Phase 1：工程化与运维体验（约 1~2 周）

**目标：** 降低每次联调的人工成本，减少「忘了检查什么」。

#### 1.1 建图前自检按钮

**新增：** `mapping/preflight.py` + `StackPanel` 上「建图检查」按钮。

自动检测并中文提示：

```text
/scan 频率
/odom_base 或 /odom 频率
TF: odom→base_link, base_link→laser
/map 是否已有（建图前应为无或可选忽略）
JSON 连接与 base_status
```

实现：短时 `ros2 topic hz` 或 rclpy 订阅计数 + `tf2` 查询，5~10 秒内出报告。

#### 1.2 地图文件管理

**新增：** `ui/widgets/map_browser.py`

- `QFileDialog` / 列表展示 `maps/*.yaml`。
- 点击选中 → 填入 `NavPanel.map_yaml_edit`。
- 显示 `.pgm` 缩略图（可选）。
- 删除/重命名（带确认）。

#### 1.3 RViz 预设配置

**新增：** `config/xtark_mapping.rviz`、`config/xtark_nav.rviz`

`mapping/ros_stack.py` 启动 RViz 时带 `-d` 参数，固定显示 `/map`、`/scan`、TF、Nav2 相关层。

#### 1.4 导航前自检

扩展自检：AMCL 是否收到 `/map`，`/scan` 与 costmap 是否更新。

**Phase 1 验收：**

- [ ] 一键自检，失败项明确可行动。
- [ ] 地图可从列表选，不必手打路径。
- [ ] RViz 开箱即有正确图层。

---

### Phase 2：内嵌可视化（约 2~3 周，核心）

**目标：** 在 Qt 内看到地图和激光，减少对 RViz 的依赖（对齐手机 App 最大短板）。

#### 2.1 技术选型

| 方案 | 优点 | 缺点 | 建议 |
|------|------|------|------|
| **A. rclpy 订阅 + QPainter 自绘** | 无新依赖，与现有架构一致 | 需自己处理 map/scan 坐标 | **推荐** |
| B. 嵌入 rviz2 渲染 | 功能全 | Qt 嵌入复杂，体积大 | 不推荐 |
| C. Web 前端 + rosbridge | 灵活 | 多一层服务 | 后期可选 |

#### 2.2 模块设计

```text
pc/qt_client/
├── viz/
│   ├── __init__.py
│   ├── map_subscriber.py    # 订阅 OccupancyGrid /map
│   ├── scan_subscriber.py   # 订阅 LaserScan /scan
│   ├── tf_cache.py          # 缓存 map←odom←base_link←laser
│   └── map_canvas.py        # QWidget：绘制栅格 + 激光 + 机器人
└── ui/widgets/
    └── map_view_panel.py    # 工具栏：缩放、跟随机器人、图层开关
```

**`map_canvas.py` 第一版能力：**

- 显示 `/map` 灰度栅格。
- 叠加 `/scan` 点（变换到 map 坐标系）。
- 画机器人位置（来自 TF `map → base_link`）。
- 鼠标滚轮缩放、拖拽平移。
- 「跟随机器人」开关。

**与现有代码集成：**

- 在 `gateway/ros2_pub.py` 同进程用 rclpy 增加订阅，或扩展现有 `Ros2Publisher`。
- `app.py` 左侧/中间加 `MapViewPanel`，与 `ControlPanel` 用 `QSplitter` 布局。

#### 2.3 第二版叠加（导航时）

- 全局路径 `/plan` 或 Nav2 plan topic。
- 局部 costmap（可选，性能允许再做）。

**Phase 2 验收：**

- [ ] 建图时 GUI 内实时看到地图扩大、激光扫到墙。
- [ ] 导航时能看到机器人在地图上的位置。
- [ ] 不启 RViz 也能完成「看图」。

---

### Phase 3：GUI 导航交互（约 1~2 周）

**目标：** 在 `MapCanvas` 上完成 RViz 的「2D Goal Pose」「2D Pose Estimate」，对齐 android_apps `map_nav`。

#### 3.1 交互模式

| 模式 | 操作 | 发布 |
|------|------|------|
| 设初始位姿 | 长按 + 拖拽朝向 | `/initialpose`（`PoseWithCovarianceStamped`） |
| 设导航目标 | 长按 + 拖拽朝向 | Nav2 `NavigateToPose` action 或 `/goal_pose` |

参考 android_apps 的 `MapPosePublisherLayer`：长按落点，移动定朝向，松手发布。

#### 3.2 UI 状态机

```text
[空闲] --点「设位姿」--> [位姿模式] --松手发布--> [空闲]
[空闲] --点「设目标」--> [目标模式] --松手发布--> [导航中]
[导航中] --急停--> [空闲]
```

#### 3.3 导航状态反馈

**新增：** `nav/nav_status.py`

订阅：

- `nav2_msgs/action/NavigateToPose` feedback（剩余距离、预计时间）。
- behavior tree 或 action status。

在 `NavPanel` 显示：`规划中 / 行进中 / 到达 / 失败（原因）`。

**Phase 3 验收：**

- [ ] 全程不打开 RViz 可完成：加载地图 → 定位 → 设位姿 → 设目标 → 车到点。
- [ ] 失败时有可读中文原因。

---

### Phase 4：遥控体验增强（约 1 周）

**目标：** 接近 RobotCA / teleop 的手感，保留麦轮优势。

#### 4.1 虚拟摇杆组件

**新增：** `ui/widgets/virtual_joystick.py`

- 左摇杆：线速度 + 角速度。
- 右摇杆（可选）：横向 `ly`（麦轮）。
- 输出仍走现有 `JsonClientBridge.send_cmd_vel`。

#### 4.2 控制模式切换

```text
[手动] / [导航]  --导航运行时自动切到导航，禁摇杆
```

与现有 `_nav_cmd_paused`、互锁逻辑统一。

#### 4.3 状态 HUD（轻量）

在 `StatusPanel` 增加：

- 当前 vx / vy / wz（来自 JSON odom 或 cmd_vel）。
- 导航剩余距离（Phase 3 已有则复用）。

**Phase 4 验收：**

- [ ] 摇杆连续控制流畅，松开即停。
- [ ] 导航与手动切换无竞态 cmd_vel。

---

### Phase 5：可选扩展（按需）

| 功能 | 条件 | 说明 |
|------|------|------|
| 摄像头 | 底盘有 `compressed_image` 或 RTSP | 订阅显示 |
| 多点导航 | Phase 3 稳定后 | GUI 点多个路点，发 `NavigateThroughPoses` |
| 仅预览地图 | Phase 1 后 | 不启 Nav2，只起 map_server 看图 |
| Android 版 | 产品明确要求 | **另立项**：Kotlin + JSON 协议，不移植 rosjava |
| odom 标定 GUI | B2 有公式后 | 向导式标定，写回配置 |

---

## 6. 目录与模块演进

```text
pc/qt_client/
├── app.py                      # 轻量入口：参数、QApplication、单实例锁
├── main_window.py              # 默认 Shell / --legacy 路由
├── legacy/                     # 旧调试台 LegacyWindow
├── core/                       # RobotSession / RobotConnectionState
├── backends/                   # RobotBackend 抽象与 mock/ros1/ros2 骨架
├── gateway/
│   ├── json_client.py          # 保持
│   └── ros2_pub.py             # 扩展：scan/map 订阅或拆 ros2_node.py
├── mapping/
│   ├── ros_stack.py            # 保持 + RViz 配置路径
│   └── preflight.py            # Phase 1 新增
├── viz/                        # Phase 2 新增
│   ├── map_canvas.py
│   ├── map_subscriber.py
│   ├── scan_subscriber.py
│   └── tf_cache.py
├── nav/                        # Phase 3 新增
│   ├── goal_publisher.py       # Nav2 action client
│   └── nav_status.py
├── ui/widgets/
│   ├── map_view_panel.py       # Phase 2
│   ├── map_browser.py          # Phase 1
│   ├── virtual_joystick.py     # Phase 4
│   ├── stack_panel.py
│   ├── nav_panel.py
│   └── control_panel.py
└── config/
    ├── slam_toolbox_xtark.yaml
    ├── nav2_xtark.yaml
    ├── xtark_mapping.rviz      # Phase 1
    └── xtark_nav.rviz
```

**`app.py` 瘦身方向：** 交互逻辑下沉到 widget / nav / viz 模块，主窗口只做信号连接与生命周期。

---

## 7. 里程碑与时间表（参考）

| 里程碑 | 内容 | 预估 | 依赖 |
|--------|------|------|------|
| **M0** | 标定完成 + 可用导航图 + 真机 Nav2 走通 | 1~2 周 | 真机时间 |
| **M1** | 自检 + 地图列表 + RViz 预设 | 1 周 | M0 |
| **M2** | 内嵌地图 + 激光显示 | 2 周 | M1 |
| **M3** | GUI 点目标/位姿 + 导航状态 | 1~2 周 | M2 |
| **M4** | 虚拟摇杆 + HUD | 1 周 | M0 |
| **M5** | 相机/多点等 | 按需 | M3 |

从 M0 到 M3（**对齐手机 App 核心体验**）约 **5~7 周**（含联调）；一人兼职需拉长。

---

## 8. 各阶段验收 checklist

### M0（必须先过）

- [ ] 三张标定测试在容差内（直行 1 m、横移 0.5 m、转 90°）
- [ ] 新地图 known ratio 明显优于当前
- [ ] Nav2 低速点到点成功 ≥ 3 次
- [ ] 急停、取消目标、停栈无残留进程

### M1

- [ ] 「建图检查」能列出全部失败项
- [ ] 从列表选地图可一键启动导航栈
- [ ] RViz 预设加载正确

### M2

- [ ] 不启 RViz 能看到 `/map` 更新
- [ ] 激光与机器人位姿正确（与 RViz 一致）
- [ ] 缩放平移流畅，CPU 占用可接受

### M3

- [ ] GUI 设初始位姿后 AMCL 收敛
- [ ] GUI 设目标后车能到达
- [ ] 界面显示导航状态/失败原因

---

## 9. 风险与「明确不做」

### 9.1 风险

| 风险 | 缓解 |
|------|------|
| `/scan` 时间戳跨设备偏差 | 保持 `WSL2统一栈运行与调试.md` 中的 relay 方案；M2 显示与 SLAM 分开验证 |
| Qt 自绘地图性能 | 限制刷新率（5~10 Hz）；大图只绘可见区域 |
| Nav2 与手动 cmd_vel 竞态 | 保持现有门控；Phase 4 不破坏互锁 |
| 标定未完成就做 UI | **强制 M0 门槛** |

### 9.2 明确不做（当前周期）

- 不移植 android_apps / RobotCA 的 Java 代码。
- 不上 world_canvas / ROS1 move_base。
- 不做 Android 原生 App（除非单独立项）。
- 不做倾斜传感器、随机游走、势场法（Nav2 已覆盖导航）。
- 不做多机器人调度（单机 xtark 优先）。

---

## 10. 推荐执行顺序

```text
先把地图和导航质量做实（M0）
  → 再做自检和地图管理（M1）
  → 再做内嵌地图（M2）
  → 再做 GUI 点目标（M3）
  → 最后摇杆抛光（M4）
```

**M2 + M3 完成后**，在「建图导航」上才算真正对齐并超过老手机 App。此前优势在栈管理和 Nav2，短板在「必须开 RViz、纯文本操作」。

---

## 11. 相关文档

| 文档 | 关系 |
|------|------|
| `WSL2统一栈运行与调试.md` | 运行流程、建图前检查命令 |
| `建图联调现状与问题记录.md` | Phase 0 任务来源（A/B/C 阶段） |
| `移动平台外挂感知建图导航方案.md` | 总体硬件/软件架构 |
| `底盘JSON对接协议草案.md` | JSON 协议与网关字段 |
| `pc/qt_client/README.md` | 客户端安装与日常使用 |

---

*文档版本：2026-06-09，随 `qt_client` 演进更新。*
