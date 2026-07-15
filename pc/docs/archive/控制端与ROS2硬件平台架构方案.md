# 控制端与 ROS2 硬件平台架构方案

本文用于统一后续开发边界：Android 作为 xtark 小车的既有稳定控制端保留；Qt 作为长期统一控制台继续演进；xtark、RK3568、Jetson 等机器人侧硬件平台在新主线中都尽量作为硬件采集平台；算法、建图、导航等能力优先集中放到 qt-client 所在的 PC / WSL / ROS2 工作站侧。

## 1. 总体结论

当前项目不再追求“Android / Qt / ROS2 一次性大统一”。更稳妥的路线是分成两条线：

```text
Android 线：xtark-only，功能基本锁死，只保证现有 Android 控制端可正常运行。

Qt 线：长期主线，逐步迁移 Android 现有功能，并扩展到 xtark、RK3568、Jetson 等硬件平台。
```

xtark 在 Qt 线中的定位不是“被改造成完整 ROS2 算法机器人”，而是：

```text
xtark ROS1 硬件采集栈
        ↓ JSON / bridge
PC / WSL ROS2 算法栈
        ↓
qt-client 展示、控制、调试、地图、任务
```

RK3568 / Jetson 等新平台也按“硬件采集平台”规划，只是它们的数据出口更适合直接设计成 ROS2-native：

```text
RK3568 / Jetson ROS2-native 硬件采集栈
        ↓ ROS2 topics / gateway
PC / WSL ROS2 算法栈
        ↓
qt-client 展示、控制、调试、地图、任务
```

### 1.1 重要术语约定

本文里的“Qt 主线”不是指把所有算法都塞进 Qt GUI 进程，而是指以 qt-client 所在的 PC / WSL / ROS2 工作站作为长期主控与算法中心。

```text
qt-client GUI：负责控制、调度、观察、展示、记录、交互。
PC / WSL / ROS2 工作站：负责运行 bridge、SLAM、Nav、RViz2、地图保存、实验分析等算法进程。
xtark / RK3568 / Jetson：尽量只作为硬件采集平台和基础安全控制平台。
```

因此，“Qt 不在 GUI 主线程里跑 SLAM”和“算法放在 qt-client 所在 WSL / ROS2 平台上”并不矛盾。前者是进程/线程边界，后者是机器/平台边界。

### 1.2 当前连接架构四条线

当前架构按平台和用途分成四条线，不再把 Android、`ros1_bridge`、xtark Qt 连接和 ROS2-native 新平台混为一个方案：

| 线 | 定位 | 当前结论 |
|---|---|---|
| Android ROS1 | 冻结的历史可用栈 | 保持 ROS1 直连，不参与 Qt/ROS2 重构 |
| `ros1_bridge dynamic_bridge` | ROS1<->ROS2 实验桥 | 非当前主线，保留为试验/历史方案 |
| xtark Qt 混合连接 | 当前 xtark <-> Qt 主方案 | JSON + HTTP/MJPEG + HTTP raw depth + PC 侧 ROS2 bridge 分工协作 |
| ROS2-native | RK3568 / Jetson 等新平台方向 | 新硬件优先直接输出 ROS2 topic |

xtark 当前 Qt 主方案不是单一 bridge，而是按数据类型分流：

```text
控制 / 遥测 / 激光摘要：JSON TCP :8765
RGB 预览：HTTP/MJPEG :8080
Depth raw：HTTP raw depth :8082
ROS2 展示 / 诊断 / 后续算法：PC 侧 xtark_ros2_bridge
```

统一边界：

- Android ROS1 已冻结，只维护既有行为。
- `ros1_bridge dynamic_bridge` 是历史/实验桥，不作为日常 Qt 主线。
- `:8765` 不传图像/点云，只管控制、遥测和轻量激光 JSON。
- `:8080` 只管 RGB MJPEG 预览。
- `:8082` 只管深度 raw frame。
- PC 侧 ROS2 bridge 面向 RViz2、诊断和算法 topic，不是 xtark 与 Qt 的唯一通信入口。
- RK3568 / Jetson 等新平台优先走 ROS2-native，不应强行继承 xtark JSON 细节。

`ros1_bridge dynamic_bridge` 降级为历史/实验线的原因：

- ROS1 连接不止 `ROS_MASTER_URI :11311`。bridge 订阅 ROS1 topic 后，机器人端还要回连 bridge 暴露的 XMLRPC / TCPROS 临时端口；Docker Desktop / WSL2 下这些端口和回连地址不稳定，容易出现“Master 看得到，数据进不来”。
- ROS2 DDS 也有独立的数据面。容器内 ROS2 与 WSL/Qt 进程之间可能出现 topic list 能发现，但 `echo/hz` 或 Qt 订阅收不到持续数据的现象；这属于 DDS discovery/data path 与 Docker/WSL 网络边界叠加问题。
- 在 WSL 原生安装 ROS1 依赖虽可绕开一部分 Docker 网络问题，但会污染当前 ROS2 Humble 工作站环境，增加 Python、消息包、setup.bash 顺序和维护成本。
- RGB/Depth 图像是大带宽数据，若把 `dynamic_bridge` 作为日常主通道，会把 TCPROS、DDS、QoS、Docker/WSL 网络和图像吞吐问题混在一起，排障成本过高。

因此，`dynamic_bridge` 只用于独立实验或临时验证 ROS1<->ROS2 语义桥接；日常 xtark Qt 线固定采用 JSON `:8765` + RGB MJPEG `:8080` + depth raw HTTP `:8082` + PC 侧 ROS2 bridge。

## 2. 角色边界

### 2.1 Android 控制端

定位：xtark 专用 legacy 控制端。

职责：

- 保证现有 xtark Android 控制功能继续可用。
- 作为 Qt 功能迁移期间的 fallback。
- 只做必要 bugfix 和兼容维护。

不再承担：

- 不再作为未来通用控制端。
- 不再兼容 RK3568 / Jetson。
- 不再参与 Qt / ROS2 架构重构。
- 不再新增大功能。

### 2.2 xtark 小车 Android 栈

定位：冻结的 ROS1 运行栈。

建议继续命名为：

```text
android_stack
```

职责：

- `start` 后保证现有 Android 控制端正常运行。
- 保持 Android 当前依赖的 ROS1 master、bringup、gmapping、move_base 等链路可用。
- 不被 Qt 新栈破坏。
- 不被 WSL / ROS2 实验链路污染。

不要做：

- 不接入 Qt 新功能。
- 不接入 WSL ROS2 算法栈。
- 不修改 Android 既有 topic / action / service 语义。
- 不为了 Qt 优化 Android 栈。

### 2.3 xtark 小车 Qt 栈

定位：硬件采集 + 基础安全控制栈。

建议继续命名为：

```text
qt_stack
```

职责：

- 启动 xtark 基础硬件驱动。
- 提供 Qt 可连接的 JSON 网关。
- 提供传感器数据：odom、scan、camera、imu、电压、状态等。
- 接收 Qt 的控制命令：cmd_vel、停止、归零、简单状态控制。
- 保留必要安全机制，例如 watchdog、急停、断连处理。
- 尽量减少机器人端算法负担，把 SLAM / Nav 等上层算法交给 qt-client 所在的 PC / WSL / ROS2 工作站。

建议机器人侧只做：

```text
硬件驱动 + 基础安全 + 数据采集 + JSON 输出 + 控制入口
```

### 2.4 PC / WSL / ROS2 算法栈

定位：qt-client 所在工作站上的算法计算层。

职责：

- 将 xtark JSON / ROS1 数据转换为 ROS2 标准话题。
- 将 RK3568 / Jetson 等 ROS2-native 硬件平台输出的数据纳入统一 ROS2 图。
- 发布 `/scan`、odom、TF 等标准数据。
- 跑 `slam_toolbox`、RViz2。
- 后续承载 Nav2、定位、地图保存、实验分析等能力。

建议在 qt-client 所在的 PC / WSL / ROS2 环境中拆成独立 sidecar，而不是嵌入 Qt GUI 主线程：

```text
ros2_bridge_stack
ros2_slam_stack
```

### 2.5 Qt 控制台

定位：运行在 PC / WSL 工作站上的长期统一上位机。

职责：

- 控制 xtark。
- 逐步替代 Android 现有功能。
- 展示传感器、状态、地图、轨迹、日志、诊断。
- 后续控制 RK3568 / Jetson 等 ROS2 平台。
- 通过 backend 抽象适配不同机器人。

不建议：

- 不在 Qt GUI 主线程里塞重 SLAM 算法。
- 不把 ROS2 算法进程和 Qt GUI 生命周期强绑定。
- 不为了统一 UI 破坏 xtark 当前已验证控制链路。

注意：这里的“不在 Qt 里塞重算法”不是说算法不在 qt-client 所在机器上运行；正确边界是：

```text
算法运行在 PC / WSL / ROS2 工作站侧。
Qt GUI 负责调度、观察、展示、记录和发控制命令。
重算法进程以 ROS2 sidecar / node 形式独立运行。
```

### 2.6 RK3568 / Jetson 平台

定位：未来 ROS2-native 硬件采集平台。

与 xtark 的关键差异：

```text
xtark：ROS1 legacy 硬件采集底盘，需要桥接到 ROS2。
RK3568 / Jetson：ROS2-native 硬件采集平台，可以直接输出 ROS2 标准数据。
```

后续 Qt 面向这类平台时，应优先走新的 ROS2 backend，而不是复用 xtark 的 JSON 细节。原则上，这类平台只负责采集与基础安全控制；SLAM、建图、导航、实验分析等尽量放在 qt-client 所在的 PC / WSL / ROS2 工作站侧。

## 3. 总体架构

```text
                 PC / WSL / ROS2 工作站
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  ┌────────────────────────┐                             │
│  │       qt-client         │                             │
│  │ 控制 / 展示 / 地图 / 日志 │                             │
│  └───────────┬────────────┘                             │
│              │ RobotBackend API                         │
│  ┌───────────▼────────────┐                             │
│  │   ROS2 sidecar nodes    │                             │
│  │ bridge / SLAM / Nav /   │                             │
│  │ RViz2 / map save / diag │                             │
│  └───────┬─────────┬──────┘                             │
└──────────┼─────────┼────────────────────────────────────┘
           │         │
           │         │ ROS2 native topics / services / actions
           │         │
           │   ┌─────▼─────────────┐
           │   │ RK3568 / Jetson    │
           │   │ ROS2 硬件采集平台   │
           │   └───────────────────┘
           │
           │ JSON TCP / bridge
┌──────────▼─────────┐
│ xtark qt_stack      │
│ ROS1 硬件采集/控制   │
└────────────────────┘


冻结保障线：

┌────────────────┐
│ Android Client  │
└───────┬────────┘
        │ ROS1 / 旧协议
┌───────▼────────┐
│ xtark android_stack │
│ 旧 ROS1 控制栈       │
└────────────────┘
```

核心原则：

- Android 和 Qt 不共栈。
- xtark 的 `android_stack` 和 `qt_stack` 互斥启动。
- xtark 不强制升级成完整 ROS2 算法机器人。
- RK3568 / Jetson 等平台也尽量作为硬件采集平台，不把 SLAM / Nav 主职责放到板端。
- Qt 不写死 xtark。
- ROS2 算法层在 qt-client 所在 PC / WSL / ROS2 工作站侧运行，并独立于 Qt GUI 主线程。
- RK3568 / Jetson 不继承 xtark legacy 包袱。

## 4. 栈设计

### 4.1 `android_stack`

目标：保证旧 Android 正常使用。

保留内容：

- roscore
- xtark bringup
- Android 当前依赖的 topic / service / action
- gmapping / move_base 等旧链路
- Android 控制端现有假设

验收标准：

- Android 客户端能启动。
- 手动控制正常。
- 地图 / 导航现有功能正常。
- 旧行为不退化。

禁止事项：

- 不接入 Qt 新功能。
- 不接入 WSL ROS2。
- 不为了 Qt 修改旧 topic 语义。
- 不把 Android 栈作为未来通用控制栈继续扩展。

### 4.2 `qt_stack`

目标：让 xtark 成为 Qt + WSL 的硬件采集底座。

保留/强化内容：

- xtark driver
- `/odom_raw`
- `/odom`
- `/scan`
- `/imu`
- `/voltage`
- camera preview
- JSON gateway
- cmd_vel 控制
- 急停 / 停止
- 状态心跳
- watchdog

弱化或可选内容：

- gmapping
- move_base
- 机器人端复杂导航
- 机器人端复杂 SLAM

验收标准：

- Qt 可连接。
- Qt 可手动控制。
- Qt 可看 odom / scan / camera / status。
- 机器人端 CPU 压力低于 Android 全栈模式。
- 断连 / 停止安全可靠。

禁止事项：

- 不自动清理 Android 栈进程。
- 不和 Android 栈共享模糊的 pid / log。
- 不在机器人端继续堆复杂算法。

### 4.3 `pc_wsl_ros2_stack`

目标：在 qt-client 所在的 PC / WSL / ROS2 工作站上，把各硬件平台的采集数据变成 ROS2 标准算法输入。

xtark 第一阶段至少发布：

```text
/scan
/odom_raw
/odom
/odom_laser
/tf
/tf_static
/robot_status
/battery
```

后续面向 xtark / RK3568 / Jetson 统一扩展：

```text
/map
/map_metadata
slam_toolbox 状态
map_save 服务
Nav2 goal/action
/path
/pose
```

验收标准：

- `ros2 topic list` 能看到标准话题。
- `ros2 topic hz /scan` 正常。
- `ros2 topic hz /odom_raw` 正常。
- RViz2 能显示 scan。
- RViz2 能显示 TF tree。
- RViz2 不报明显 TF extrapolation。
- ROS2 侧数值与 Qt odom compare 侧一致或差异可解释。

禁止事项：

- 不嵌入 Qt GUI 主线程。
- 不依赖 Qt GUI 启动。
- 不在第一版就接 Nav2。
- 不在第一版就做复杂地图 UI。

## 5. Qt 功能迁移路线

Qt 迁移 Android 功能时，不建议照抄 Android UI。应按能力分层迁移。

### 第一层：基础控制

优先级最高。

- 连接 / 断开
- 急停
- 手动遥控
- 电量 / 状态
- 网络状态
- 速度档位
- watchdog 状态

这层必须直接可靠，不依赖 ROS2 SLAM。

### 第二层：传感器观察

- camera 预览
- laser scan 显示
- odom 对比
- imu 状态
- topic 频率
- 数据延迟
- 丢包 / 超时提示

这层是调试和安全基础。

### 第三层：地图 / SLAM

建议分三步：

1. Qt 只显示 ROS2 侧状态，例如 SLAM 是否启动、topic 是否在线、地图尺寸、当前 pose。
2. Qt 显示 ROS2 产出的 `/map` 或桥接后的 occupancy grid。
3. Qt 增加地图交互，包括保存地图、清图、重定位、目标点、路径显示。

### 第四层：导航

等 SLAM 稳定后再做：

- 设置目标点
- Nav2 goal
- 路径显示
- 取消导航
- 导航状态
- recovery 状态
- 速度限制

不要现在就把导航塞进 Qt 主线，否则会把控制台迁移和算法稳定性绑死。

## 6. 当前地图/里程计对比的处理

当前 Qt 里的 odom compare / 地图对比能力应保留为验证工具。

推荐顺序：

```text
第一步：保留当前 Qt odom compare
第二步：做 JSON -> ROS2 bridge
第三步：ROS2 侧发布 scan / odom / tf
第四步：RViz2 验证
第五步：slam_toolbox 建图
第六步：Qt 接入 ROS2 map 结果
第七步：Qt 地图页替代 Android 地图功能
```

原因：

- 当前 odom compare 已能校验编码器、融合、激光里程计。
- ROS2 SLAM 的主要风险在 TF、时间戳、frame、scan 质量。
- 如果一上来做 Qt 地图 UI，会把 UI 问题和 ROS2 数据问题混在一起。
- 先让 RViz2 / slam_toolbox 跑通，Qt 再接结果，风险更低。

## 7. Qt Backend 抽象建议

Qt 内部不要写死 xtark，应继续强化 `RobotBackend` 抽象。

建议按能力分组，而不是按协议分组：

```text
ConnectionCapability
MotionControlCapability
TelemetryCapability
CameraCapability
LaserScanCapability
MapCapability
NavigationCapability
DiagnosticsCapability
```

短期真实可用实现：

```text
XtarkJsonBackend
```

未来新增：

```text
Ros2GatewayBackend
Ros2NativeBackend
```

注意事项：

- 当前 xtark 工作链路里的 `json_gateway` 是真实可用路径，短期不要为命名好看强行替换。
- 可以在 UI / 文档层称为 “Xtark JSON Gateway”。
- 等 ROS2 backend 真实可用后，再统一整理命名和兼容 alias。

## 8. 实施阶段

### 阶段 0：文档锁边界

目标：先统一团队认知，防止误迁移。

修改范围：

- `pc/docs/`
- `pc/qt_client/README.md`
- xtark scripts 相关 README
- legacy 清理说明

要写清楚：

- Android 是 xtark-only legacy client。
- Android stack 冻结。
- Qt stack 是 xtark 采集栈。
- qt-client 所在 PC / WSL / ROS2 工作站是算法栈。
- xtark / RK3568 / Jetson 都尽量是硬件采集平台。
- RK3568 / Jetson 是未来 ROS2-native 硬件采集平台。
- 两套 xtark 栈互斥。

验收标准：

- 新人看文档不会把 Android 和 Qt 混成一条路线。
- 不会再把 legacy Qt 旧 ROS2 调试窗口当主线。
- 每个栈的启动/停止边界清楚。

### 阶段 1：固定 xtark 双栈边界

目标：让 `android_stack` 和 `qt_stack` 明确互斥、可诊断、可停止。

需要检查/完善：

- `android_stack.sh`
- `qt_stack.sh`
- stop 行为
- pid / log 路径
- 端口占用检查
- roscore 所属栈标记
- 启动前提示当前已有哪个栈在跑

验收标准：

- 冷启动 Android 栈后 Android 正常。
- 冷启动 Qt 栈后 Qt 正常。
- 两套栈不会互相覆盖进程。
- stop 只停止自己启动的内容。
- 日志能判断当前运行的是哪个栈。

禁止事项：

- 不让 Qt stack 自动 stop Android stack。
- 不让 Android stack 自动 stop Qt stack。
- 除非明确确认，否则不杀无关 ROS 进程。

### 阶段 2：实现 PC / WSL ROS2 数据接入 sidecar

目标：在 qt-client 所在的 PC / WSL / ROS2 工作站上，从 xtark Qt 栈的数据生成 ROS2 标准话题；后续同一层也负责接入 RK3568 / Jetson 的 ROS2-native 采集数据。

建议新建独立模块，而不是塞进 Qt GUI：

```text
pc/ros2_bridge/
```

核心能力：

- 连接 xtark JSON gateway。
- 订阅 / 解析 telemetry。
- 接收 RK3568 / Jetson 等平台发布的 ROS2-native 传感器数据。
- 发布 ROS2 `/scan`。
- 发布 ROS2 odom topics。
- 发布 TF。
- 提供健康状态。
- 支持 `.env`。
- 支持日志。
- 支持重连。

验收标准：

- `ros2 topic list` 能看到标准话题。
- `ros2 topic hz /scan` 正常。
- `ros2 topic hz /odom_raw` 正常。
- RViz2 能显示 scan。
- RViz2 不报明显 TF 错误。
- Qt 仍可同时连接，或明确规定 bridge / Qt 的连接独占策略。

禁止事项：

- 不先接 Nav2。
- 不先做地图 UI。
- 不把 bridge 写进 Qt 主线程。
- 不让 bridge 依赖 Qt GUI 启动。

### 阶段 3：PC / WSL ROS2 SLAM 验证

目标：让 qt-client 所在的 PC / WSL / ROS2 工作站使用硬件平台采集数据跑 `slam_toolbox`。第一验证对象是 xtark，后续 RK3568 / Jetson 也按同一算法侧链路接入。

需要明确：

- frame 约定
- `base_link`
- `odom`
- `map`
- `laser`
- scan timestamp 策略
- TF tree 检查
- slam_toolbox 参数
- RViz2 配置
- 地图保存脚本

验收标准：

- RViz2 显示稳定 TF。
- 机器人移动时 scan 与轨迹方向一致。
- 能生成 `/map`。
- 能保存地图。
- 静止时地图不明显漂移。
- 慢速运动时地图能闭合或至少可用。

禁止事项：

- 不把 Android gmapping 结果和 ROS2 slam_toolbox 混用。
- 不同时跑多个 SLAM 抢 TF。
- 不在机器人端和 WSL 端同时发布同名 `/map -> odom`。

### 阶段 4：qt-client GUI 接入 ROS2 地图结果

目标：qt-client GUI 不在 UI 主线程里跑 SLAM，只消费同机 PC / WSL / ROS2 算法进程输出的结果。

优先推荐：

```text
ROS2 sidecar -> 轻量 JSON/map gateway -> qt-client GUI
```

原因：

- qt-client 当前已有 JSON 体系。
- 短期工程风险低。
- qt-client GUI 可避免直接耦合 ROS2 算法进程生命周期。

后续再考虑：

```text
Qt 直接 ROS2 native
```

Qt 地图页第一版只做：

- 显示 map。
- 显示 robot pose。
- 显示 scan overlay。
- 显示轨迹。
- 显示 SLAM 状态。
- 保存地图按钮。

验收标准：

- qt-client 地图显示和 RViz2 基本一致。
- qt-client GUI 不影响 SLAM 运行。
- 关闭 qt-client GUI 后，PC / WSL / ROS2 侧 SLAM 可继续运行。
- 地图保存有明确成功 / 失败反馈。

禁止事项：

- 不第一版就做复杂导航。
- 不让 qt-client GUI 自己维护另一套地图坐标真值。
- 不在 qt-client GUI 里重写 SLAM 算法。

### 阶段 5：迁移 Android 功能到 Qt

按功能迁移，不按界面迁移。

优先级：

1. 手动控制
2. 状态 / 电量 / 连接
3. 相机
4. 地图显示
5. 地图保存 / 清理
6. 目标点
7. 导航
8. 任务流

每迁移一个功能，都要标记：

```text
Android 现有能力
Qt 已实现能力
Qt 已验证能力
是否可替代 Android
```

验收标准：

- 不是“UI 上有按钮”，而是实车验证过。
- Android 可继续作为 fallback。
- Qt 功能稳定后，再考虑 Android 对应功能冻结不维护。

## 9. legacy 清理策略

`pc/qt_client/legacy` 可以退役，而且应当先于“地图比对 / 机器人模块”的新架构改造完成第一阶段清理。

这里要区分两件事：

```text
第一阶段清理：退役入口、冻结旧 UI、迁出可复用经验，为新架构改造扫清边界。
最终物理删除：等新架构里的地图、SLAM、map save、诊断能力替代后，再删除旧代码。
```

### 9.1 第一阶段清理：先做

目标：让后续开发不再把 legacy 当主线入口，不再往旧窗口里加功能。

建议先做：

- 从默认入口隐藏 legacy。
- 文档标记 deprecated。
- 不再向 legacy 加功能。
- 新功能全部进新 Qt shell。
- 梳理 legacy 里仍有价值的 ROS2 启动、RViz2、slam、map save、诊断配置经验。
- 把可复用经验迁移到 PC / WSL ROS2 sidecar 方案或文档中。
- 保留必要的 fallback 入口，但明确不再作为主线。

验收标准：

- 默认启动不会进入 legacy。
- 新架构开发任务不依赖 legacy window。
- legacy 中可复用的 ROS2 调试经验已经被记录或迁出。
- 苦力不会再把 legacy 当作“地图比对 / 机器人模块”的实现基础。

### 9.2 最终物理删除：后做

等以下能力替代后再删除：

- `qt_stack` 稳定。
- WSL ROS2 bridge 独立可运行。
- RViz2 / `slam_toolbox` 验证通过。
- qt-client GUI 新地图页开始接 ROS2 结果。
- legacy 中旧的 RViz / slam / map save 能力有新 sidecar 替代方案。

结论：

```text
旧 UI 可以删。
旧 UI 里的 ROS2 启动、配置、调试经验要迁到新的 sidecar 方案里。
第一阶段清理应放在地图比对 / 机器人模块改造之前。
最终物理删除可以放在新架构替代验证之后。
```

### 9.3 从 legacy 迁出的 ROS2 调试经验（2026-06-24）

以下内容摘自 `pc/qt_client/mapping/ros_stack.py`、`gateway/ros2_pub.py` 与 legacy 窗口行为，供后续 **PC/WSL ROS2 sidecar** 实现参考。新 Qt shell **不得**再依赖 `LegacyWindow` 启动这些进程。

#### 环境与 shell 前缀

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}
```

子进程统一经 `bash -lc` 启动；stdout/stderr 写入 `pc/qt_client/logs/<stack>_<timestamp>.log`。

#### RViz2

```bash
rviz2
```

前置检查：`command -v rviz2`（未安装：`sudo apt install ros-humble-rviz2`）。

#### slam_toolbox（在线异步）

```bash
ros2 launch slam_toolbox online_async_launch.py \
  use_sim_time:=false \
  slam_params_file:=<pc/qt_client/config/slam_toolbox_xtark.yaml>
```

前置检查：`ros2 pkg prefix slam_toolbox`。启动 SLAM 前若 Nav 在跑，legacy 会先停 navigation/localization。

#### 地图保存

```bash
ros2 run nav2_map_server map_saver_cli -f <pc/qt_client/maps/<name>>
```

要求 SLAM 已运行且 `/map` 在发布。默认输出 `maps/<name>.pgm` + `.yaml`。常见失败：`Failed to spin map subscription` → `/map` 无数据或 TF/scan 未刷新。

#### Nav2 定位

```bash
ros2 launch nav2_bringup localization_launch.py \
  map:=<maps/xxx.yaml> \
  params_file:=<pc/qt_client/config/nav2_xtark.yaml 或 humble 默认> \
  use_sim_time:=false
```

启动前若 SLAM 在跑会先停 SLAM。`start_nav_all` 会等待 `/map` 最多约 45s。

#### Nav2 导航

```bash
ros2 launch nav2_bringup navigation_launch.py \
  params_file:=<同上> \
  use_sim_time:=false
```

要求 localization 已运行。取消导航：对 `/navigate_to_pose/_action/cancel_goal` 与 `/navigate_through_poses/_action/cancel_goal` 发 `CancelGoal`。

#### 进程内 JSON → ROS2 桥（legacy 曾嵌入 GUI）

`Ros2Publisher`（`gateway/ros2_pub.py`）在 **legacy 进程内** spin，约定：

| 方向 | Topic / TF | 说明 |
|------|------------|------|
| 发布 | `/odom_base` | JSON `odom_base` → Odometry |
| 发布 | `/odom` | 同上副本，供 Nav2 |
| 发布 | `/base_status` | JSON `base_status` → `std_msgs/String` |
| 发布 TF | `odom` → `base_link` | 与 odom 位姿一致 |
| 静态 TF | `base_link` → `laser` | x=0.05, y=0, z=0.10, yaw=π |
| 订阅 | `/cmd_vel` | Nav 模式下回调转 JSON `cmd_vel` 到底盘 |

后续应改为 **独立 sidecar 节点**，不在 Qt 主线程 `spin_once`。

#### 排错日志关键词（legacy `LogPanel` / 现统一 logging）

- `STACK start/stop <name>`：RViz / SLAM / Nav 子进程
- `MAP save OK/FAIL`：存图结果
- `NAV cancel_navigation`：导航取消
- `JSON gateway` / `CONNECT` / `CONNECTION LOST`：底盘 JSON 链路

新主线控车走 `RobotSession` → `JsonGatewayBackend`，不经过 legacy。

## 10. 关键风险

### 10.1 栈边界混乱

风险：

- Android stack、Qt stack、WSL ROS2 stack 互相启动/停止。
- roscore、bridge、camera、SLAM 进程归属不清。

对策：

- 每个 stack 只管理自己启动的进程。
- pid / log 独立。
- 启动前检查并提示冲突。
- 不自动跨栈清理。

### 10.2 ROS2 时间戳和 TF

风险：

- scan stamp 不一致。
- odom stamp 不一致。
- `map` / `odom` / `base_link` / `laser` frame 混乱。
- WSL 和机器人时间不同步导致 TF extrapolation。

对策：

- 第一版允许 bridge 统一使用 WSL receive time。
- 或明确使用机器人源时间，但要求时间同步。
- 先在 RViz2 验证 TF，再验证 SLAM。

### 10.3 qt-client GUI 过早变重

风险：

- qt-client GUI 同时承担控制、SLAM、ROS2 节点、文件写入、地图计算。
- UI 卡顿，控制链路不稳定。

对策：

- qt-client GUI 只做控制台。
- 重算法在 qt-client 所在 PC / WSL / ROS2 工作站的 ROS2 sidecar / node 中运行。
- 文件日志使用后台队列。
- 地图数据通过轻量协议进入 qt-client GUI。

### 10.4 为了通用性牺牲 xtark 当前可用性

风险：

- 为未来 RK3568 / Jetson 抽象过度，导致 xtark 当前链路不稳定。

对策：

- `json_gateway` 继续作为 xtark 主路径。
- 新 ROS2 能力并行接入。
- 不替换已验证控制链路。
- 每步保留 rollback。

## 11. 推荐落地顺序

```text
1. 文档锁边界
2. 完成 legacy 第一阶段清理：隐藏入口、冻结旧 UI、迁出可复用 ROS2 调试经验
3. 固化 android_stack / qt_stack 互斥关系
4. 在新架构上改造当前“机器人”工作区和“地图比对”模块
5. 保留当前 Qt odom compare 作为验证工具，并纳入新机器人模块
6. 新建 PC / WSL ROS2 数据接入 sidecar
7. RViz2 验证 scan / odom / tf
8. 在 PC / WSL ROS2 侧用 slam_toolbox 建图
9. qt-client GUI 接 ROS2 map 结果
10. Qt 逐步迁移 Android 功能
11. RK3568 / Jetson 作为 ROS2-native 硬件采集平台接入
12. 新架构替代验证完成后，最终物理删除 legacy
```

不要反过来先做“大统一 Qt 地图界面”。更合理的路径是：先把 legacy 入口和旧主线干扰清掉，再把当前“机器人”工作区与“地图比对”按新架构重构成稳定承载面，并在这个阶段直接打通 **xtark 采集数据 -> PC / WSL ROS2 topics -> RViz2** 的验证链路。完整 SLAM / Nav2 可以后置，但 ROS2 scan / odom / TF 与 RViz2 可视化应尽早纳入机器人页面。

## 12. 给后续开发的任务边界

后续派工时，建议按下面方式拆任务：

### 任务 A：文档与命名边界

- 更新相关 README。
- 标明 Android / Qt / WSL / ROS2 / RK / Jetson 的职责。
- 标明算法集中在 qt-client 所在 PC / WSL / ROS2 工作站侧。
- 标明 xtark / RK3568 / Jetson 都尽量作为硬件采集平台。
- 标明 legacy 状态。

不要改运行代码。

### 任务 B：legacy 第一阶段清理

- 隐藏默认 legacy 入口。
- 标记 legacy deprecated。
- 冻结旧 UI，不再新增功能。
- 梳理 legacy 中 RViz2 / slam / map save / ROS2 调试相关经验。
- 将可复用经验迁移到 PC / WSL ROS2 sidecar 文档或新架构任务中。

不要在这个阶段一刀切删除所有 legacy 文件；第一阶段目标是退役入口和迁出经验。

### 任务 C：xtark 双栈整理

- 检查 `android_stack` 和 `qt_stack` 的进程归属。
- 完善 status / stop / log。
- 明确互斥提示。

不要跨栈自动清理。

### 任务 D：机器人工作区 / 地图比对模块新架构改造

- 在新 Qt shell 中整理“机器人”工作区边界。
- 将当前 odom compare / 地图比对能力纳入新机器人模块。
- 保留已有 odom compare 作为采集链路和 ROS2 算法链路的验证工具。
- 在机器人页面内新增“ROS2 / RViz2 联调”能力：显示 bridge 状态、topic 频率、RViz2 启停入口与错误信息。
- 直接打通 xtark JSON 采集数据到 PC / WSL ROS2 标准话题，至少覆盖 `/scan`、`/odom_raw`、`/odom`、`/odom_laser`、`/tf`、`/tf_static`。
- 确认 RViz2 可看到 xtark 的雷达 scan、底盘 odom 与 TF tree。
- 明确模块只消费 backend/session/sidecar 输出，不直接依赖 legacy window。
- 为后续 ROS2 map、pose、trajectory 接入预留接口。

不要先做“大而全地图 UI”；本任务重点是把当前模块放到新架构承载面上，并先完成 ROS2 数据链和 RViz2 可视化闭环。完整 SLAM / Nav2 不在本任务内。

### 任务 E：PC / WSL ROS2 数据接入 sidecar

- 新建独立 sidecar，供机器人页面调度和观察。
- 连接 xtark JSON。
- 发布 ROS2 标准话题。
- RViz2 验证 scan / odom / TF。

不要接完整 qt-client 地图 UI；本任务只打通 PC / WSL ROS2 数据链、topic 状态和 RViz2 可视化。

### 任务 F：PC / WSL ROS2 SLAM

- 配置 `slam_toolbox`。
- 验证 `/map`。
- 保存地图。
- 记录参数和实车表现。

不要混用 Android gmapping。

### 任务 G：qt-client GUI 地图接入

- qt-client GUI 消费同机 ROS2 sidecar 结果。
- 显示 map / pose / scan / trajectory。
- 提供保存地图入口。

不要在 qt-client GUI 内实现 SLAM；SLAM 运行在同机 PC / WSL / ROS2 sidecar / node 中。

### 任务 H：Qt 替代 Android 功能

- 按功能迁移。
- 每项必须区分：已实现、已部署、已实车验证。
- Android 保留 fallback。

不要因为 UI 完成就宣布功能替代。
