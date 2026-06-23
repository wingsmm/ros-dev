# Project Memory / 项目备忘

最后整理日期：2026-06-15

## 1. 当前主线

本仓库当前主线是移动平台外挂感知与建图联调：

```text
RK3568   -> 传感器采集盒，Docker 内发布 ROS2 /scan、/camera/*
xtark    -> 底盘与里程计来源，ROS1 + JSON 适配，TCP 8765
WSL2/PC  -> 统一联调中心，运行 pc/qt_client
```

技术路线已经跑通，后续进入“调系统”阶段，重点是稳定性：

```text
/scan 频率
/odom_base 频率
TF: odom -> base_link -> laser
slam_toolbox 丢帧与建图质量
```

## 2. 日常入口

优先看：

```text
PROJECT_MEMORY.md
pc/README.md
pc/docs/WSL2统一栈运行与调试.md
pc/qt_client/README.md
```

日常启动：

```bash
cd /mnt/d/Downloads/work/ros-dev/pc/qt_client
./run.sh
```

仅验证 JSON：

```bash
./run.sh --no-ros
```

## 3. 三端状态

### RK3568

用途：Astra / RPLidar 采集节点。

关键路径：

```text
rk3568/README.md
rk3568/docs/
rk3568/deploy/sensor_stack/
```

远端运行目录：

```text
~/sensor_stack
```

当前关键容器：

```text
astra-camera
```

确认命令：

```bash
docker ps
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  export ROS_DOMAIN_ID=0
  ros2 topic hz /scan
'
```

### xtark

用途：底盘运动、里程计和 JSON 底盘验证平台。

关键路径：

```text
xtark/docs/
xtark/xtark_json_bridge/
```

车端需要两个前台服务：

```bash
roslaunch xtark_driver xtark_bringup.launch
roslaunch xtark_json_bridge json_base_adapter.launch
```

`json_base_adapter` 监听：

```text
0.0.0.0:8765
```

注意：

```text
没有 xtark_bringup 就没有 /odom；
没有 /odom 就没有完整 odom_base；
只启动 json_base_adapter 时，base_status 可能在线，但 battery_v 可能为 null。
```

### WSL2 / PC

用途：统一联调中心。

原则：

```text
WSL2 原生 apt 安装 ROS2 Humble；
不使用 WSL2 Docker ROS2 做跨机 DDS 验收；
Qt GUI 也在 WSL2 下运行；
RViz2 / slam_toolbox 由 qt_client 启停。
```

关键路径：

```text
pc/qt_client/
pc/tools/
pc/docs/
```

## 4. 当前代码入口

```text
pc/qt_client/app.py
pc/qt_client/json_client.py
pc/qt_client/ros2_pub.py
pc/qt_client/ros_stack.py
pc/qt_client/widgets/stack_panel.py
pc/qt_client/config/slam_toolbox_xtark.yaml

pc/tools/check_links.py
pc/tools/send_cmd_vel_json.py
pc/tools/xtark_json_keyboard.py

xtark/xtark_json_bridge/scripts/json_base_adapter_node.py
```

## 5. 当前文档结构

```text
pc/docs/WSL2统一栈运行与调试.md     当前主线：运行、验收、稳定性调试
pc/docs/移动平台外挂感知建图导航方案.md 总体架构
pc/docs/底盘JSON对接协议草案.md       底盘协议
pc/docs/archive/                     历史方案

rk3568/docs/                         RK3568 传感器部署
xtark/docs/                          xtark 小车本体与 JSON 适配
android/docs/                        Android / RobotCA 文档
```

### Android / RobotCA

RobotCA Android 客户端已整理为独立目录，不再从 `other/other/android` 运行：

```text
android/
```

日常入口：

```bat
cd /d D:\Downloads\work\ros-dev\android
scripts\build_app.bat
scripts\install_mumu.bat
..\xtark\scripts\android_remote.bat all
..\xtark\scripts\android_remote.bat status
```

约定：

```text
默认 APK 包名：cn.xtark.robotca，避免覆盖原 Release 的 com.robotca.ControlApp
编译依赖保存在 android/tools/jdk8 和 android/tools/rosjava_mvn_repo
机器人端 Android 专用脚本源文件：xtark/scripts/android_stack.sh
Android/RobotCA 直接连接 ROS master，不启动 json_base_adapter
json_base_adapter 只用于 PC Qt client
```

Android 根目录约定：

```text
android/scripts/ 保存 Windows 侧构建、部署、远程启动脚本
android/docs/ 保存 Android/RobotCA 文档
android/RobotCA-master/ 保存源码
android/apks/xtark-control-alt-debug.apk 为当前推荐安装包产物
机器人端 android_stack.sh 不再放在 android/ 根目录，统一维护在 xtark/scripts/android_stack.sh
```

Android SLAM / A-B-A 导航当前状态：

```text
SLAM 地图页面已支持设 A、设 B、去 B、返回 A、A-B-A、取消
Android 发布 /move_base_simple/goal，订阅 /move_base/status，取消走 /move_base/cancel
A/B 点会在地图上显示，A 蓝色，B 红色
目标点使用 SlamMapView.isFreeForGoal() 校验白色 free 栅格和约 3 格安全半径
当前 APK 不硬性限制 A/B 必须在黄色设定框内；黄色框作为 gmapping 设定区域提示
该功能已安装到 MuMu，机器人端 android_stack.sh 默认启动 move_base，下一步直接 start 后做实车验证
```

Android 手动控制注意：

```text
左下角手工按钮和右下角摇杆都走 RobotController.forceVelocity() -> /cmd_vel -> xtark_driver
这条链路会经过 RobotCA SafeMode
SafeMode 是前向碰撞预警 + 安全减速，不是完整自主避障
HUD 红色预警时，前进速度会按 (1 - warnAmount)^2 被压低
现象可能表现为“后退/转向正常，但前进不灵活”
详细说明：android/docs/Android手动控制与SafeMode说明.md
```

Android 文档命名约定：

```text
Markdown 文档优先使用中文文件名，专业术语保留英文。
例如：Android地图功能说明.md、SLAM地图开发方案.md、自主导航开发方案.md。
同一主题的设计方案使用“开发方案”，调试和现状说明使用“功能说明”或“说明”。
```

## 6. 卸载 Codex 前必须保留

当前仓库存在大量未提交文件，尤其：

```text
pc/qt_client/ros2_pub.py
pc/qt_client/ros_stack.py
pc/qt_client/widgets/stack_panel.py
pc/qt_client/config/slam_toolbox_xtark.yaml
pc/qt_client/run.sh
pc/qt_client/check_ros2.py
pc/qt_client/fonts.py
pc/qt_client/gen_run_sh.py
pc/docs/WSL2统一栈运行与调试.md
pc/docs/archive/WSL2_ROS2联调方案归档.md
pc/docs/archive/WSL2统一栈方案归档.md
```

卸载 Codex 前建议至少执行：

```bash
git status --short
git diff --stat
```

并把当前工作区提交或打包备份。

## 7. 复活顺序

1. 打开仓库：

```text
D:\Downloads\work\ros-dev
```

2. 先读：

```text
PROJECT_MEMORY.md
pc/README.md
pc/docs/WSL2统一栈运行与调试.md
```

3. 确认三端：

```text
RK3568 astra-camera 容器在线
xtark bringup + json_base_adapter 在线
WSL2 原生 ROS2 可见 /scan
```

4. 启动 WSL2 统一客户端：

```bash
cd /mnt/d/Downloads/work/ros-dev/pc/qt_client
./run.sh
```

5. 在 GUI 中：

```text
连接 xtark
确认 odom_base / base_status
一键启动建图栈
低速遥控
检查 RViz2 / SLAM
```

## 8. 不要再走的旧路线

```text
VMware 直连 USB 相机 / 雷达
WSL2 Docker ROS2 做跨机 DDS 验收
Windows 原生 Qt + WSL2 ROS2 分裂运行
xtark 上雷达参与建图
```

## 9. 敏感信息

密码、token、Codex 凭据不要写入仓库。远端登录信息只记录主机、用户、IP，密码手动输入或临时提供。

## 10. Windows 命令约定

在 Windows 侧操作时，优先使用 `cmd` 或项目内临时 `.bat` 脚本。

原因：

```text
PowerShell 在本项目里多次遇到双引号、$env、重定向、分号参数被外层解析的问题。
Android SDK / Gradle / rosjava 这类命令参数复杂时，使用 .bat 更稳定。
```

约定：

```text
复杂命令写成临时 .bat 后运行；
需要环境变量时在 .bat 内 set JAVA_HOME / ANDROID_HOME / PATH；
完成任务后清理一次性脚本、残留下载碎片和无用临时目录；
保留真正有复用价值的构建脚本，并在结果说明里点明。
```

## 11. 2026-06-11 Android A-B-A 导航进展

今日 Android/xtark 自主导航主线进入实车验证阶段：

```text
Android SLAM 地图
  -> 设置 A/B
  -> 发布 /move_base_simple/goal
  -> move_base 规划
  -> /cmd_vel 控车
  -> /move_base/status 返回 SUCCEEDED
```

已经确认：

- 机器人端 `xtark/scripts/android_stack.sh` 默认启用 gmapping + move_base。
- `SLAM_XMIN/XMAX/YMIN/YMAX` 当前按 4m x 4m 小空间配置。
- `/map`、`/scan`、`/odom`、TF、`/move_base/status` 正常。
- `/robot_pose_in_map` 已发布，约 10Hz，用于 Android 显示小车位置。
- Android SLAM 地图已支持 A/B、去 B、返回 A、A-B-A、取消。
- A-B-A 实车链路已经跑通，move_base 可返回 `Goal reached`。
- 手动按钮 `左移/右移/左转/右转` 的符号已修正，避免和车头方向相反。

当前主要问题不是“导航未实现”，而是稳定性和可观测性：

```text
在线 gmapping 可能导致 map->odom 跳变，路径看起来诡异；
goal yaw 当前仍可能固定为 0，后续需改为当前车头朝向或目标方向；
导航期间 Android 仍可能通过摇杆/手动按钮抢 /cmd_vel；
当前还不能在 SLAM 地图上显示 move_base 规划线。
```

明日优先实现：

```text
android/docs/导航路径可视化开发方案.md
```

推荐后续顺序：

```text
1. 订阅并绘制 /move_base/NavfnROS/plan
2. 导航期间锁定 Android 手动 /cmd_vel 输出
3. goal yaw 使用当前车头朝向或 A->B 方向
4. 多次实车测试 A-B-A
5. 稳定后切换到 保存地图 + map_server + amcl + move_base
```
