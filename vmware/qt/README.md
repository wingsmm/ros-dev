# VMware Qt RViz 控制台 (v1)

VMware `192.168.1.154` 上的**纯客户端**：连接小车 ROS Master、本地 topic 诊断、本地 RViz。

**不 SSH、不远程启脚本、不需要 VM 本地 `pc_stack.sh`。**

当前 v1 以显示和诊断为主；基础遥控是下一阶段计划，见
[VMware Qt基础遥控与RViz联动方案.md](../docs/VMware%20Qt基础遥控与RViz联动方案.md)。

## 架构

```text
小车 169：手动 pc_stack camera-start / camera-deep-start / radar2d-start / full-start
VM 154：./run.sh → 检查环境 + RViz + topic 诊断
```

## 依赖

- Ubuntu 18.04 + ROS Melodic
- Python 3 + PyQt5
- `source /opt/ros/melodic/setup.bash` 与 `~/ros_ws/devel/setup.bash`

```bash
sudo apt-get install -y python3-pyqt5
```

**深度增强**模式额外需要 VM 本地点云（不自动安装）：

```bash
sudo apt install ros-melodic-depth-image-proc
```

缺包时 Qt 会提示；仍可看 RViz Image / `image_view`，只是没有 `/vmware/depth/points`。

## 部署 Qt 到 VM（Windows）

```bat
vmware\scripts\vm_qt_remote.bat bootstrap
```

仅同步客户端，**不会**给 VM 部署 `pc_stack`。

## 日常使用

```bash
# 1. 小车 169（SSH 登录真机后手动）
~/ros_ws/scripts/pc_stack.sh camera-start      # 深度轻量
~/ros_ws/scripts/pc_stack.sh camera-deep-start # 深度增强（+ /camera/depth/preview）
# 或
~/ros_ws/scripts/pc_stack.sh full-start

# 2. VM 154
cd ~/ros-dev/vmware/qt && ./run.sh
```

客户端内：

1. **检查环境** → `which rviz`、`rostopic list`
2. **检查关键 topic** → RGB、Depth raw、Depth preview（增强模式需 preview）
3. 选模式 → **启动 RViz**
4. **深度诊断**（不要求点云 topic）

## 配置

`vmware/qt/.env` **与 `pc/qt_client/.env` 对齐**（以 pc-client 为基准）；共享段改一处请同步另一处。末尾 **VMware 专用** 段仅 VM 生效。

| 变量 | 说明 |
|------|------|
| `XTARK_HOST` | 机器人 IP（兼 `ROBOT_IP`） |
| `ROS_MASTER_URI` | 默认 `http://<XTARK_HOST>:11311` |
| `ROS_IP` | VM 本机 IP（可选，不设则自动检测） |
| `XTARK_LINEAR_SPEED` / `XTARK_ANGULAR_SPEED` | 遥控线/角速度 |
| `CAMERA_POINTCLOUD_STRIDE` 等 | 深度点云稀疏度（同 pc-client） |
| `CAMERA_X` … `CAMERA_YAW` | 相机外参（同 pc-client） |

VMware 专用：

| 变量 | 默认 |
|------|------|
| `CMD_VEL_TOPIC` | `/cmd_vel` |
| `TELEOP_REPEAT_HZ` | `10` |
| `TELEOP_ENABLE_KEYBOARD` | `1`（W/S/A/D + 方向键 dead-man） |
| `CAMERA_TF_ENABLE` | `1` |
| `XTARK_RVIZ_SOFTWARE_GL` | VM 段覆盖为 `1`（软件渲染） |

## RViz / Image View 模式

| 模式 | 配置文件 | 用途 | 小车命令 | 额外 VM 进程 |
|------|----------|------|----------|--------------|
| 雷达/里程计 | `config/rviz_mapping.rviz` | 看 `/scan`、TF（Map 默认关） | `radar2d-start` / `full-start` | 无 |
| 深度轻量 | `config/rviz_depth_light.rviz` | 深度卡顿验收基准 | `camera-start` | RGB + Depth `image_view` |
| RGB+Depth 诊断 | `config/rviz_rgb_depth_diag.rviz` | RGB+深度+TF 排错 | `camera-start` | RGB + Depth `image_view` |
| 深度增强 | `config/rviz_depth_enhanced.rviz` | 完整深度观察 + VM 点云 | **`camera-deep-start`** | RGB + Depth + Preview `image_view`，本地点云 |

RViz 由 Qt 在本机 `rviz -d config/*.rviz` 启动。

深度轻量 / RGB+Depth 诊断 / 深度增强会额外启动本地 `image_view`：

| 节点名 | Topic |
|--------|-------|
| `/vmware_rgb_view` | `/camera/image_raw` |
| `/vmware_depth_view` | `/camera/depth/image_raw` |
| `/vmware_depth_preview_view` | `/camera/depth/preview`（仅深度增强） |

深度增强还会在 VM 本地运行 `depth_image_proc/point_cloud_xyz`，发布 `/vmware/depth/points`（不增加小车算力）。

停止 RViz 时，Qt 按顺序停止 preview view、RGB/Depth view、点云进程、RViz。

## 基础遥控（下一阶段）

计划新增 `vmware/qt/ui/teleop_panel.py`，提供五键手动遥控：

```text
      前进
左转  停止  右转
      后退
```

行为要求：

- VM Qt 本地发布 ROS1 `geometry_msgs/Twist` 到 `/cmd_vel`。
- 按住运动，松开停止，约 10Hz 重发。
- 「左 / 右」先按原地转向处理：`angular.z` 正/负。
- 关闭窗口、切走焦点、应用失活时必须发布零速度。
- 这不是硬件急停，不做导航、地图、自动避障。

移动显示验收用「雷达/里程计」模式：小车先 `pc_stack radar2d-start` 或 `full-start`，RViz Fixed Frame 使用 `odom`，观察 `/odom`、`/scan`、TF 随运动实时刷新。

## 日志

与 `pc/qt_client` 同款约定（目录默认 `vmware/qt/logs/`）：

| 文件 | 内容 |
|------|------|
| `logs/vmware-console-YYYY-MM-DD.log` | 客户端运行日志（按日滚动） |
| `logs/rviz_YYYYMMDD_HHMMSS_ffffff.log` | 每次「启动 RViz」的 stdout |
| `logs/image_view_rgb_*.log` | RGB `image_view` |
| `logs/image_view_depth_*.log` | Depth raw `image_view` |
| `logs/image_view_preview_*.log` | Preview `image_view`（深度增强） |
| `logs/depth_point_cloud_*.log` | VM 本地点云 nodelet |

环境变量（可写入 `.env`）：

- `XTARK_LOG_DIR` — 默认 `logs`
- `XTARK_LOG_LEVEL` — 默认 `INFO`
- `XTARK_LOG_RETENTION_DAYS` — 默认 `30`

## 常见错误

| 现象 | 处理 |
|------|------|
| Master 不可达 | 小车上 `pc_stack camera-start` 或 `full-start` |
| 深度增强无 preview | 小车须 `pc_stack camera-deep-start`，不是 `camera-start` |
| `which rviz` 失败 | `sudo apt install ros-melodic-rviz` |
| 点云进程立即退出 | `sudo apt install ros-melodic-depth-image-proc` |
| 深度无 publisher | 小车 `pc_stack camera-check` |
| 深度轻量中间 3D 区域黑屏 | 正常；该模式不启用 Grid/点云，只看 Image / image_view |
| 点云竖起/飞天 | 优先查 TF：`base_link→camera_link→optical`；深度增强会启 VM static TF |
| 点云 Fixed Frame 报错 | 真机若无 `base_link`，试 `ROBOT_BASE_FRAME=base_footprint` |
| 点云竖起/飞到天上 | 优先查 TF：需要 `base_link -> camera_link -> camera_depth_optical_frame`；PC Qt 曾补相机外参，VM 也应对齐 |
| `camera_info` 无 subscribers | 正常；`image_view` 看图不需要 CameraInfo |
| SSH 启动 GUI 失败 | 正常；`image_view` / RViz 需要 VM 桌面 DISPLAY，日常在 VM 桌面 `./run.sh` |
| 遥控按钮无效 | 小车需 `radar2d-start` / `full-start`；Qt 日志看 `/cmd_vel` subscriber |

## 验收状态

- v1（2026-07-03）：雷达/里程计、深度轻量、RGB+Depth 诊断已在真机 + VM 验证。
- v1 + 遥控（2026-07-03）：五键 dead-man `/cmd_vel`；与深度增强分阶段验收。
- 下一阶段：基础 `/cmd_vel` 遥控 + RViz 移动显示联动。

详见 [vmware/docs/VMware Qt深度相机增强方案.md](../docs/VMware%20Qt深度相机增强方案.md)。
