# VMware Qt 纯客户端实现与测试报告

日期：2026-07-03

环境：

- 真机 `192.168.1.168`：xtark / ROS Melodic
- VM `192.168.1.154`：Ubuntu 18.04 / ROS Melodic
- Windows 部署机

## 目标与架构

原 `pc/qt_client` 的深度链路较长，卡顿明显。本轮改为使用官方 VMware 开发 VM 作为 ROS1 纯客户端：直连小车 Master，在 VM 本地用 RViz / `image_view` 看流，绕开 PC/WSL 侧桥接。

职责划分：

| 位置 | 组件 | 职责 |
|------|------|------|
| 小车 169 | `xtark/scripts/pc_stack.sh` | `roscore`、bringup、相机、深度、雷达；手动 `camera-start` / `radar2d-start` / `full-start` |
| VM 154 | `vmware/qt` | 连 Master、环境检查、topic 诊断、本地 RViz + `image_view`；不 SSH、不远程启脚本 |
| Windows | `pc_stack_remote.bat` | 部署/控制真机 `pc_stack` |
| Windows | `vmware/scripts/vm_qt_remote.bat` | 仅同步 `vmware/qt` + PyQt5 到 VM |

```text
小车 169 -- ROS Master / topics --> VM 154 (vmware/qt)
     ^
     Windows: pc_stack_remote.bat deploy / camera-start
```

## 交付物

VM 客户端 `vmware/qt/`：

```text
vmware/qt/
├── app.py
├── main_window.py
├── run.sh
├── config/
│   ├── rviz_mapping.rviz
│   ├── rviz_depth_light.rviz
│   ├── rviz_rgb_depth_diag.rviz
│   └── vmware_client.env.example
├── core/
│   ├── env.py
│   ├── ros1_probe.py
│   ├── rviz_commands.py
│   ├── rviz_process.py
│   ├── process_manager.py
│   └── logging_config.py
└── ui/
    ├── status_panel.py
    ├── rviz_panel.py
    ├── topic_panel.py
    └── log_panel.py
```

真机栈：

- `xtark/scripts/pc_stack.sh`
- `xtark/scripts/pc_stack_modules.sh`
- `xtark/scripts/pc_stack_remote.bat`

VM 部署脚本：

- `vmware/scripts/vm_qt_remote.bat`

## 实现要点

Qt 主界面能力：

| 区域 | 功能 |
|------|------|
| 环境状态 | 显示 `ROS_MASTER_URI`、`ROS_IP`、Master 可达、RViz 运行 pid |
| 检查环境 | 本地 `which rviz`、`rostopic list` |
| RViz | 三档配置单选 + 启动/停止，只管理本客户端启动的进程 |
| Topic 诊断 | 5 个关键 topic publisher 检查 |
| 深度诊断 | `rostopic info/echo/hz` 深度链路 |
| 日志 | UI 面板 + `logs/vmware-console-YYYY-MM-DD.log` |

三种显示模式：

| 模式 | 配置文件 | RViz Displays | 额外窗口 | Fixed Frame |
|------|----------|---------------|----------|-------------|
| 激光/地图 | `rviz_mapping.rviz` | Grid、TF、Scan；Map/Odom 默认关 | 无 | `odom` |
| 深度轻量 | `rviz_depth_light.rviz` | Depth + RGB 小预览；TF 关 | RGB + Depth `image_view` | `camera_depth_optical_frame` |
| RGB+Depth 诊断 | `rviz_rgb_depth_diag.rviz` | RGB + Depth + TF；Scan 可选 | RGB + Depth `image_view` | `camera_depth_optical_frame` |

子进程管理：

- RViz 使用 `RvizProcessManager`，无 30s 超时。
- `image_view` 同样使用长驻进程管理器。
- RGB 节点名：`/vmware_rgb_view`。
- Depth 节点名：`/vmware_depth_view`。
- 深度轻量和 RGB+Depth 诊断会在启动 RViz 后自动启动双 `image_view`。
- 停止 RViz 时依次停止 RGB view、Depth view、RViz。

## 会话中修复的问题

| # | 现象 | 根因 | 修复 |
|---|------|------|------|
| 1 | 激光 Global Error，无红点 | `rviz_mapping` 默认开 Map 无发布、LaserScan 字段不全、Fixed Frame 不当 | 关 Map/Odom；补全 Scan；Fixed Frame 改为 `odom` |
| 2 | 深度轻量 Global Error | `camera-start` 时 TF 无 `base_link` | Fixed Frame 改为 `camera_depth_optical_frame` |
| 3 | 深度全黑 + Panel 报错 | 误加 `Panels: rviz/Image`，Melodic 无此 Panel | 删除非法 Panel |
| 4 | RGB 预览消失 | 清理 Panel 时删掉 RGB Display | 恢复 RGB Display |
| 5 | 双 `image_view` 闪退 | 两进程同名 `/image_view` | 使用 `vmware_rgb_view` / `vmware_depth_view` |
| 6 | 诊断模式无大图 | 仅深度轻量开 `image_view` | RGB+Depth 诊断也开双窗 |
| 7 | 日志难排查 | 子进程日志标签和文件名不够明确 | 分进程标签 + 微秒戳分文件 |

## 测试结果

部署：

| 步骤 | 命令 | 结果 |
|------|------|------|
| 同步客户端 | `vmware\scripts\vm_qt_remote.bat deploy` | 成功 |
| 状态检查 | `vmware\scripts\vm_qt_remote.bat status` | `run.sh` 可执行，PyQt5 OK |

真机栈：

| 项 | 结果 |
|----|------|
| MODE | `camera`，并测过 `radar2d` / `full` |
| master | OK |
| `/scan` / `/odom` | publisher OK |
| `/camera/image_raw` | publisher OK |
| `/camera/depth/image_raw` | publisher OK |
| `/camera/depth/camera_info` | publisher OK |

VM topic 探测：

| Topic | 结果 |
|-------|------|
| `/camera/depth/image_raw` | 有 publisher；`frame_id=camera_depth_optical_frame` |
| `/camera/image_raw` | 有 publisher；`frame_id=camera_link` |
| 深度 hz | 一次短采样约 26 fps，另一次约 2.4 fps，存在短窗口波动 |
| RGB hz | 约 7 fps |

桌面验收：

| 模式 | 结果 |
|------|------|
| 激光/地图 | Global Status Ok，Scan 红点/轮廓可见；TF 橙警告可接受 |
| 深度轻量 | Global Status Ok，RViz 深度/RGB 小预览有画面，RGB/Depth `image_view` 大图有画面 |
| RGB+Depth 诊断 | RViz + RGB image_view + Depth image_view 均启动；深度诊断收到 1 帧；子进程日志无 ERROR |

## 标准使用流程

一次性准备：

```bat
vmware\scripts\vm_qt_remote.bat bootstrap
xtark\scripts\pc_stack_remote.bat deploy
```

每次联调：

```bash
# 小车 169
~/ros_ws/scripts/pc_stack.sh camera-start
# 或 radar2d-start / full-start
```

```bash
# VM 154
cd ~/ros-dev/vmware/qt
./run.sh
```

Qt 内：

1. 点 `检查环境`，确认 Master 可达。
2. 按场景选择模式并点 `启动 RViz`。
3. 使用 `检查关键 topic` / `深度诊断` 排查链路。

日志位置：

```text
~/ros-dev/vmware/qt/logs/
```

## 结论

VMware Qt 纯客户端 v1 已可用于日常深度验收与 RGB/深度/激光排查。它与 `pc/qt_client` 解耦，不依赖 VM 侧 `pc_stack`，通过小车侧 `pc_stack` 发布 ROS1 topic，再由 VM 本地 RViz / `image_view` 直连显示。
