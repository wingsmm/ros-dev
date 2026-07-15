# vmware

塔克官方 VMware 虚拟开发机 `xtark-vmpc`（`192.168.1.154`，Ubuntu 18.04 + ROS Melodic）在本仓库的落地目录。

> **产品状态：一代 ROS1 冻结维护版。** 版本基线与维护规则见 [xtark/README.md](../xtark/README.md)。本目录不升级 ROS/Ubuntu/PyQt，不接入二代 Jetson ROS2。

职责与真机 `xtark-robot`（`192.168.1.168`）严格分开：VM 只做**纯客户端**（本地 RViz + topic 诊断 + 手动 `/cmd_vel` 遥控），不跑 roscore、不跑相机 / 雷达驱动。ROS Master 由真机侧的 `pc_stack` 提供，VM 通过 `ROS_MASTER_URI=http://192.168.1.168:11311` 加入。

## 目录结构

```text
vmware/
├── docs/       文档集，见下表
├── qt/         VM 上运行的 PyQt5 客户端源码（部署目标：/home/xtark/ros-dev/vmware/qt）
├── ros_ws/     VM 侧 catkin workspace 的源码快照（仅 src/ + .catkin_workspace，不含构建产物与脚本）
└── scripts/    Windows 侧远端管理脚本（部署 qt/ 到 VM）
```

各子目录用途：

| 目录 | 说明 | 权威源 |
|------|------|--------|
| `docs/` | VMware VM 相关设计与联调文档 | 本目录 |
| `qt/` | VM 上的 PyQt5 客户端，`app.py` / `main_window.py` / `core/` / `ui/` / `config/` / `.env`；`run.sh` 是 VM 侧入口 | 本目录（部署源） |
| `ros_ws/src/` | VM 出厂的两个 catkin 包 `xtark_ctl`（键盘遥控节点）+ `xtark_viz`（RViz 配置合集），供仓库离线查阅 | VM `/home/xtark/ros_ws/src`（只读快照） |
| `scripts/` | `vm_qt_remote.bat`（同步 qt/ 到 VM、装 PyQt5、远程 run）+ `.env`（PLINK/PSCP、VM SSH 变量） | 本目录 |

`ros_ws/` 不含 `build/` / `devel/` / `scripts/`。VM 上原有的 `~/ros_ws/scripts/pc_stack.sh` 是旧客户端启动器（RViz + 键盘 teleop），已被 `qt/` 全面取代，本地和 VM 端都已清理，不再维护。真机侧的 `pc_stack` 请看 `xtark/scripts/`（同名但职责相反，是机器人侧 bringup / camera / radar2d 入口）。

## 文档索引

| 文档 | 定位 |
|------|------|
| [docs/VMware开发环境.md](./docs/VMware开发环境.md) | VM 实探测、ROS 网络、`~/ros_ws` 布局 |
| [docs/VMware Qt客户端整体方案.md](<./docs/VMware Qt客户端整体方案.md>) | VMware Qt 纯客户端实施方案 |
| [docs/VMware Qt纯客户端实现与测试报告.md](<./docs/VMware Qt纯客户端实现与测试报告.md>) | 2026-07-03 实现结果与验收记录 |
| [docs/VMware Qt深度相机增强方案.md](<./docs/VMware Qt深度相机增强方案.md>) | 深度 preview、VM 本地点云、第四档增强模式 |
| [docs/VMware Qt基础遥控与RViz联动方案.md](<./docs/VMware Qt基础遥控与RViz联动方案.md>) | 五键 `/cmd_vel` 遥控与 RViz 联动 |
| [docs/VMware Qt雷达里程计联调指南.md](<./docs/VMware Qt雷达里程计联调指南.md>) | 雷达/里程计：障碍、TF、遥控移动、RViz 验收 |
| [qt/README.md](./qt/README.md) | PyQt5 客户端使用与 `.env` 配置 |
| [scripts/README.md](./scripts/README.md) | Windows 侧远端脚本入口 |

相关（真机 / 全仓库入口）：

- [xtark/docs/远端登录.md](../xtark/docs/远端登录.md) — 真机 SSH / plink / ROS 环境
- [xtark/scripts/pc_stack.sh](../xtark/scripts/pc_stack.sh) — 真机 ROS 服务栈（配 VMware Qt）
- [xtark/scripts/pc_stack_remote.bat](../xtark/scripts/pc_stack_remote.bat) — Windows 部署/启停真机 `pc_stack`

## 快速命令

一次性准备（Windows）：

```bat
vmware\scripts\vm_qt_remote.bat bootstrap
```

日常使用：

```bash
# 真机 169（SSH 登录后手动，仓库里由 xtark/scripts 部署）
~/ros_ws/scripts/pc_stack.sh camera-start        # 或 camera-deep-start / radar2d-start / full-start
```

```bat
rem VM 154（Windows 一键起 GUI）
vmware\scripts\vm_qt_remote.bat run
```

## Git 与本地文件规则

- 本目录已有 `.gitignore` 忽略 `__pycache__/`、`*.pyc`、`logs/`
- 仓库根 `.gitignore` 默认忽略 `.env`，但对 `vmware/qt/.env` 开了白名单（VM 客户端的运行时配置需要入库）
- `vmware/scripts/.env` 含明文 SSH 口令，仍走默认忽略，不要 `-f` 强推
- `ros_ws/src/CMakeLists.txt` 在 VM 上是软链到 `/opt/ros/melodic/share/catkin/cmake/toplevel.cmake`；pscp 拉回后是普通文件，仅供查阅，不要当作源文件修改
