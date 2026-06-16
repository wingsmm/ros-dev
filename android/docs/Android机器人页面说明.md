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
- Wi-Fi 信号强度
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

这是机器人当前位置和朝向指示，不是障碍物，也不是地图点。

代码里会先画一个起始参考点，再画机器人本体和朝向标记。

### 紫色方块

你怀疑得很对，这个通常就是起始点 / 参考原点。

代码中在 `(0, 0)` 位置专门绘制了一个浅紫灰色的起始位置标记，所以它更像“世界原点”或“起点参考”，不是普通激光点。

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

它更偏向实时感知和控制，用来观察机器人周围激光回波、当前位置、朝向，以及手动驱动。

## 简单图例

- 蓝色三角形：机器人
- 紫色方块：起点 / 原点
- 密集放射点：激光雷达扫描点
- 线状路径：航点轨迹
- 左下按钮：手动驾驶
- 右下摇杆：连续控制
- 顶部栏：速度、转角、GPS、Wi-Fi、急停状态

## 备注

如果后续要把这个页面讲给别人听，建议直接说：

> 这是 Android 端的机器人实时控制与激光扫描页，不是 SLAM 地图页。

这样最不容易混淆。
