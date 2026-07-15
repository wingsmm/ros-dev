# 历史：WSL DDS 观测端排障记录

> 本文只保存 2026-07-09 的历史排障证据。WSL 已退出项目运行环境，不再用于 ROS2、DDS、RViz、编译、部署或验收。当前支持的 cockpit/RViz 观测端是 VMware。

## 当时现象

```text
WSL eth1: 172.0.0.52/24
Jetson: 172.0.0.82
ip route get 172.0.0.82 -> dev eth1 src 172.0.0.52
WSL -> Jetson ping: success
Jetson -> WSL ping: success
WSL ros2 topic list: only /parameter_events and /rosout
```

双向 ROS2 multicast 测试均未收到：

```text
WSL ros2 multicast send    -> Jetson receive: not received
Jetson ros2 multicast send -> WSL receive: not received
```

## 历史结论

问题位于 Windows/WSL 与 Jetson 之间的 DDS discovery/multicast 环境，不是 L1 硬件、串口、SSH、colcon 或 RViz 配置问题。阶段一随后由 VMware 完成 `/unilidar/cloud`、`/unilidar/imu`、频率和 RViz 点云闭环。

该问题不再安排修复。Codex 如需借用 WSL，只能将其作为 SSH 透传层；透传成功不能作为 ROS2 运行证据。
