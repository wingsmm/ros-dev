# VMware Qt 雷达/里程计联调指南

本文说明如何在 VMware Qt「**雷达/里程计**」模式下，完成最基础的联调目标：

- RViz 中能看到**障碍物**（`/scan` 红点）
- Qt 遥控能让**小车前后移动**
- RViz 中 `/odom`、TF、`/scan` 随车运动**正常刷新**

适用环境：

| 机器 | IP | 角色 |
|------|-----|------|
| 真机 `xtark-robot` | `192.168.1.168` | ROS Master、底盘、雷达、里程计 |
| VMware `xtark-vmpc` | `192.168.1.154` | 纯客户端：本地 RViz + `/cmd_vel` 遥控 |

相关文档：[VMware开发环境.md](./VMware开发环境.md)、[VMware Qt基础遥控与RViz联动方案.md](./VMware%20Qt基础遥控与RViz联动方案.md)、[vmware/qt/README.md](../qt/README.md)。

---

## 1. 结论（先记住分工）

```text
下位机 168                         上位机 154 (VMware Qt)
────────────────                   ────────────────────────
roscore (Master)        ◄───────   ROS_MASTER_URI → 168:11311
bringup + 底盘 + 雷达                本地 RViz（只显示）
  ├ 发布 /scan                       本地发布 /cmd_vel（遥控）
  ├ 发布 /odom
  └ 订阅 /cmd_vel
```

- **下位机**：跑驱动和数据；用 `pc_stack radar2d-start`（或 `full-start`）。
- **上位机**：只连 Master、起 RViz、发速度；**不**跑 roscore、雷达、相机驱动。
- **不要用 `camera-start` 配雷达/里程计模式**：bringup 虽也有 `/scan`，但会额外拉起相机节点和 TF，RViz 里 TF 易报黄、画面杂乱。

---

## 2. 启动步骤

### 2.1 下位机（真机 168）

SSH 登录真机，或 Windows 侧：

```bat
rem 首次或脚本有更新
xtark\scripts\pc_stack_remote.bat deploy

rem 雷达/里程计专用（推荐）
xtark\scripts\pc_stack_remote.bat radar2d-start

rem 验收
xtark\scripts\pc_stack_remote.bat radar2d-status
xtark\scripts\pc_stack_remote.bat radar2d-check
```

真机手动等价命令：

```bash
~/ros_ws/scripts/pc_stack.sh radar2d-start
~/ros_ws/scripts/pc_stack.sh radar2d-status
```

`full-start` 也可用于本模式（= 雷达 + 相机），但仅看雷达/里程计时优先 `radar2d-start`，更轻、更干净。

### 2.2 上位机（VM 154）

```bash
cd ~/ros-dev/vmware/qt && ./run.sh
```

Windows 一键部署并启动 GUI：

```bat
vmware\scripts\vm_qt_remote.bat run
```

客户端内：

1. 确认 **Master: 可达**
2. 选择 **「雷达/里程计」**
3. 点击 **「启动 RViz (本机 VM)」**
4. 可选：**「检查关键 topic」** 验证 `/scan`、`/odom`

---

## 3. 上下位机节点与 Topic 对应

### 3.1 下位机必须有的节点

| 节点 | 作用 |
|------|------|
| `roscore` | ROS Master |
| `/xtark_driver` | 底盘驱动；**订阅 `/cmd_vel`** |
| `/rplidarNode`、`/laser_filter` | 发布 `/scan` |
| `/odom_ekf_node` 或 `/robot_pose_ekf` | 发布 `/odom`；广播 `odom → base_footprint` |
| `/robot_state_publisher` | 车体关节 TF |
| `/base_foot_print_to_laser` | 静态 TF：`base_footprint → laser` |

### 3.2 上位机（VM）对应关系

| VM 侧 | 连到下位机 |
|-------|------------|
| RViz `LaserScan` → `/scan` | `/rplidarNode` 发布 |
| RViz `Odometry` → `/odom` | 里程计节点发布 |
| Qt 五键遥控 → `/cmd_vel` | `/xtark_driver` 订阅 |
| `Fixed Frame = odom` | 与 `/odom.header.frame_id` 一致 |

VM **不启动**雷达、里程计、底盘节点；只做订阅、显示和发速度。

### 3.3 关键 Topic 一览

| Topic | 类型 | frame / 说明 |
|-------|------|----------------|
| `/scan` | `sensor_msgs/LaserScan` | `frame_id: laser` |
| `/odom` | `nav_msgs/Odometry` | `frame_id: odom`，`child_frame_id: base_footprint` |
| `/cmd_vel` | `geometry_msgs/Twist` | VM Qt 发布，下位机 `xtark_driver` 订阅 |

---

## 4. 正方向、障碍物与 TF 链

### 4.1 TF 链（RViz Fixed Frame = `odom`）

```text
odom  ──►  base_footprint  ──►  laser
(世界)      (车体中心)          (/scan 的 frame_id)
```

| 显示内容 | 数据来源 | 在 RViz 中的含义 |
|----------|----------|------------------|
| **障碍物红点** | `/scan` | 雷达测距点，变换到 `odom` 后显示 |
| **车头方向** | `/odom` | Odometry 橙色箭头 = 车体在 `odom` 下的位姿 |
| **前后移动** | `/cmd_vel.linear.x` | Qt「前进」发 `+x`，车体沿箭头方向平移 |

出厂配置中 `base_footprint → laser` 带约 180° 安装偏置，属正常；不影响障碍物显示与遥控验收。

### 4.2 RViz 显示项（`vmware/qt/config/rviz_mapping.rviz`）

| Display | Topic | 建议 |
|---------|-------|------|
| Grid | — | **开** |
| TF | — | **开** |
| Scan | `/scan` | **开**（红色障碍点） |
| Odometry | `/odom` | **开**（橙色方向箭头） |
| Map | `/map` | **关**（未建图时不要开） |

**Global Options → Fixed Frame** 必须为 **`odom`**。

---

## 5. 遥控与移动验收

Qt「基础遥控」面板（五键 dead-man）：

```text
      前进
左转  停止  右转
      后退
```

| 按钮 | `/cmd_vel` |
|------|------------|
| 前进 | `linear.x > 0` |
| 后退 | `linear.x < 0` |
| 左转 | `angular.z > 0`（原地转） |
| 右转 | `angular.z < 0`（原地转） |
| 停止 | 全零 |

默认约 10Hz 重发；**按住才动，松开即停**。关闭窗口或失焦也会发零速度（非硬件急停）。

### 验收通过标准

在「雷达/里程计」+ RViz 已启动的前提下：

1. **障碍物**：静止时 RViz 中 `/scan` 红点稳定显示周围障碍。
2. **前进/后退**：按住「前进」→ Odometry 箭头沿自身朝向平移，`/scan` 红点随车一起动；「后退」反向。
3. **转向**：按住「左转/右转」→ Odometry 箭头 yaw 变化，`/scan` 扫掠方向随之变化。
4. **停止**：松开后车停，`/cmd_vel` 归零。

下位机可辅助确认：

```bash
rostopic info /cmd_vel    # 应有 Subscriber: /xtark_driver
rostopic echo /cmd_vel    # 按住按钮时应有非零 Twist
```

---

## 6. 常见问题

| 现象 | 原因 / 处理 |
|------|-------------|
| RViz 无 `/scan` 红点 | 下位机未 `radar2d-start`；或 Master 不可达 |
| TF 报黄、画面杂乱 | 用了 `camera-start` 而非 `radar2d-start`；或误开了 Map display |
| 遥控按钮无效 | 下位机无 `/cmd_vel` subscriber；改 `radar2d-start` / `full-start` |
| Odometry 动但 scan 不跟 | Fixed Frame 不是 `odom`；或 TF `odom→base_footprint→laser` 断链 |
| Map 全黑 / Global Error | 正常：本模式不建图，**关闭 Map display** |
| Master 不可达 | 确认真机 168 上电、同网段；VM `ROS_MASTER_URI` 指向 168 |

### 快速诊断命令（真机）

```bash
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
export ROS_MASTER_URI=http://192.168.1.168:11311

rosnode list | egrep 'xtark_driver|rplidar|odom|ekf'
rostopic hz /scan
rostopic hz /odom
rostopic info /cmd_vel
rosrun tf tf_echo odom base_footprint
rosrun tf tf_echo base_footprint laser
```

---

## 7. 与其他 VMware Qt 模式的区别

| Qt 模式 | RViz 配置 | 下位机命令 | 用途 |
|---------|-----------|------------|------|
| **雷达/里程计** | `rviz_mapping.rviz` | `radar2d-start` / `full-start` | 看障碍、里程计、基础遥控 |
| 深度轻量 | `rviz_depth_light.rviz` | `camera-start` | 深度卡顿验收 |
| RGB+Depth 诊断 | `rviz_rgb_depth_diag.rviz` | `camera-start` | 相机 TF 排错 |
| 深度增强 | `rviz_depth_enhanced.rviz` | `camera-deep-start` | 深度 preview + VM 点云 |

本指南只覆盖 **雷达/里程计** 一档。

---

## 8. 维护说明

- 探测与联调基准：**2026-07-08**；IP 以局域网 DHCP 为准。
- RViz 配置源：`vmware/qt/config/rviz_mapping.rviz`。
- 下位机栈入口：`xtark/scripts/pc_stack.sh`（Windows：`xtark/scripts/pc_stack_remote.bat`）。
- 密码、密钥勿写入 Git；自动化 SSH 见 [xtark/docs/远端登录.md](../../xtark/docs/远端登录.md)。
