# RobotCA Android SLAM Map 开发方案

## 1. 背景

当前 RobotCA Android 项目中侧边栏的 `Map` 页面是 osmdroid/OpenStreetMap GPS 街道地图，主要用于显示机器人和 Android 设备的经纬度位置。它不订阅 `/map`，不处理 `nav_msgs/OccupancyGrid`，也不具备 SLAM 地图显示或保存能力。

本方案目标是在现有 RobotCA App 内合入 `make_a_map` 类能力，新增一个独立的 `SLAM Map` 页面，用于显示 ROS SLAM 发布的栅格地图，并为后续地图保存、导航、地图管理功能打基础。

## 2. 总体目标

第一阶段目标是实现稳定的 SLAM 栅格地图查看能力：

- 订阅 ROS topic `/map`
- 解析 `nav_msgs/OccupancyGrid`
- 在 Android 端渲染栅格地图
- 支持拖动、缩放、居中
- 保留现有 GPS Map 页面，避免功能混淆

第二阶段再补充机器人位姿叠加和地图保存能力。

第三阶段再考虑导航和地图管理。

推荐功能顺序：

```text
make_a_map / SLAM Map
  -> map_nav
  -> map_manager
```

原因：

- 建图只依赖 `/scan`、`/odom`、gmapping 或其他 SLAM 节点，依赖较少
- 建图产出的 `pgm + yaml` 是后续导航输入
- `move_base`、`amcl`、`map_server` 参数配置较重，应在地图显示和保存稳定后再做

## 3. 关键设计决策

| 决策点 | 推荐方案 | 说明 |
|---|---|---|
| 菜单入口 | 新增 `SLAM Map`，保留原 `GPS Map` | 两者坐标系和用途不同，不建议复用一个页面 |
| 菜单位置 | 插入在 `Robot` 和原 `Map` 之间 | 室内机器人调试时 SLAM Map 优先级更高 |
| `/map` 订阅位置 | `RobotController` 集中订阅 | 与现有 `/scan`、`/odom`、`/navsat/fix` 模式一致 |
| 渲染方式 | 自定义 `View` + `Bitmap` 缓存 | 收到地图时生成 bitmap，`onDraw()` 只绘制 bitmap，性能稳定 |
| 坐标系 | 地图显示基于 OccupancyGrid 自身坐标 | 不使用 osmdroid，osmdroid 是经纬度坐标系 |
| 机器人位姿 | 优先使用 `map` frame 下的 pose 或 TF | 不建议直接把 `/odom` 叠加到 `/map` 上 |
| 地图保存 | 优先机器人端服务触发 `map_saver` | Android 端本地导出可作为备选，不作为第一优先级 |

## 4. 不推荐的实现方式

### 4.1 不建议复用现有 MapFragment

现有 `MapFragment` 使用：

- `org.osmdroid.views.MapView`
- `TileSourceFactory.MAPNIK`
- GPS 经纬度 overlay

SLAM `/map` 使用：

- `nav_msgs/OccupancyGrid`
- 栅格坐标
- meter-based map frame

两者坐标体系完全不同，强行复用会导致坐标转换复杂、语义混乱、后续维护困难。

### 4.2 不建议逐格实时 drawRect

直接在 `onDraw()` 中循环每个栅格并执行 `canvas.drawRect()`，在地图尺寸较大时容易卡顿。

推荐做法：

- 收到新的 `OccupancyGrid` 后，将栅格数据转换成 `Bitmap`
- `onDraw()` 使用 `canvas.drawBitmap()`
- 平移和缩放通过 `Matrix` 或 canvas transform 完成

### 4.3 不建议假设 gmapping 提供 save_map 服务

ROS1 `gmapping` 通常发布 `/map`，但并不提供标准的 `/slam_gmapping/save_map` 服务。

标准保存方式通常是：

```bash
rosrun map_server map_saver -f ~/maps/my_map
```

如果 Android 端要一键保存机器人端地图，需要机器人端额外提供一个服务或接口来触发上述命令。

## 5. 分阶段开发计划

## Phase 1: SLAM Map 显示

Phase 1 只做地图显示，不做保存，不做导航。

### 5.1 新增文件

#### `SlamMapView.java`

路径：

```text
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Views/SlamMapView.java
```

职责：

- 接收 `nav_msgs.OccupancyGrid`
- 将栅格数据转换为 `Bitmap`
- 绘制 bitmap
- 支持拖动、缩放、居中
- 显示地图基本信息：宽、高、分辨率、更新时间

核心接口：

```java
public void updateMap(OccupancyGrid grid);
public void recenter();
public void clear();
```

实现要点：

- `OccupancyGrid.info.width`
- `OccupancyGrid.info.height`
- `OccupancyGrid.info.resolution`
- `OccupancyGrid.info.origin`
- `OccupancyGrid.data`

栅格颜色建议：

| OccupancyGrid 值 | 含义 | 显示颜色 |
|---|---|---|
| `-1` | unknown | 中灰 |
| `0` | free | 白色 |
| `1..99` | probability | 灰阶插值 |
| `100` | occupied | 黑色 |

注意：rosjava 中 `OccupancyGrid.getData()` 的实际返回类型需要以本地 jar 编译结果为准，常见可能是 `org.jboss.netty.buffer.ChannelBuffer`。实现时不要先假设它一定是 Java `byte[]` 或 `int[]`。

#### `SlamMapFragment.java`

路径：

```text
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Fragments/SlamMapFragment.java
```

职责：

- 管理 `SlamMapView`
- 从 `RobotController` 注册 `/map` listener
- 在 fragment 生命周期中添加和移除 listener
- 提供 `Recenter` 按钮
- 显示连接状态或无地图提示

建议参考：

- `LaserScanFragment.java`
- `MapFragment.java`

注意事项：

- ROS 回调线程不能直接更新 UI
- 需要通过 `Activity.runOnUiThread()` 或 `View.post()` 调用 `SlamMapView.updateMap()`
- `onDestroyView()` 或 `onPause()` 中移除 listener，避免 fragment 泄漏

#### `fragment_slam_map.xml`

路径：

```text
src/android_foo/control_app/src/main/res/layout/fragment_slam_map.xml
```

布局建议：

- 主体：`SlamMapView`
- 底部工具栏：`Recenter`
- 状态文本：显示地图尺寸、分辨率、topic 状态

Phase 1 不放 `Save Map` 按钮，避免 UI 暗示保存能力已经可用。

### 5.2 修改文件

#### `RobotController.java`

新增 import：

```java
import nav_msgs.OccupancyGrid;
```

新增字段：

```java
private Subscriber<OccupancyGrid> mapSubscriber;
private OccupancyGrid occupancyGrid;
private final Object mapMutex = new Object();
private final ArrayList<MessageListener<OccupancyGrid>> mapListeners;
```

构造方法中初始化：

```java
this.mapListeners = new ArrayList<>();
```

新增 listener 方法：

```java
public boolean addMapListener(MessageListener<OccupancyGrid> listener);
public boolean removeMapListener(MessageListener<OccupancyGrid> listener);
public OccupancyGrid getOccupancyGrid();
```

`refreshTopics()` 中新增 `/map` 订阅：

```java
String mapTopic = PreferenceManager.getDefaultSharedPreferences(context)
        .getString(context.getString(R.string.prefs_map_topic_edittext_key),
                context.getString(R.string.map_topic));

if (mapSubscriber == null || !mapTopic.equals(mapSubscriber.getTopicName().toString())) {
    if (mapSubscriber != null) {
        mapSubscriber.shutdown();
    }

    mapSubscriber = connectedNode.newSubscriber(mapTopic, OccupancyGrid._TYPE);
    mapSubscriber.addMessageListener(new MessageListener<OccupancyGrid>() {
        @Override
        public void onNewMessage(OccupancyGrid grid) {
            setOccupancyGrid(grid);
        }
    });
}
```

新增内部方法：

```java
protected void setOccupancyGrid(OccupancyGrid grid) {
    synchronized (mapMutex) {
        occupancyGrid = grid;
    }

    synchronized (mapListeners) {
        for (MessageListener<OccupancyGrid> listener : mapListeners) {
            listener.onNewMessage(grid);
        }
    }
}
```

`shutdownTopics()` 中补充：

```java
if (mapSubscriber != null) {
    mapSubscriber.shutdown();
}
```

#### `strings.xml`

新增 topic 和 preference 文案：

```xml
<string name="map_topic">/map</string>
<string name="prefs_map_topic_edittext_key">prefs_map_topic_edittext</string>
<string name="map_topic_pref_title">Map Topic</string>
<string name="map_topic_pref_summary">Topic for SLAM occupancy grid.\nExpected message type: nav_msgs/OccupancyGrid\nValue: %s</string>
<string name="slam_map">SLAM Map</string>
<string name="gps_map">GPS Map</string>
<string name="slam_map_recenter">Recenter</string>
<string name="slam_map_waiting">Waiting for /map...</string>
```

调整 `feature_titles`：

```xml
<string-array name="feature_titles">
    <item>Select Robot</item>
    <item>Overview</item>
    <item>Camera</item>
    <item>Robot</item>
    <item>SLAM Map</item>
    <item>GPS Map</item>
    <item>Preferences</item>
    <item>About</item>
</string-array>
```

中文资源 `values-zh-rCN/strings.xml` 也应同步添加。

#### `prefs.xml`

在 topic 设置组中新增：

```xml
<com.robotca.ControlApp.Views.BetterEditTextPreference
    android:defaultValue="@string/map_topic"
    android:key="@string/prefs_map_topic_edittext_key"
    android:singleLine="true"
    android:summary="@string/map_topic_pref_summary"
    android:title="@string/map_topic_pref_title" />
```

#### `ControlApp.java`

新增 import：

```java
import com.robotca.ControlApp.Fragments.SlamMapFragment;
```

抽屉图标数组 `imgRes` 需要新增一项，保证长度和 `feature_titles` 一致。

推荐复用：

```java
R.drawable.ic_terrain_black_24dp
```

`selectItem()` 中调整：

```java
case 3:
    fragment = new LaserScanFragment();
    break;

case 4:
    fragment = new SlamMapFragment();
    break;

case 5:
    fragment = new MapFragment();
    break;

case 6:
    // Preferences
    break;

case 7:
    // About
    break;
```

注意同步所有与 drawer index 相关的逻辑，避免 Preferences/About 错位。

#### `build.gradle`

项目已经使用 `nav_msgs.Odometry`，说明 `nav_msgs` 可能已通过 rosjava 依赖传递存在。

推荐先尝试不改依赖直接编译。如果 `OccupancyGrid` 无法解析，再显式增加：

```gradle
compile 'org.ros.rosjava_messages:nav_msgs:1.12.7'
```

本地 maven 仓库中已存在：

```text
android/tools/rosjava_mvn_repo/org/ros/rosjava_messages/nav_msgs/1.12.7/
```

## Phase 2: 机器人位姿叠加

Phase 2 在 SLAM Map 稳定显示后实现。

### 6.1 不建议直接使用 `/odom`

`/map` 是 map frame，`/odom` 是 odom frame。直接把 `/odom` 坐标绘制到 `/map` 上会出现偏移或漂移。

正确输入应满足以下条件之一：

- 位姿已经在 `map` frame 下
- Android 端能计算 TF：`map -> odom -> base_link`
- 机器人端发布一个专用 pose topic，例如 `/robot_pose_in_map`

### 6.2 推荐方案

优先推荐机器人端发布简化 pose：

```text
topic: /robot_pose
type: geometry_msgs/PoseStamped
frame_id: map
```

Android 端只订阅该 topic，并在 `SlamMapView` 中将 pose 转换成栅格坐标。

转换公式：

```text
grid_x = (pose_x - origin_x) / resolution
grid_y = (pose_y - origin_y) / resolution
```

绘制时需要注意 Android Canvas 的 Y 轴方向与 OccupancyGrid 逻辑坐标方向可能不同，应在 `Bitmap` 生成或绘制矩阵中统一处理。

## Phase 3: 地图保存

Phase 3 在地图显示稳定后实现。

### 7.1 推荐方案：机器人端保存

Android 端不要直接假设存在 gmapping save service。推荐在机器人端提供一个明确的保存接口：

```text
service: /xtark/save_map
request:
  string map_name
response:
  bool success
  string message
```

机器人端 service 内部执行：

```bash
rosrun map_server map_saver -f ~/maps/<map_name>
```

Android 端 `Save Map` 按钮只负责调用 `/xtark/save_map`，并显示保存结果。

优点：

- 保存位置固定在机器人端
- 格式标准：`pgm + yaml`
- 后续 `map_nav` 可直接加载
- Android 不需要处理文件传输和 ROS 地图格式细节

### 7.2 备选方案：Android 本地导出

Android 可从当前 `OccupancyGrid` 本地生成：

- `map.pgm`
- `map.yaml`

但它更适合作为调试或备份，不建议作为导航主流程。

原因：

- 文件还需要传回机器人
- Android 存储权限和路径兼容性复杂
- YAML 中 origin、resolution、occupied/free threshold 必须严格匹配 ROS 约定

## Phase 4: map_nav

导航依赖比建图更重，应在 SLAM Map 和地图保存跑通后实施。

机器人端需要：

- `map_server`
- `amcl`
- `move_base`
- global costmap 参数
- local costmap 参数
- planner 参数
- footprint / inflation / obstacle layer 配置

Android 端主要新增：

- 地图选择
- 发送 `move_base_simple/goal`
- 显示目标点
- 显示导航状态
- 支持取消目标

## Phase 5: map_manager

地图管理应放在最后。

它依赖机器人端已经有稳定地图目录和保存规范。

功能包括：

- 列出已保存地图
- 重命名地图
- 删除地图
- 选择导航地图
- 查看地图元信息

建议通过机器人端服务提供统一接口，而不是 Android 直接操作机器人文件系统。

## 8. 验证清单

### 8.1 编译验证

- Android 工程可完整编译
- `feature_titles` 数量和 drawer icon 数量一致
- `SlamMapFragment` 生命周期中 listener 正确添加和移除
- 无 `OccupancyGrid` 类型解析错误

### 8.2 机器人端验证

启动 SLAM：

```bash
rosrun gmapping slam_gmapping scan:=/scan
```

确认 topic：

```bash
rostopic echo /map -n 1
rostopic hz /map
```

### 8.3 App 端验证

- 侧边栏出现 `SLAM Map`
- 原 `GPS Map` 仍可进入
- 进入 `SLAM Map` 后能看到地图逐步更新
- 拖动和缩放流畅
- 离开页面后不会继续刷新已销毁的 view
- 断开 ROS 后不会崩溃

### 8.4 回归验证

- Joystick 控制正常
- LaserScan 页面正常
- Camera 页面正常
- Preferences 页面正常
- About 页面正常
- 原 GPS Map 页面正常

## 9. 建议最终文件变更清单

### 新增

```text
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Views/SlamMapView.java
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Fragments/SlamMapFragment.java
src/android_foo/control_app/src/main/res/layout/fragment_slam_map.xml
```

### 修改

```text
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/RobotController.java
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/ControlApp.java
src/android_foo/control_app/src/main/res/values/strings.xml
src/android_foo/control_app/src/main/res/values-zh-rCN/strings.xml
src/android_foo/control_app/src/main/res/xml/prefs.xml
src/android_foo/control_app/build.gradle
```

### 可选修改

如果需要把 `/map` topic 纳入每个机器人独立配置，而不仅是全局 Preferences，需要额外修改：

```text
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/RobotInfo.java
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/RobotStorage.java
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Dialogs/AddEditRobotDialogFragment.java
src/android_foo/control_app/src/main/res/layout/dialog_add_robot.xml
```

Phase 1 建议先使用全局 Preferences 配置 `/map`，降低改动范围。等 SLAM Map 稳定后，再决定是否扩展到每个 RobotInfo。

## 10. 推荐落地版本

推荐第一版只交付：

- 新增 `SLAM Map` 页面
- 订阅 `/map`
- Bitmap 渲染 OccupancyGrid
- 支持拖动、缩放、居中
- 保留原 GPS Map

暂不交付：

- 地图保存
- 导航目标下发
- 地图管理
- TF 计算

这样可以用最小改动快速验证核心链路：

```text
xtark gmapping -> /map -> RobotController -> SlamMapFragment -> SlamMapView
```

核心链路验证通过后，再逐步接入机器人位姿、保存地图和导航。
