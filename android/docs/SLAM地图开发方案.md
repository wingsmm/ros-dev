# SLAM 地图与 A-B-A 往返导航开发方案

## 1. 目标收敛

当前目标不是实现完整的室内任意点自主导航，也不是追求整张 gmapping 画布全部探索完成。

当前要实现的最小闭环是：

```text
在 SLAM 地图中选择 A 点和 B 点
  -> 小车从当前位置或 A 点导航到 B 点
  -> 到达 B 点后再导航返回 A 点
```

约束条件：

- A 点和 B 点必须落在已探索的白色可通行区域。
- A 到 B 的路径优先位于黄色设定区域与绿色已探索区域的有效交集内。
- 当前 Android 第一版不硬性限制 A/B 必须在黄色框内；它只强制目标点落在白色 free 栅格并通过周边安全半径校验。黄色框用于提示 gmapping 设定区域和调试参考。
- 不支持让小车主动进入灰色未知区域。
- 不要求 Android 端自己做路径规划。
- Android 端只负责显示地图、选择点、下发目标和显示导航状态。
- 机器人端 ROS 负责建图、定位、路径规划、避障和底盘控制。

这一路线最稳妥，因为 Android 端不承担导航算法，只使用 ROS 标准导航链路。

## 2. 当前实现状态

### 2.1 已实现

Android 端已经完成以下能力：

- 新增 `SLAM 地图` 页面。
- 订阅 `/map`，消息类型为 `nav_msgs/OccupancyGrid`。
- 使用 `SlamMapView` 将栅格地图渲染为 bitmap。
- 支持地图拖动、缩放、居中。
- 显示 gmapping 地图画布大小、分辨率、已探索范围。
- 显示黄色设定区域：来自 `/slam_gmapping/xmin`、`xmax`、`ymin`、`ymax` 或 Android 设置。
- 显示绿色已探索范围。
- 统计整张地图栅格比例。
- 统计设定区域内的空闲、障碍、未知比例。
- 订阅并显示 `/scan` 频率、`/odom` 状态、gmapping entropy。
- 在 SLAM 地图上选择 A 点、B 点。
- 将触摸像素坐标转换为 `/map` 坐标。
- 校验 A/B 点是否位于白色可通行栅格，并检查周边安全半径。
- 在地图上显示 A/B 标记。
- 发布导航目标到 `/move_base_simple/goal`。
- 订阅 `/move_base/status` 显示导航状态。
- 支持取消导航目标。
- 支持一键执行 `去 B -> 返回 A`。
- 使用悬浮菜单提供 `设 A`、`设 B`、`去 B`、`返回 A`、`A-B-A`、`取消`、`居中` 操作。

相关文件：

```text
android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Fragments/SlamMapFragment.java
android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Views/SlamMapView.java
android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/SlamMapDiagnostics.java
android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/SlamMapStats.java
android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/RobotController.java
android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Views/SlamFloatingNavMenu.java
android/RobotCA-master/RobotCA-master/src/android_foo/control_app/src/main/res/layout/view_slam_floating_nav_menu.xml
xtark/scripts/android_stack.sh
```

### 2.2 尚未实车验证或后续优化

Android 端后续可优化：

- 若必须限制小车只在 4m x 4m 黄色框内活动，可在 `SlamMapView.isFreeForGoal()` 中额外加入 configured bounds 校验。
- 可根据 A->B 方向自动设置 goal yaw，当前第一版固定 yaw=0。
- 可订阅并显示 `/move_base/NavfnROS/plan` 或实际 planner plan，当前第一版不画真实规划路径。
- 可把 `/move_base_simple/goal`、`/move_base/status`、`/move_base/cancel` 做成 Preferences 配置项，当前第一版写死标准 topic。

机器人端尚未实车完成：

- `~/ros_ws/scripts/android_stack.sh start` 后 `move_base` 是否实际正常运行。
- costmap 参数是否适合当前 xtark 小车和现场空间。
- 小车 footprint / inflation / obstacle layer 是否配置正确。
- Android 发布 B 点后，小车是否能真实从当前位置到 B。
- `A-B-A` 往返是否能稳定完成。
- 稳定版本是否切换为保存地图后的 `map_server + amcl + move_base`。

## 3. 关键结论

### 3.1 红色小方块不是小车初始位置

LaserScan 页面中的红色小方块通常表示激光雷达当前扫到的障碍点或反射点。

真正代表小车当前姿态的是视图中心的蓝色箭头。

### 3.2 整张地图未知比例不是核心指标

gmapping 发布的 `/map` 画布可能自动扩展，实际画布可能远大于设定的 4m x 4m 区域。

因此调试时应优先看：

```text
设定区域栅格：空闲 xx%，障碍 xx%，未知 xx%
```

而不是只看：

```text
整张地图栅格比例：未知 xx%
```

### 3.3 当前需求只需要局部可通行区域

只要 A/B 点和它们之间的路径附近存在连续白色通道，就可以做 A-B-A 往返导航测试。

不需要整张黄色框全部探索完成。黄色框是推荐活动范围和 gmapping 参数提示；当前 Android 第一版不把黄色框作为硬边界。

## 4. 推荐总体架构

```text
Android SLAM 地图页面
  - 显示 /map
  - 选择 A/B 点
  - 校验目标点
  - 发布导航目标
  - 显示 move_base 状态

ROS 导航栈
  - gmapping 或 map_server
  - amcl 或在线 SLAM 位姿
  - move_base
  - global costmap
  - local costmap
  - scan obstacle layer

小车底盘
  - 接收 /cmd_vel
  - 发布 /odom
  - 发布 /scan
  - 提供 TF: odom -> base_footprint -> laser
```

### 4.1 车端位姿链（从传感器到 SLAM 地图上车标）

SLAM 地图页上的小车位置**不是**把 `/odom` 的 x、y 直接画到 `/map` 像素上。Android `SlamMapFragment` 订阅 `/map` 与 `/robot_pose_in_map`，在栅格图上画车标；`/robot_pose_in_map` 由车端查 TF 得到，上游依次经过里程计、建图与 TF 串联。

```text
车端传感器 / 底盘
  ├─ 轮速、IMU 等 → xtark_driver / odom_ekf
  │                    └─ 发布 /odom
  │                    └─ 广播 TF: odom → base_footprint
  │
  └─ 激光雷达 → /scan
           │
           ▼
      gmapping（android_stack 启动）
           ├─ 输入: /scan + /odom
           ├─ 输出: /map（OccupancyGrid）
           └─ 广播 TF: map → odom
           │
           ▼
      move_base（导航栈）
           └─ 用 /map + /odom + costmap 规划路径
           │
           ▼
      publish_robot_pose_in_map.py（xtark_nav）
           └─ lookupTransform(map, base_footprint)
           └─ 发布 /robot_pose_in_map（map 坐标系 PoseStamped）
           │
           ▼
      Android SlamMapFragment / SlamMapView
           └─ mapWorldToBitmap(x, y) 把车标画在 /map 栅格上
```

TF 可记为：

```text
T_map→base = T_map→odom × T_odom→base
              ↑ gmapping      ↑ /odom 对应 TF
```

| 层级 | 话题 / 产物 | 坐标系 | 说明 |
|------|-------------|--------|------|
| 底盘反馈 | `/odom` | `odom` | 轮速/IMU 积分或 EKF 后的里程计 |
| 建图 | `/map` + `map→odom` | `map` | gmapping 用 `/scan`+`/odom` 建图并修正 map 与 odom 关系 |
| 地图上车标 | `/robot_pose_in_map` | `map` | `xtark_nav` 查 TF 后发布，供 `SlamMapView.setRobotPose()` |
| 导航 | `/move_base_simple/goal` 等 | `map` | 目标点与规划路径均在 map 系 |

实现入口：

- 车端：`xtark/xtark_nav/scripts/publish_robot_pose_in_map.py`
- Android 订阅与绘制：`SlamMapFragment` → `robotPoseInMapListener` → `SlamMapView.setRobotPose()` → `drawRobotPose()` / `mapWorldToBitmap()`

Android 与 ROS 的接口：

| 功能 | Topic | 类型 | 方向 |
|---|---|---|---|
| 地图显示 | `/map` | `nav_msgs/OccupancyGrid` | ROS -> Android |
| 地图上车标 | `/robot_pose_in_map` | `geometry_msgs/PoseStamped` | ROS -> Android |
| 激光诊断 | `/scan` | `sensor_msgs/LaserScan` | ROS -> Android |
| 里程计诊断 | `/odom` | `nav_msgs/Odometry` | ROS -> Android |
| 下发导航目标 | `/move_base_simple/goal` | `geometry_msgs/PoseStamped` | Android -> ROS |
| 导航状态 | `/move_base/status` | `actionlib_msgs/GoalStatusArray` | ROS -> Android |
| 取消导航 | `/move_base/cancel` | `actionlib_msgs/GoalID` | Android -> ROS |
| 底盘控制 | `/cmd_vel` | `geometry_msgs/Twist` | move_base -> 小车 |

## 5. 机器人端方案

### 5.1 建图阶段

当前 4m x 4m 测试区域推荐参数：

```bash
SLAM_XMIN=-2
SLAM_XMAX=2
SLAM_YMIN=-2
SLAM_YMAX=2
SLAM_DELTA=0.10
SLAM_MAX_URANGE=2.0
SLAM_MAX_RANGE=2.5
SLAM_LINEAR_UPDATE=0.20
SLAM_ANGULAR_UPDATE=0.20
SLAM_TEMPORAL_UPDATE=2.0
SLAM_MAP_UPDATE_INTERVAL=1.0
```

gmapping 启动要点：

```bash
rosrun gmapping slam_gmapping \
  scan:=/scan \
  _base_frame:=base_footprint \
  _xmin:=-2 _xmax:=2 _ymin:=-2 _ymax:=2 \
  _delta:=0.10 \
  _maxUrange:=2.0 _maxRange:=2.5 \
  _linearUpdate:=0.20 _angularUpdate:=0.20 \
  _temporalUpdate:=2.0 _map_update_interval:=1.0 \
  __name:=slam_gmapping
```

注意：

- xtark 当前没有 `base_link`，需要使用 `base_footprint`。
- gmapping 的 `/map` 画布可能仍会自动扩展，Android 端应以设定区域统计为准。
- 如果只做 A-B-A 测试，地图不需要覆盖整个房间，只要 A/B 及路径附近是已知白色区域。

### 5.2 导航阶段推荐路线

推荐分两种路线，先做路线 A。

#### 路线 A：在线 SLAM + move_base

用于快速验证 A-B-A 闭环。

```text
gmapping 发布 /map
gmapping/TF 提供 map -> odom
move_base 使用当前 /map 和 /scan
Android 发布 /move_base_simple/goal
```

优点：

- 不需要先保存地图。
- 适合当前调试阶段。
- 可以快速验证 A-B-A 能否跑通。

风险：

- 在线建图过程中地图会继续变化，路径可能抖动。
- 长时间运行可能受 odom 漂移影响。

#### 路线 B：保存地图 + map_server + amcl + move_base

用于稳定演示和长期使用。

```text
先用 gmapping 建好局部地图
  -> map_saver 保存 pgm/yaml
  -> 下次启动 map_server 加载地图
  -> amcl 定位
  -> move_base 导航
```

优点：

- 地图固定，导航更稳定。
- 更接近 ROS 标准导航流程。

风险：

- 初始位姿需要设置。
- amcl 参数和 costmap 参数需要调试。

本项目建议：

```text
先用路线 A 跑通 A-B-A
再切换路线 B 做稳定版本
```

### 5.3 move_base 最小配置要求

机器人端需要确认以下链路存在：

```bash
rostopic list | grep move_base
rostopic echo /move_base/status -n 1
rostopic echo /move_base_simple/goal -n 1
rostopic echo /cmd_vel -n 1
```

TF 应至少满足：

```text
map -> odom -> base_footprint -> laser
```

costmap 初始建议：

| 参数 | 建议值 | 说明 |
|---|---:|---|
| global_frame | `map` | 全局规划使用 map |
| robot_base_frame | `base_footprint` | 匹配 xtark TF |
| local_costmap width | `3.0` | 4m 区域内够用 |
| local_costmap height | `3.0` | 4m 区域内够用 |
| resolution | `0.05` 或 `0.10` | 先与地图一致可降低复杂度 |
| inflation_radius | `0.15` 到 `0.25` | 根据车体尺寸调整 |
| obstacle_range | `2.0` | 匹配当前激光有效范围 |
| raytrace_range | `2.5` | 匹配当前 scan/maxRange |

## 6. Android 端开发方案

### 6.1 新增导航交互状态

在 `SlamMapFragment` 或独立控制类中维护：

```java
enum NavPointMode {
    SET_A,
    SET_B,
    NONE
}

enum RoundTripState {
    IDLE,
    GOING_TO_B,
    RETURNING_TO_A,
    FINISHED,
    FAILED,
    CANCELED
}
```

保存点位：

```java
PoseStamped pointA;
PoseStamped pointB;
RoundTripState roundTripState;
```

### 6.2 地图点选

`SlamMapView` 需要暴露触摸点到 map 坐标的转换。

屏幕坐标转 bitmap 坐标：

```text
bitmap_x = (touch_x - translateX) / scale
bitmap_y = (touch_y - translateY) / scale
```

bitmap 坐标转 map 坐标：

```text
map_x = origin_x + bitmap_x * resolution
map_y = origin_y + (height - bitmap_y) * resolution
```

注意：

- 当前 bitmap 绘制时对 Y 轴做了翻转，所以转换时必须与 `mapRectToBitmapRect()` 保持一致。
- 点选 A/B 时应同时保存 `frame_id = "map"`。
- orientation 第一版可以固定为当前车头方向或默认朝向。

第一版可以先使用固定朝向：

```text
orientation.z = 0
orientation.w = 1
```

后续再根据 A->B 的路径方向自动设置 yaw。

### 6.3 目标点合法性校验

点选 A/B 后必须校验：

- 点位在地图范围内。
- 点位应优先在黄色设定区域内；当前 APK 第一版不做硬限制。
- 点位不是灰色未知。
- 点位不是黑色障碍。
- 点位周围至少保留一定安全半径。

建议第一版实现简单栅格校验：

```text
目标点所在 cell 必须 value == 0
目标点周围半径 2 到 3 个 cell 内不能有 occupied
```

若 `SLAM_DELTA=0.10`，半径 3 个 cell 约等于 0.3m。

当前代码状态：

```text
SlamMapView.isFreeForGoal()
  - 目标 cell 必须在地图范围内
  - 目标 cell 周围 3 格内不能有 unknown
  - 目标 cell 周围 3 格内不能有 occupied 或概率值 > 50
  - 未硬性检查黄色 configured bounds
```

失败提示：

```text
目标点不可用：请选择白色可通行区域
```

### 6.4 发布导航目标

新增 publisher：

```java
Publisher<PoseStamped> moveBaseGoalPublisher;
```

topic：

```text
/move_base_simple/goal
```

type：

```text
geometry_msgs/PoseStamped
```

消息内容：

```text
header.frame_id = "map"
header.stamp = connectedNode.getCurrentTime()
pose.position.x = selected_map_x
pose.position.y = selected_map_y
pose.position.z = 0
pose.orientation = quaternion_from_yaw(yaw)
```

第一版目标：

- 点击 `去 B`：发布 B 点。
- 点击 `返回 A`：发布 A 点。
- 点击 `A-B-A`：先发布 B 点，到达后自动发布 A 点。

### 6.5 订阅导航状态

新增 subscriber：

```java
Subscriber<GoalStatusArray> moveBaseStatusSubscriber;
```

topic：

```text
/move_base/status
```

type：

```text
actionlib_msgs/GoalStatusArray
```

需要处理的状态：

| status | 含义 | Android 行为 |
|---:|---|---|
| `1` | ACTIVE | 显示正在导航 |
| `3` | SUCCEEDED | 如果正在去 B，则发布 A；如果正在返回 A，则完成 |
| `4` | ABORTED | 标记失败 |
| `5` | REJECTED | 标记失败 |
| `2` | PREEMPTED | 标记取消或被新目标覆盖 |

A-B-A 状态机：

```text
IDLE
  -> 点击 A-B-A
  -> GOING_TO_B
  -> 收到 SUCCEEDED
  -> RETURNING_TO_A
  -> 收到 SUCCEEDED
  -> FINISHED
```

失败状态：

```text
GOING_TO_B 或 RETURNING_TO_A
  -> 收到 ABORTED / REJECTED
  -> FAILED
```

### 6.6 取消导航

新增 publisher：

```java
Publisher<GoalID> moveBaseCancelPublisher;
```

topic：

```text
/move_base/cancel
```

type：

```text
actionlib_msgs/GoalID
```

发布空 `GoalID` 可取消当前目标：

```text
stamp = 0
id = ""
```

Android 页面提供 `取消` 或复用 `停止`：

- 发布 `/move_base/cancel`
- 同时发布一次 `/cmd_vel` 零速度更稳妥
- 状态切换为 `CANCELED`

### 6.7 UI 设计

在 `SLAM 地图` 页面增加最小控制区：

```text
[设 A] [设 B] [去 B] [返回 A] [A-B-A] [取消]
```

地图显示：

- A 点：蓝色圆点或 `A` 标记。
- B 点：红色圆点或 `B` 标记。
- 当前目标点：高亮描边。
- 若订阅到 global plan，后续可显示路径线，第一版不强制。

面板显示：

```text
设定区域栅格：空闲 xx%，障碍 xx%，未知 xx%
导航状态：去 B / 返回 A / 已完成 / 失败
目标：A 或 B
```

注意：

- 不要把 A/B 点允许放到灰色未知区。
- 第一版 Android 通过 free 栅格和安全半径阻止灰色/黑色区域；如果现场要求“只能在黄色框内”，后续再加边界硬校验。
- 不要在 Android 端绘制一条蓝线就当成真实路径。真实路径应以后续 `/move_base/NavfnROS/plan` 或 `/move_base/DWAPlannerROS/local_plan` 为准。

## 7. RobotController 修改建议

新增字段：

```java
private Publisher<PoseStamped> moveBaseGoalPublisher;
private Publisher<GoalID> moveBaseCancelPublisher;
private Subscriber<GoalStatusArray> moveBaseStatusSubscriber;
private final ArrayList<MessageListener<GoalStatusArray>> moveBaseStatusListeners;
```

新增方法：

```java
public boolean publishMoveBaseGoal(double x, double y, double yaw);
public boolean cancelMoveBaseGoal();
public boolean addMoveBaseStatusListener(MessageListener<GoalStatusArray> listener);
public boolean removeMoveBaseStatusListener(MessageListener<GoalStatusArray> listener);
```

`refreshTopics()` 中初始化：

```java
moveBaseGoalPublisher =
    connectedNode.newPublisher("/move_base_simple/goal", PoseStamped._TYPE);

moveBaseCancelPublisher =
    connectedNode.newPublisher("/move_base/cancel", GoalID._TYPE);

moveBaseStatusSubscriber =
    connectedNode.newSubscriber("/move_base/status", GoalStatusArray._TYPE);
```

依赖如果缺失，优先检查本地 rosjava maven 仓库是否已有：

```text
geometry_msgs
actionlib_msgs
```

若编译找不到，再在 `build.gradle` 显式补充。

## 8. 实施阶段

### Phase 1：保持当前 SLAM 地图显示稳定

状态：基本完成。

验收：

- `/map` 能显示。
- `/scan` 约 14Hz。
- `/odom` 正常。
- 黄色设定区域显示正确。
- 设定区域栅格统计能显示。

### Phase 2：机器人端启动 move_base

目标：

- 能在 RViz 或命令行发布 `/move_base_simple/goal` 后让小车移动。

命令行测试示例：

```bash
rostopic pub /move_base_simple/goal geometry_msgs/PoseStamped "
header:
  frame_id: 'map'
pose:
  position:
    x: 0.5
    y: 0.0
    z: 0.0
  orientation:
    w: 1.0
" -1
```

验收：

- `/move_base/status` 有数据。
- `/cmd_vel` 会被 move_base 发布。
- 小车不会原地乱转或直接撞障碍。

### Phase 3：Android 实现 A/B 点选择

状态：已完成，待实车验证。

目标：

- 在地图上设置 A 点和 B 点。
- A/B 点显示在地图上。
- 点位坐标能导出到调试面板。
- 点位必须通过可通行校验。

验收：

- 点白色区域成功。
- 点灰色未知或黑色障碍会拒绝。
- 地图缩放/拖动后点选坐标仍正确。

### Phase 4：Android 下发单目标

状态：已完成，待实车验证。

目标：

- `去 B` 发布 B 点到 `/move_base_simple/goal`。
- `返回 A` 发布 A 点到 `/move_base_simple/goal`。

验收：

- 在 ROS 端能收到 goal。
- 小车能向目标移动。
- Android 能显示 ACTIVE / SUCCEEDED / FAILED。

### Phase 5：Android 实现 A-B-A 自动往返

状态：已完成，待实车验证。

目标：

- 点击 `A-B-A` 后自动执行：

```text
发布 B
  -> B 到达
  -> 发布 A
  -> A 到达
  -> 完成
```

验收：

- 小车从 A 附近出发能到 B。
- 到达 B 后能自动返回 A。
- 任一阶段失败时 Android 明确显示失败。
- 点击取消能停止当前导航。

### Phase 6：保存地图并切换稳定导航

目标：

- 将可用地图保存为 `pgm + yaml`。
- 使用 `map_server + amcl + move_base` 重复 A-B-A。

验收：

- 重启后不重新建图，也能跑 A-B-A。
- 初始定位完成后目标点仍然有效。

## 9. 验收标准

### 9.1 地图质量

最低要求：

- A 点、B 点均在白色区域。
- A/B 周围 0.2m 到 0.3m 内无黑色障碍。
- A 到 B 之间存在连续白色通路。
- 设定区域内未知比例不作为唯一指标，但路径附近不能大片未知。
- 若按当前 APK 第一版使用，A/B 可在黄色框外的已探索白色区域；若要严格 4m x 4m 活动范围，需要补充黄色框边界硬校验。

建议目标：

```text
设定区域未知 < 50% 可以开始局部测试
路径附近未知 < 20% 更适合导航
```

### 9.2 导航链路

必须满足：

- `/map` 正常。
- `/scan` 正常。
- `/odom` 正常。
- TF 正常。
- `/move_base/status` 正常。
- `/cmd_vel` 由 move_base 输出。

### 9.3 Android 交互

必须满足：

- 能设置 A/B。
- 能拒绝非法点。
- 能单独去 B。
- 能单独返回 A。
- 能一键 A-B-A。
- 能取消。
- 能显示失败原因或状态。

## 10. 风险与处理

| 风险 | 表现 | 处理 |
|---|---|---|
| 地图局部未知太多 | move_base 绕路或失败 | 在路径附近慢速移动、原地旋转补图 |
| 目标点靠近障碍 | 小车不敢过去或撞障碍 | 目标点校验加入安全半径 |
| TF 不完整 | move_base 报 transform 错误 | 确认 `map -> odom -> base_footprint -> laser` |
| odom 漂移 | 回 A 不准 | 保存地图后切换 AMCL |
| costmap 过保守 | 路很宽但规划失败 | 降低 inflation 或修正 footprint |
| costmap 过激进 | 贴障碍太近 | 增大 inflation 或 footprint |
| Android 坐标转换错误 | 点 A/B 后目标偏移 | 用 RViz 对比点击坐标和 goal 坐标 |

## 11. 推荐下一步

下一步不要继续扩大地图功能，直接进入实车验证：

```text
1. 机器人端执行 `~/ros_ws/scripts/android_stack.sh start` 启动 gmapping 和 move_base
2. Android 进入 SLAM 地图并连接 ROS master
3. 设置 A/B 到白色可通行区域
4. 先点“去 B”验证单程
5. 再点“返回 A”验证返程
6. 最后点“A-B-A”验证自动往返
```

第一版只要求在已探索白色区域内可靠往返，不要求任意区域、任意路线、地图管理或复杂巡航。

## 12. 2026-06-11 当前状态补充

今日实车验证表明，SLAM 地图 + A-B-A 导航 MVP 已经跑通：

- Android SLAM 地图能显示 `/map`。
- A/B 点能在白色 free 区域内设置并显示。
- Android 能发布 `/move_base_simple/goal`。
- move_base 能规划、输出 `/cmd_vel` 并返回 `Goal reached`。
- 机器人端已经具备 `/robot_pose_in_map`，Android 端可显示小车位置和朝向。
- 手动按钮方向已修正，`左移/右移/左转/右转` 与车头方向保持一致。

后续不再把“是否能导航”作为主要问题，重点转向：

```text
路径可视化
导航期间 /cmd_vel 发布权管理
目标朝向 yaw 优化
在线 SLAM 漂移下的调参
保存地图后切换 map_server + amcl
```

路径可视化单独见：

```text
android/docs/导航路径可视化开发方案.md
```
