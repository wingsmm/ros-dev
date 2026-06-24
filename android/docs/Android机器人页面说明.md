# Android 机器人页面说明

本文说明 Android 端 `Robot` 页面当前已经实现的功能，以及界面中常见图元的含义，避免把它和 SLAM 地图页混淆。

## 页面定位

`Robot` 页面在代码里实际对应的是激光扫描可视化相关的界面，核心实现是 `LaserScanFragment` 和 `LaserScanRenderer`，而不是 SLAM 栅格地图页。

从交互上看，这个页面更像是“机器人实时状态 + 激光雷达视图 + 手动控制”的组合页。

参考代码：

- `android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/java/com/robotca/ControlApp/ControlApp.java`
- `android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Fragments/LaserScanFragment.java`
- `android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Layers/LaserScanRenderer.java`

## 已实现功能

### 1. 顶部 HUD 状态栏

页面顶部会显示机器人实时状态，包括：

- 当前速度
- 当前转向角速度
- GPS 纬度和经度
- Wi-Fi 信号强度（取决于所用 HUD 布局；普通布局中该控件目前被注释）
- 急停 / 告警相关状态

如果启用了安全告警逻辑，机器人靠近障碍物时 HUD 还会出现红色警示效果。

### 2. 左下角手动控制按钮

左下角是一组按住生效的手动运动按钮，包括：

- 左转
- 前进
- 右转
- 左移
- 停止
- 右移
- 后退

这组按钮会通过 `RobotController.forceVelocity()` 直接发布运动控制指令，松开后会自动停下。

### 3. 右下角摇杆

右下角是一个独立的虚拟摇杆，用于连续控制机器人移动方向和速度，属于另一套手动控制入口。

### 4. 中央激光扫描视图

页面中央显示的是机器人激光雷达扫描的二维可视化结果：

- 支持显示 `/scan` 类激光数据
- 支持视角居中
- 支持锁定相机角度跟随机器人朝向
- 支持清除航点
- 支持查看或编辑路径点

### 5. 航点相关操作

页面里还提供了和航点有关的功能：

- `Recenter`：将视图重新居中
- `Clear Waypoints`：清除当前航点
- `Lock Camera Angle`：锁定相机角度，让视角跟随机器人朝向

## 图中元素分别是什么

### 蓝色三角形 / 蓝色机器人标记

机器人朝向指示，固定在激光**视图中心**，不随 `/odom` 平移。不是障碍物，也不是 SLAM 地图上的像素点。

`LaserScanRenderer.onDrawFrame()` 中在变换后的原点调用 `Utils.drawShape()` 绘制。

### 紫色方块

表示 `RobotController` 本次生命周期收到的**第一帧 `/odom` 位置**所建立的相对原点，会随行驶在屏幕上移动。它不是原始 ROS `odom` 坐标系的绝对 `(0,0)`，也不是 SLAM `/map` 上的点。

渲染器虽然对 `(0,0)` 调用 `drawPoint()`，但 `RobotController.getX()/getY()` 已经是 `currentPos - startPos`，因此这里的 `(0,0)` 属于首帧平移后的相对坐标系。

### 四周密集的小点 / 放射状线条

这些是激光雷达扫描点。

它们来自机器人实时采集到的距离数据，经过渲染后会围绕机器人中心展开，所以视觉上像一圈圈从中心往外发散的点和线。

如果某个方向特别密，通常表示那个方向上有墙面、障碍物或距离更近的物体。

### 额外的点和连线

如果你看到一串有顺序的点或连线，那通常是航点路径，不是激光噪点。

这些点一般会被渲染成不同颜色，用来区分：

- 第一个航点
- 普通航点
- 当前正在移动的航点

## 和 SLAM 地图页的区别

这个页面不是 SLAM 栅格地图页，所以它不等于：

- `/map` OccupancyGrid 地图
- PGM/YAML 保存的建图结果
- 传统意义上的“黑白方格地图”

它更偏向实时感知和控制，用来观察机器人周围激光回波、当前位置、朝向，以及手动驱动。本页**不在** SLAM 栅格地图上标定小车位置；位姿链路见下一节。

## 位姿数据链

机器人页只接 **`/scan` + `/odom`**，不经过 gmapping、`/map`、`/robot_pose_in_map` 或 move_base。

```text
车端传感器 / 底盘
  ├─ 轮速、IMU 等 → xtark_driver / odom_ekf
  │                    └─ 发布 /odom
  │                    └─ 广播 TF: odom → base_footprint
  │
  └─ 激光雷达 → /scan（laser 坐标系，经 TF 与车体对齐）
           │
           ├────────────────────────────┐
           ▼                            ▼
    Android 订 /scan              Android 订 /odom
    LaserScanRenderer           RobotController.setOdometry()
           │                            │
           ├─ 激光点：机体坐标系          ├─ startPos = 本会话首帧 position
           │  绕视图中心展开              ├─ currentPos = 后续帧 position
           │                            ├─ getX/Y = currentPos − startPos
           │                            ├─ getHeading() → 车体朝向
           │                            │
           ▼                            ├─→ HUDFragment（速度、位姿文字）
    蓝三角：永远在屏幕中心               ├─→ 未锁朝向：相机绕 heading 旋转
    （不随 odom 平移）                   └─→ drawPoint(0,0)：紫块 = 首帧相对原点
           │                                 相对当前车体的位置
           │
           └─ 航点：screenToWorld / drawPoint
              用 getX、getY、heading 做坐标换算

（链在此结束）
```

| 层级 | 话题 | 在机器人页的用途 |
|------|------|------------------|
| 底盘反馈 | `/odom` | 朝向、相对首帧位移、HUD、首帧相对原点紫块、航点换算 |
| 激光 | `/scan` | 点云与扇面，机体坐标系，画在视图中心周围 |
| 手动控制 | `/cmd_vel` | 左下按钮 / 摇杆经 `RobotController` 发布（出站，非位姿输入） |

**`/odom` 在 App 内的记法：**

- `startPos`：`RobotController` 创建后**收到的第一帧** `/odom` 的 `position`（不是上电瞬间，也不是 map 原点）。
- `currentPos`：第二帧及以后每帧的 `position`；首帧只写 `startPos`，不写 `currentPos`。
- `getX()` / `getY()`：`currentPos − startPos`，表示相对「连接后第一帧」的位移。

这里的基准属于 `RobotController` 生命周期，不是每次进入 Robot 页面都重置。通常重启 App、重建控制器并重新连接后才会重新采集首帧。

实现入口：

- 激光：`LaserScanFragment` → `LaserScanView` → `LaserScanRenderer.onNewMessage(LaserScan)`
- 里程计：`RobotController` 订阅可配置话题（默认 `/odom`）→ `setOdometry()` → `getX()` / `getY()` / `getHeading()`
- 绘制：`LaserScanRenderer.onDrawFrame()`、`drawPoint()`、`screenToWorld()`

## 简单图例

- 蓝色三角形：机器人（永远在激光视图中心）
- 紫色方块：本次连接首帧 `/odom` 建立的相对原点
- 密集放射点：激光雷达扫描点
- 线状路径：航点轨迹
- 左下按钮：手动驾驶
- 右下摇杆：连续控制
- 顶部栏：速度、转角、GPS、Wi-Fi、急停状态

## Qt 基本功能对齐边界

截至 2026-06-23，Qt 工作区“机器人”页按本项目确认的基本范围对齐 Android：

| 能力 | Android | Qt 当前实现 |
|------|---------|-------------|
| 实时激光 | 直接订阅 ROS `/scan` | 经 JSON `laser_scan` 接收真实 `/scan`，没有模拟激光回退 |
| 视图交互 | 居中、拖动/缩放、锁定机器人朝向 | 居中、拖动/滚轮缩放、锁定机器人朝向 |
| 图元 | 起点、机器人、激光点和放射扇面 | 同类图元，并额外保留蓝色连续墙体轮廓 |
| 手动按钮 | 六向运动 + 停止，按住运动、松开停车 | 六向运动 + 停止，约 10Hz 重发，松开/失焦/离页停车 |
| HUD | 速度、转速、GPS、布局相关 Wi-Fi、告警、停止/恢复计划 | 连接、电压、速度、转速、位姿、告警和“停止” |

以下内容是确认过的范围差异，不算 Qt 缺陷：

- Qt 不提供右下角虚拟摇杆；六向控制统一使用按钮。
- Qt 暂不提供航点查看、编辑和清除，也不在“机器人”页做导航。
- Qt HUD 暂不显示 GPS 和 Wi-Fi；HUD 是摄像头页与机器人页共用组件。
- Qt 顶部“停止”只发送零速度，不实现 Android 自动模式下的计划暂停/恢复，也不是硬件急停。
- 当前 MEC + XAS 真车的 `base_footprint -> laser` 外参约为 `x=0.05m, yaw=pi`；Qt 在绘制前应用该外参，所以画面不保证与 Android 原始 OpenGL 结果逐像素一致。

告警语义仍需真车确认：Android `WarningSystem` 按原始扫描角 `+-40 deg` 判断前方，并加入当前转速修正；Qt 的机器人端 `scan_warning` 目前同样取原始扫描角 `+-40 deg`，但没有转速修正，也没有应用上述 `yaw=pi` 外参。默认机器人配置已关闭 `warning_enabled` / `warning_safemode`，未完成确认前不要把 HUD 红色提示当作可靠硬件避障。

---

## 备注

如果后续要把这个页面讲给别人听，建议直接说：

> 这是 Android 端的机器人实时控制与激光扫描页，不是 SLAM 地图页。

这样最不容易混淆。
