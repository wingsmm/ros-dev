# ros-dev

本仓库同时保留两代机器人产品线。两代系统的 ROS 版本、部署目标、客户端和运行脚本彼此独立，不混用。

## 产品线

| 产品线 | 组成 | 状态 | 权威入口 |
|---|---|---|---|
| 一代 ROS1 | xtark 小车 + VMware 控制端 + Android RobotCA | **冻结维护版** | [xtark/README.md](xtark/README.md) |
| 二代 ROS2 | Jetson + cockpit + Unitree L1 + Point-LIO | **当前开发主线，等待底盘改进** | [jetson/README.md](jetson/README.md) |

## 一代 ROS1

一代使用 xtark 真机上的 ROS1 Melodic，VMware 作为 ROS1 图形控制端，Android RobotCA 直接连接真机 ROS Master。

- 真机与 ROS 包：[xtark/README.md](xtark/README.md)
- VMware 客户端：[vmware/README.md](vmware/README.md)
- Android 客户端：[android/README.md](android/README.md)

该产品线已经冻结：不升级 Ubuntu、ROS、Gradle、Android SDK 或 rosjava，不新增产品功能，不与二代 ROS2 合并。只处理阻塞性 bug、部署恢复、安全问题和文档纠错；功能扩展必须先明确解除冻结。

## 二代 ROS2

二代由 Jetson 运行 ROS2 Humble、自研 cockpit、Unitree L1、Point-LIO 和 odom adapter。当前已经完成短距离人工搬运的定位观测闭环，物理位移可在 VMware RViz 中连续显示，但尚未完成导航级精度验收。

- Jetson 目录与运行边界：[jetson/README.md](jetson/README.md)
- Unitree L1 权威方案：[jetson/docs/宇树L1对接方案.md](jetson/docs/宇树L1对接方案.md)
- cockpit 观测端：[jetson/cockpit/README.md](jetson/cockpit/README.md)

当前卡点是底盘改进。底盘能够稳定行走后，再完成 3～5 米直行、往返和转向验收，随后进入台阶识别与相机互补。

## 环境边界

- VMware 是两代系统各自的图形观测端，但两代使用不同 ROS 环境和不同客户端目录。
- 项目运行、编译、DDS、RViz、部署和验收只认两代产品线各自列出的目标机与 VMware 客户端。
- Codex 的可选 SSH 透传规则见 [AGENTS.md](AGENTS.md)；任何透传环境都不能代替目标机证据。
- IP 地址属于现场部署配置，不属于产品版本基线，以各远端登录或 `.env` 文档为准。
