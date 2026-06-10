# Android Map 功能说明

本文说明 RobotCA Android 端侧边栏 `Map` 页面的现有实现边界，避免把它和 SLAM 建图地图混淆。

## 结论

当前 Android 端 `Map` 页面显示的是基于 osmdroid/OpenStreetMap 的 GPS 街道地图，不是 SLAM 栅格地图。

它的主要用途是：在有 GPS 的户外场景中，显示机器人和 Android 设备在真实地理坐标中的位置。

它当前不订阅 `/map`，不处理 `nav_msgs/OccupancyGrid`，也没有 PGM/YAML 地图导出或保存功能。

## 入口

侧边栏菜单项来自：

- `src/android_foo/control_app/src/main/res/values/strings.xml`
- `feature_titles` 数组中的 `Map`

实际 fragment 映射在：

- `src/android_foo/control_app/src/main/java/com/robotca/ControlApp/ControlApp.java`
- `selectItem()` 中 `case 4` 创建 `new MapFragment()`

注意：`feature_titles` 是显示顺序，Java `switch` 使用 0-based 索引，所以 `Map` 显示为第 5 项，对应代码里的 `case 4`。

## 显示内容

实现文件：

- `src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Fragments/MapFragment.java`

页面核心控件是：

- `org.osmdroid.views.MapView`

地图瓦片源是：

```java
mapView.setTileSource(TileSourceFactory.MAPNIK);
```

因此底图是 OpenStreetMap MAPNIK 风格的街道瓦片，依赖网络下载或 osmdroid 缓存。

页面上叠加了两个定位 overlay：

- 机器人位置：`MyLocationNewOverlay(locationProvider, mapView)`
- Android 设备位置：`MyLocationNewOverlay(mapView)`

其中机器人位置来自 ROS GPS 话题；Android 设备位置来自手机/平板自身定位能力。

## ROS 话题依赖

默认 GPS 话题配置在：

- `src/android_foo/control_app/src/main/res/values/strings.xml`

```xml
<string name="navsat_topic">/navsat/fix</string>
```

订阅逻辑在：

- `src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/RobotController.java`

`RobotController.refreshTopics()` 会创建：

```java
navSatFixSubscriber = connectedNode.newSubscriber(navSatTopic, NavSatFix._TYPE);
```

消息类型是：

- `sensor_msgs/NavSatFix`

位置桥接在：

- `src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/LocationProvider.java`

`LocationProvider` 实现了 osmdroid 的 `IMyLocationProvider`，收到 `NavSatFix` 后把：

- `navSatFix.getLatitude()`
- `navSatFix.getLongitude()`

写入 Android `Location`，再通知地图 overlay 更新位置。

## 交互行为

`MapFragment` 当前实现的交互包括：

- 点击地图：弹出该点经纬度 toast
- 长按地图：在该经纬度放置旗帜标记
- `Center View` 短按：跟随并居中到机器人 GPS 位置
- `Center View` 长按：跟随并居中到 Android 设备自身位置

这些交互都基于地理坐标，经纬度单位不是 SLAM map/odom 坐标系。

## 与 SLAM 地图的区别

SLAM 建图通常使用：

- topic: `/map`
- message: `nav_msgs/OccupancyGrid`
- map frame: 通常是 `map`
- 输出文件：`map.pgm` + `map.yaml`

当前 Android 端没有这些实现：

- 未订阅 `nav_msgs/OccupancyGrid`
- 未读取 `/map` 栅格数据
- 未把栅格地图绘制到 `MapFragment`
- 未调用 `map_saver`
- 未调用 `slam_toolbox` 的 `save_map` 服务
- 未实现 Android 本地 PGM/YAML 导出

所以这个页面不能用于查看室内 SLAM 栅格地图，也不能保存建图结果。

## 没有 GPS 时的表现

如果机器人没有 GPS，或 ROS 侧没有发布 `/navsat/fix`：

- 机器人位置 overlay 不会得到有效经纬度更新
- `Center View` 短按居中到机器人时可能看不到有效机器人位置
- Android 设备自身定位仍可能显示，取决于设备定位权限和定位服务
- OSM 底图能否显示取决于网络或缓存

对于 xtark 这类主要依赖激光雷达/里程计做室内 SLAM 的机器人，这个 `Map` 页通常不是核心地图功能。

## 推荐的地图保存方式

如果目标是保存 SLAM 建图结果，推荐在 PC/ROS 端完成：

- ROS 1 常见方式：运行 `map_server` 的 `map_saver`
- slam_toolbox：调用对应的 `save_map` 服务

这样保存的是 ROS 栅格地图，格式通常为：

- `*.pgm`
- `*.yaml`

这比在 Android 端重新实现栅格地图订阅、坐标变换、渲染和导出更稳定。

## 如果要扩展 Android 端

若确实需要 Android 端显示或保存 SLAM 地图，需要新增功能，而不是复用现有 `MapFragment` 的 OSM/GPS 逻辑。

建议扩展点：

- 在 `RobotController` 中新增 `/map` 订阅
- 消息类型使用 `nav_msgs/OccupancyGrid`
- 在新的 fragment 或改造后的地图 fragment 中渲染栅格数据
- 明确处理 `map` 坐标系、origin、resolution、width、height
- 如需保存，按 OccupancyGrid 数据生成 PGM，并生成匹配的 YAML 元数据

如果同时保留 OSM/GPS 地图和 SLAM 栅格地图，建议在 UI 文案上区分：

- `GPS Map` 或 `Street Map`：现有 OSM/GPS 页面
- `SLAM Map`：新增 `/map` 栅格地图页面
