# xtark 文档目录

当前项目目标：**Android 地图上显示已走过区域，并在已知可通行区域内完成 A/B 两点导航验证**。

## 当前主线

| 文档 | 定位 |
|------|------|
| `Android与xtark交互说明.html` | 当前 Android ↔ 小车主契约文档：11311、/scan、/map、/robot_pose_in_map、move_base、状态语义、路径显示、速度同步、部署顺序。 |
| `远端登录.md` | 给 agent/开发者用的远端登录与开发手册：SSH、plink、ROS 环境、远程检查。 |
| `远端硬件与传感器.md` | 远端设备总结：硬件、传感器、设备节点、ROS 话题，方便 agent 快速了解小车。 |
| `深度相机与机器人端相机功能梳理.md` | Android / Qt 端到端相机链路说明：Android 走 ROS 话题，Qt 走 HTTP/MJPEG。 |
| `机器人控制链路说明.md` | Android / Qt 手动控制与底盘反馈链路说明：控制最终落到 `/cmd_vel`；编码器、IMU、电压经 `xtark_driver` 回到 ROS，Qt 再经 JSON 收 `odom_base` / `base_status`。 |
| `激光里程计实验方案.md` | 使用现有 2D 雷达 `/scan` 生成 `/odom_laser` 的实验方案：先并行对比轮子 `/odom`，再决定是否接入 gmapping / move_base。实现见 `../xtark_laser_odometry/`。 |
| `Orbbec_Astra_Pro_深度相机资料.md` | Orbbec Astra Pro 深度相机集中资料：设备身份、USB ID、xtark/RK3568 话题、验收结果和维护边界。 |

## 保留参考

| 文档 | 定位 |
|------|------|
| `archive/JSON控制适配方案.md` | PC/Qt JSON 控制适配方案。当前先归档；Android 两点导航调通后，再做 Android/Qt 方案一致性整理。 |
| `archive/真机建图与遥控方案.md` | 早期学习/参考文档：借鉴别人的原生 ROS1 建图、遥控、保存地图流程。当前不作为主线。 |
| `archive/真机自主导航方案.md` | 早期学习/参考文档：保存地图后的 AMCL + move_base/TEB 完整导航。当前不作为主线。 |

## 当前只关注的链路

```text
/scan + /odom
  -> gmapping
  -> /map
  -> Android 显示已走过地图

map -> base_footprint TF
  -> xtark_nav/launch/robot_pose_in_map.launch
  -> /robot_pose_in_map
  -> Android 显示小车位置

Android A/B 点
  -> /move_base_simple/goal
  -> move_base
  -> /cmd_vel
  -> xtark_driver
```

## 当前怎么跑

```bat
xtark\scripts\android_remote.bat all
xtark\scripts\android_remote.bat status
xtark\scripts\android_remote.bat stop
```

Android App 的 ROS Master URI：

```text
http://192.168.1.169:11311
```

## 维护规则

- 当前可执行流程、远端登录、硬件速查留在根目录。
- 学习资料、旧方案、未来高级导航内容放入 `archive/`。
- 不删除历史参考，但 README 必须标清它们不是当前主线。
