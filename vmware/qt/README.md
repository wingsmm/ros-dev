# VMware Qt RViz 控制台 (v1)

VMware `192.168.1.154` 上的**纯客户端**：连接小车 ROS Master、本地 topic 诊断、本地 RViz。

**不 SSH、不远程启脚本、不需要 VM 本地 `pc_stack.sh`。**

## 架构

```text
小车 169：手动 pc_stack camera-start / radar2d-start / full-start
VM 154：./run.sh → 检查环境 + RViz + topic 诊断
```

## 依赖

- Ubuntu 18.04 + ROS Melodic
- Python 3 + PyQt5
- `source /opt/ros/melodic/setup.bash` 与 `~/ros_ws/devel/setup.bash`

```bash
sudo apt-get install -y python3-pyqt5
```

## 部署 Qt 到 VM（Windows）

```bat
vmware\scripts\vm_qt_remote.bat bootstrap
```

仅同步客户端，**不会**给 VM 部署 `pc_stack`。

## 日常使用

```bash
# 1. 小车 169（SSH 登录真机后手动）
~/ros_ws/scripts/pc_stack.sh camera-start
# 或
~/ros_ws/scripts/pc_stack.sh full-start

# 2. VM 154
cd ~/ros-dev/vmware/qt && ./run.sh
```

客户端内：

1. **检查环境** → `which rviz`、`rostopic list`
2. 选 **深度轻量** → **启动 RViz**
3. **深度诊断**

## 配置

```bash
cp config/vmware_client.env.example config/vmware_client.env
```

| 变量 | 默认 |
|------|------|
| `ROBOT_IP` | `192.168.1.169` |
| `ROS_MASTER_URI` | `http://192.168.1.169:11311` |
| `ROS_IP` | 自动检测 VM IP |

## RViz / Image View 模式

| 模式 | 配置文件 | 用途 | 额外窗口 |
|------|----------|------|----------|
| 激光/地图 | `config/rviz_mapping.rviz` | 看 `/scan`、TF、地图/里程计诊断 | 无 |
| 深度轻量 | `config/rviz_depth_light.rviz` | 深度验收首选，RViz 内小预览 | RGB + Depth `image_view` |
| RGB+Depth 诊断 | `config/rviz_rgb_depth_diag.rviz` | 同时看 RGB、Depth、TF | RGB + Depth `image_view` |

RViz 由 Qt 在本机 `rviz -d config/*.rviz` 启动。深度轻量和 RGB+Depth 诊断会额外启动两个本地 `image_view`：

- `/vmware_rgb_view` 订阅 `/camera/image_raw`
- `/vmware_depth_view` 订阅 `/camera/depth/image_raw`

停止 RViz 时，Qt 会按顺序停止本客户端启动的 RGB view、Depth view、RViz，不会依赖 VM 本地 `pc_stack.sh`。

## 日志

与 `pc/qt_client` 同款约定（目录默认 `vmware/qt/logs/`）：

| 文件 | 内容 |
|------|------|
| `logs/vmware-console-YYYY-MM-DD.log` | 客户端运行日志（按日滚动） |
| `logs/rviz_YYYYMMDD_HHMMSS_ffffff.log` | 每次「启动 RViz」的 stdout |
| `logs/image_view_rgb_YYYYMMDD_HHMMSS_ffffff.log` | RGB `image_view` stdout |
| `logs/image_view_depth_YYYYMMDD_HHMMSS_ffffff.log` | Depth `image_view` stdout |

环境变量（可写入 `config/vmware_client.env`）：

- `XTARK_LOG_DIR` — 默认 `logs`
- `XTARK_LOG_LEVEL` — 默认 `INFO`
- `XTARK_LOG_RETENTION_DAYS` — 默认 `30`

UI 面板显示 `ui` 日志；完整细节见当日 console 日志文件。

## 常见错误

| 现象 | 处理 |
|------|------|
| Master 不可达 | 小车上 `pc_stack camera-start` 或 `full-start` |
| `which rviz` 失败 | `sudo apt install ros-melodic-rviz` |
| 深度无 publisher | 小车 `pc_stack camera-check` |
| 深度轻量中间 3D 区域黑屏 | 正常；该模式不启用 Grid/点云，只看 Image / image_view |
| `camera_info` 无 subscribers | 正常；`image_view` 看图不需要 CameraInfo |
| SSH 启动 GUI 失败 | 正常；`image_view` / RViz 需要 VM 桌面 DISPLAY，日常在 VM 桌面 `./run.sh` |

## 验收状态（2026-07-03）

已在真机 `192.168.1.169` + VM `192.168.1.154` 上验证：

- `pc_stack camera/full` 可发布 `/scan`、`/odom`、RGB、Depth、`camera_info`。
- VM 侧深度 topic 可收帧，深度短采样曾测得约 26 fps，RGB 约 7 fps。
- 激光/地图、深度轻量、RGB+Depth 诊断三种模式均可显示。
- 深度轻量与 RGB+Depth 诊断均能启动 RViz + RGB image_view + Depth image_view。
