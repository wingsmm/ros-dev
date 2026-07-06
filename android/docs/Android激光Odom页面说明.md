# Android 激光 Odom 页面说明

本文说明 Android 端**尚未实现、仅处于开发计划阶段**的「激光 Odom」页面：在视觉与交互上接近现有 `Robot` 激光页，但位姿与紫块相对原点计划改用车端实验话题 **`/odom_laser`**，用于与轮式融合 `/odom` 做对照观察。

---

## 页面定位

「激光 Odom」页是 **对比可视化页**，不替代主线 `/odom`。

| 维度 | Robot 页 | 激光 Odom 页（本页） |
|------|----------|----------------------|
| 激光数据 | `/scan` | `/scan`（相同） |
| 位姿数据 | `/odom`（轮速 + IMU 融合） | `/odom_laser`（rf2o 激光扫描匹配） |
| 主要用途 | 日常感知、手动驾驶、航点 | 观察激光里程计相对位移与漂移 |
| 航点 | 支持 | **不支持**（仅可视化） |

从交互上看，本页仍是「激光雷达视图 + 手动控制」的组合；与 `Robot` 页并排切换时，可直观对比同一行驶过程中 **紫块漂移、横移误差、原地旋转稳定性** 的差异。

计划中的代码入口（尚未实现）：

- `LaserOdomScanFragment` — 页面 Fragment
- `RelativeOdometryTracker` — 页内独立的「首帧归零」位姿跟踪
- 复用 `LaserScanView` / `LaserScanRenderer`，注入本页 tracker，关闭航点交互

---

## 计划改动文件（Android）

以下路径均相对于仓库根目录；App 模块根为  
`android/RobotCA-master/RobotCA-master/src/android_foo/control_app/`。  
**状态：尚未实现**，仅作开发清单。

```text
android/RobotCA-master/RobotCA-master/src/android_foo/control_app/
├── src/main/java/com/robotca/ControlApp/
│   ├── ControlApp.java                          [修改] 抽屉菜单新增「激光 Odom」；selectItem case 顺延
│   ├── Core/
│   │   ├── RobotController.java                 [修改] 位姿逻辑委托 RelativeOdometryTracker；static getX/Y/Heading 保持不变
│   │   └── RelativeOdometryTracker.java         [新增] 首帧归零、update(Odometry)、getX/Y/Heading、reset()
│   ├── Fragments/
│   │   ├── LaserScanFragment.java               [不改或微调] Robot 页；继续用默认 tracker + 航点
│   │   └── LaserOdomScanFragment.java           [新增] 本页入口；订阅 /odom_laser；无航点 UI
│   ├── Layers/
│   │   └── LaserScanRenderer.java               [修改] 注入 tracker；waypointsEnabled 开关；drawPoint/screenToWorld 读 tracker
│   └── Views/
│       └── LaserScanView.java                   [修改] 支持 configure(tracker, waypointsEnabled) 供两页复用
└── src/main/res/
    ├── layout/
    │   ├── fragment_laser_scan.xml              [不改] Robot 页布局（含 Clear Waypoints）
    │   └── fragment_laser_odom_scan.xml         [新增] 仅 Recenter + Lock Camera；可选无数据 TextView
    └── values/
        ├── strings.xml                          [修改] feature_titles 插入一项；无数据提示等文案
        └── values-zh-rCN/
            └── strings.xml                      [修改] 中文菜单名「激光 Odom」等
```

### 各文件职责摘要

| 文件 | 操作 | 说明 |
|------|------|------|
| `RelativeOdometryTracker.java` | 新增 | 从 `setOdometry` 抽出的相对位姿；激光 Odom 页独立实例 |
| `LaserOdomScanFragment.java` | 新增 | `onCreateView` 加载 `fragment_laser_odom_scan`；`getConnectedNode()` 订 `/odom_laser`；生命周期内 `shutdown` 订阅 |
| `fragment_laser_odom_scan.xml` | 新增 | 复用 `LaserScanView`；无 `clear_waypoints_button` |
| `LaserScanRenderer.java` | 修改 | 不再写死 `RobotController.getX()`；关闭航点时跳过双击/长按与 `drawWayPoints` |
| `LaserScanView.java` | 修改 | Robot 页默认 tracker=Controller；激光 Odom 页传入页内 tracker |
| `RobotController.java` | 修改 | 内部持默认 tracker；`setOdometry` 仍驱动 HUD/摇杆用的全局状态 |
| `ControlApp.java` | 修改 | `feature_titles` 在 Robot 项之后插入；`case 4` → `LaserOdomScanFragment`，其后 case 顺延 |
| `strings.xml` / `values-zh-rCN/strings.xml` | 修改 | 抽屉标题；如 `laser_odom_waiting`「等待 /odom_laser」 |

### 明确不改动（本需求范围内）

- `LaserScanFragment.java`、`fragment_laser_scan.xml` — Robot 页行为保持不变
- `SlamMapFragment.java`、`SlamMapView.java` — 不在本需求范围内
- `HUDFragment.java`、`JoystickFragment.java`、`ManualControlFragment.java` — 仍用全局 `/odom`，不为本页单独改数据源

### 车端配套（非 Android 目录，同一功能上线时需要）

| 文件 | 操作 | 说明 |
|------|------|------|
| `xtark/scripts/android_stack.sh` | 修改 | `LASER_ODOM_ENABLE=1` 时启动 `rf2o_odom_laser.launch`；stop/status 检查 `/odom_laser` |

---

## 车端前置条件

`/odom_laser` 不会随默认 `android_stack.sh start` 自动出现，需要车端并行启动 **rf2o 激光里程计旁路**。

### 车端数据链（ROS）

```text
激光雷达
  └─ /scan
        │
        ├─（Robot 页、本页共用）Android 订阅 /scan → 激光点云绘制
        │
        └─ rf2o_laser_odometry（旁路实验节点）
              └─ 发布 /odom_laser
                 （nav_msgs/Odometry，frame_id: odom_laser）
                 publish_tf: false（不替换主线 TF）

底盘 / IMU（与 Robot 页相同，本页紫块不用它）
  └─ /odom_raw + /imu → robot_pose_ekf → /odom
```

实验包与 launch 文件：

- `xtark/xtark_laser_odometry/launch/rf2o_odom_laser.launch`
- 默认话题：`/odom_laser`，默认 `odom_frame_id`：`odom_laser`

### 推荐启动方式

计划在 `android_stack.sh` 增加可选开关（默认关闭）：

```bash
LASER_ODOM_ENABLE=1 android_stack.sh start
```

等价于：在 bringup 与 `/scan` 已就绪后，额外 `roslaunch xtark_laser_odometry rf2o_odom_laser.launch`。

也可在 bringup 已由其他栈拉起时，单独执行：

```bash
xtark/scripts/laser_odom_experiment.sh start
```

### 启动检查

```bash
rostopic hz /odom_laser
rostopic echo /odom_laser -n 1
```

若 App 打开本页后长时间无紫块移动、无朝向跟随，优先确认 `/odom_laser` 是否在发布；rf2o 在静止或刚连接时可能尚未输出有效增量。

---

## 计划实现的功能

### 1. 顶部 HUD 状态栏（与 Robot 页共用）

仍显示全局 `RobotController` 订阅的 **`/odom`** 速度与角速度、GPS、告警等。

这是**刻意设计**：HUD 反映轮式融合里程计，中央视图与紫块反映激光里程计，便于同屏对比两套源的差异。

### 2. 手动控制（与 Robot 页相同）

- 左下角六向按钮 + 停止
- 右下角虚拟摇杆（若当前控制模式启用）

均经 `RobotController` 发布 `/cmd_vel`，与位姿数据源无关。

### 3. 中央激光扫描视图

与 Robot 页相同的能力：

- 显示 `/scan` 激光点与扇面
- `Recenter`：视图重新居中
- `Lock Camera Angle`：相机角度跟随**本页** `getHeading()`（来自 `/odom_laser`）

**不包含：**

- 航点添加、编辑、清除
- `Clear Waypoints` 按钮
- 路径规划相关 action

### 4. 无数据提示（计划）

当页面已连接 ROS 但 `/odom_laser` 无消息时，显示轻量状态提示（例如「等待 /odom_laser」），避免误以为 App 卡死。

---

## 图中元素分别是什么

### 蓝色三角形 / 蓝色机器人标记

与 Robot 页相同：表示车体朝向，**固定在激光视图中心**，不随 `/odom_laser` 平移。

### 紫色方块

按计划应表示本页 tracker 收到的**第一帧 `/odom_laser` 位置**所建立的相对原点，会随行驶在屏幕上移动。

- 它正是本页 `startPos` 所定义的平移基准，不是原始 `odom_laser` 坐标系的绝对 `(0,0)`
- 对相对坐标 `(0,0)` 调用 `drawPoint()`，再用本页 tracker 的 `getX()` / `getY()` / `getHeading()` 换算到车体视角后绘制

与 Robot 页对比：Robot 页紫块对应 `/odom` 首帧相对原点；本页计划对应 `/odom_laser` 首帧相对原点。同一物理路径下，若激光里程计与轮式里程计不一致，两页紫块相对蓝三角的运动会不同。

### 四周密集的小点 / 放射状线条

激光雷达扫描点，数据来源与 Robot 页相同（`/scan`），机体坐标系下绕视图中心展开。

### 不会出现的内容

- 航点路径（点 + 连线）

---

## 位姿数据链

本页只接 **`/scan` + `/odom_laser`**。

```text
车端
  ├─ 激光雷达 → /scan
  │       │
  │       ├─────────────────────────────┐
  │       ▼                             ▼
  │  Android 订 /scan              rf2o → /odom_laser
  │  LaserScanRenderer                  │
  │       │                             ▼
  │       ├─ 激光点：机体坐标系           Android 订 /odom_laser（页内订阅）
  │       │  绕视图中心展开               RelativeOdometryTracker.update()
  │       │                             ├─ startPos = 本页首帧 position
  │       ▼                             ├─ currentPos = 后续帧 position
  │  蓝三角：永远在屏幕中心               ├─ getX/Y = currentPos − startPos
  │  （不随 odom_laser 平移）             ├─ getHeading() → 激光 odom 航向
  │                                     │
  │                                     ├─→ 未锁朝向：相机绕 heading 旋转
  │                                     └─→ drawPoint(0,0)：紫块 = 激光 odom 首帧相对原点
  │                                         相对车体的位置
  │
  └─ 轮速+IMU → /odom（本页紫块不用）
        └─→ HUDFragment（速度、角速度等，全局）

手动控制：/cmd_vel ← RobotController（出站，非位姿输入）

（链在此结束）
```

| 层级 | 话题 | 在本页的用途 |
|------|------|----------------|
| 激光里程计 | `/odom_laser` | 朝向、相对首帧位移、紫块 (0,0)、相机跟随 |
| 激光 | `/scan` | 点云与扇面，机体坐标系，画在视图中心周围 |
| 轮式融合（旁路） | `/odom` | 仅 HUD 速度/角速度，**不参与本页紫块与相机** |
| 手动控制 | `/cmd_vel` | 左下按钮 / 摇杆发布 |

### `/odom_laser` 在 App 内的记法

算法与 Robot 页对 `/odom` 的「手撕相对位姿」相同，但使用**页内独立** tracker，与 `RobotController` 的全局 `startPos` 互不影响：

- `startPos`：进入本页（或重连）后**收到的第一帧** `/odom_laser` 的 `position`
- `currentPos`：第二帧及以后每帧的 `position`；首帧只写 `startPos`，不写 `currentPos`
- `getX()` / `getY()`：`currentPos − startPos`，表示相对「本页连接后第一帧」的位移
- `getHeading()`：当前帧姿态四元数换算的航向（弧度）

切换回 Robot 页再切回本页时，tracker 会重新归零，紫块语义重置为新的「会话首帧」。

### 计划中的实现入口

| 环节 | 组件 |
|------|------|
| 激光 | `LaserScanView` → `LaserScanRenderer.onNewMessage(LaserScan)`（与 Robot 页共用 `/scan` 订阅） |
| 激光里程计 | `LaserOdomScanFragment` 页内订阅 `/odom_laser` → `RelativeOdometryTracker.update()` |
| 绘制 | `LaserScanRenderer` 注入本页 tracker → `onDrawFrame()`、`drawPoint()` |
| 导航栏 | `ControlApp` 抽屉新增「激光 Odom」项 |

---

## 与 Robot 页的区别

| 项目 | Robot 页 | 激光 Odom 页 |
|------|----------|--------------|
| 紫块含义 | `/odom` 首帧相对原点 | `/odom_laser` 首帧相对原点（计划） |
| 位姿话题 | `/odom` | `/odom_laser` |
| 航点 | 有 | 无 |
| HUD 速度来源 | `/odom` | `/odom`（相同，便于对照） |
| 相机朝向锁定 | 跟 `/odom` heading | 跟 `/odom_laser` heading |

---

## 简单图例

- 蓝色三角形：机器人（永远在激光视图中心）
- 紫色方块：本页首帧 `/odom_laser` 建立的相对原点（计划）
- 密集放射点：激光雷达扫描点（`/scan`）
- 左下按钮 / 右下摇杆：手动驾驶（`/cmd_vel`）
- 顶部栏：速度、转角等（来自 `/odom`，非本页位姿源）

---

## 使用与验收建议

### 典型对比流程

1. 车端：`LASER_ODOM_ENABLE=1 android_stack.sh start`，确认 `/odom_laser` 有数据
2. App 连接同一 Master URI
3. 先打开 **Robot** 页，再打开 **激光 Odom** 页，或来回切换
4. 低速直线前进、原地旋转、麦轮横移，观察两页紫块相对蓝三角的差异

### 预期现象（实验性质）

| 动作 | 一般预期 |
|------|----------|
| 直线前进 | 两页紫块都应向后（或向前）移动；幅度可能接近但不保证一致 |
| 原地旋转 | 紫块绕蓝三角摆动；激光 odom 对旋转更敏感 |
| 麦轮横移 | `/odom` 与 `/odom_laser` 差异往往最明显 |
| 长时间静止 | `/odom_laser` 可能有小幅抖动，属 rf2o 常见现象 |
| 环境变化（人走动、大空场） | 激光 odom 可能跳变或漂移，需记录而非当 bug |

### 验收清单（页面实现完成后）

- [ ] 抽屉可见「激光 Odom」入口
- [ ] `/scan` 正常显示，与 Robot 页一致
- [ ] `/odom_laser` 有数据时，紫块随行驶移动，Lock Camera 跟随激光航向
- [ ] 无法在本页添加或编辑航点
- [ ] 无 `/odom_laser` 时有明确等待提示
- [ ] `LASER_ODOM_ENABLE=0` 时默认 Android 栈行为不变

---

## 风险与限制

1. **实验话题，非主线**：`/odom_laser` 不替换 `/odom`；本页仅供观察，不能当作导航定位依据。
2. **依赖 rf2o 旁路**：未启动 rf2o 时本页位姿无效，但激光与手动控制仍可用。
3. **双套 startPos 独立**：Robot 页与激光 Odom 页各自「首帧归零」，切换页面会重置相对起点，不宜跨页比较绝对位移数值，宜比较**运动趋势与形态**。
4. **HUD 与紫块数据源不一致**：顶部速度来自 `/odom`，紫块来自 `/odom_laser`；阅读 HUD 时不要误以为速度来自激光里程计。
5. **不发布 TF**：`rf2o_odom_laser.launch` 默认 `publish_tf:=false`，本页完全依赖 Odometry 消息内的 pose，不查 TF 树。

---

## 备注

对外介绍时建议这样说：

> 这是 Android 端的激光里程计对比页：激光画法跟 Robot 页一样，但紫块和朝向用的是 `/odom_laser`，用来和轮式 `/odom` 对照。
