# 一代 ROS1：xtark 冻结维护版

`xtark/` 是一代 ROS1 产品线的机器人端权威入口。该产品线由 xtark 真机、VMware ROS1 客户端和 Android RobotCA 组成，现已进入**冻结维护**状态。

## 冻结基线

| 组件 | 固定基线 | 职责 |
|---|---|---|
| xtark 真机 | Jetson Nano、Ubuntu 18.04.5、ROS Melodic | ROS Master、底盘与传感器驱动、SLAM、导航 |
| VMware | Ubuntu 18.04.5、ROS Melodic、Python 3 + PyQt5 | 纯 ROS1 客户端、RViz、诊断与手动遥控 |
| Android | RobotCA + rosjava，现有 Gradle/Android SDK 工具链 | 直连真机 ROS Master 的移动客户端 |

冻结后不升级 Ubuntu、ROS、Gradle、Android SDK 或 rosjava，不新增产品功能，不与二代 Jetson ROS2 合并。只接受阻塞性 bug、部署恢复、安全问题和文档纠错；功能扩展必须先明确解除冻结。

## 固定运行入口

| 场景 | 机器人端入口 | 客户端 |
|---|---|---|
| Android | `scripts/android_stack.sh` | `../android/`，直接连接 ROS1 Master |
| VMware | `scripts/pc_stack.sh` | `../vmware/qt/` |

两套机器人端栈互斥，具体启停和冲突规则见 `scripts/README.md`。一代 ROS1 不调用 `jetson/` 下的 ROS2 脚本。

## ROS 运行包

| Path | Responsibility |
|------|----------------|
| `xtark_nav/` | SLAM, navigation, costmap configuration, and map-overlay ROS nodes. |
| `xtark_json_bridge/` | JSON bridge used by PC/Qt tools to command or inspect the robot. |
| `xtark_depth_preview/` | Phase 1.5: depth 16UC1 → pseudo-color `/camera/depth/preview` for MJPEG. |
| `xtark_laser_odometry/` | RF2O laser odometry (`/odom_laser`) for Qt compare page. |

Runtime nodes should live inside a ROS package, not in `xtark/scripts/`.

## 部署与诊断脚本

| Path | Responsibility |
|------|----------------|
| `scripts/android_stack.sh` | Starts the Android validation stack on the robot: roscore, bringup, camera, gmapping, move_base, pose relay, and speed sync. |
| `scripts/android_remote.bat` | Windows helper: deploy / start / stop / status / logs for the Android validation stack. |
| `scripts/deploy_json_bridge.bat` | Windows helper: sync and restart the JSON bridge package. |
| `scripts/deploy_laser_odom_compare.bat` | Windows helper: sync and run the laser odometry compare stack. |
| `scripts/json_stack.sh` | Starts the PC/Qt JSON bridge validation stack on the robot. |
| `tools/analyze_laser_odom_bag.py` | Offline rosbag analysis for laser odometry experiments. |

`xtark/scripts/` 只放编排、部署和诊断脚本，长期运行节点必须放在 ROS 包内。入口划分见 `scripts/README.md`。

## 客户端代码

客户端位于本目录之外：

| Path | Responsibility |
|------|----------------|
| `../android/` | 冻结版 Android RobotCA、构建脚本和说明文档。 |
| `../vmware/` | 冻结版 VMware ROS1/PyQt5 客户端。 |

`jetson/` 属于二代 ROS2 自研产品线，不是本产品线的客户端或升级路径。

## 目录规则

- Robot capability or ROS topic provider: put it in a ROS package under `xtark/`.
- Remote startup, sync, status, or log collection: put it in `xtark/scripts/` or a client-specific `scripts/` directory.
- Android-only UI behavior: keep it under `android/`.
- VMware Qt behavior: keep it under `vmware/`.
