# Unitree L1 接入 xtark 小车的 WSL2 / PC-client 完整方案

## 1. 背景

当前目标不是把 Unitree L1、SLAM、导航和控制全部塞进 xtark 小车本机，而是把 xtark 当作一个完整、稳定的移动底盘使用：

- xtark 负责底盘运动、里程计、状态回传和速度命令执行。
- Unitree L1 安装在 xtark 车体上，负责环境扫描和 IMU 采集。
- WSL2 / PC-client 负责数据汇聚、建图、导航决策、调试界面和控制闭环。

这条路线的核心思想是：小车本体保持轻量，重计算搬到 WSL2 / PC 侧。

## 2. 目标

完成一个可验证的 L1 + xtark 分布式建图与导航 demo：

```text
Unitree L1
  -> 车载采集节点
  -> /unilidar/cloud + /unilidar/imu
  -> /scan

xtark 底盘
  -> JSON 8765
  -> odom_base / base_status
  <- cmd_vel

WSL2 / pc-client
  -> 汇聚 /scan + /odom_base + TF
  -> RViz2 / slam_toolbox / Nav2
  -> 通过 pc-client 控制 xtark
```

第一阶段验收以“低速遥控建图”为主，不直接追求完整自主导航。

## 3. 当前状态

仓库中已有以下基础能力：

- `pc/qt_client` 已作为 WSL2 统一入口，负责连接 xtark JSON、发布 ROS2 里程计/状态、启动 RViz2 / slam_toolbox。
- xtark 侧已有 JSON 桥接思路，默认地址为 `192.168.1.169:8765`。
- WSL2 侧已有 `/odom_base`、`/base_status`、`odom -> base_link` TF 发布逻辑。
- `plj/src/slam_bringup/launch/l1_driver.launch.py` 已有 Unitree L1 ROS2 驱动启动入口。
- `plj/src/slam_bringup/launch/obstacle_scan.launch.py` 已有点云转 2D `/scan` 的入口。
- `plj/src/slam_bringup/config/robot_tf.yaml` 已有临时 `base_link -> unilidar_lidar` 外参配置。

当前不应假设以下事项已经完成：

- L1 已经实际安装到 xtark 车体。
- L1 外参已经实测。
- L1 数据已经稳定跨机进入 WSL2。
- Nav2 已经能基于 L1 `/scan` 稳定控制 xtark。

## 4. 总体架构

推荐架构如下：

```text
┌──────────────────────── xtark 小车本体 ────────────────────────┐
│                                                                  │
│  xtark 底盘                                                       │
│    ├─ 执行速度命令                                                │
│    ├─ 输出里程计 / 状态                                            │
│    └─ xtark_json_bridge :8765                                     │
│                                                                  │
│  Unitree L1                                                       │
│    └─ USB 接入车载采集节点                                         │
│                                                                  │
│  车载采集节点                                                     │
│    ├─ unitree_lidar_ros2                                          │
│    ├─ /unilidar/cloud                                             │
│    ├─ /unilidar/imu                                               │
│    └─ 可选：pointcloud_to_laserscan -> /scan                      │
│                                                                  │
└───────────────────────────── 网络 ───────────────────────────────┘
                         │
                         ▼
┌────────────────────── WSL2 / PC-client ─────────────────────────┐
│                                                                  │
│  pc/qt_client                                                     │
│    ├─ 连接 xtark JSON 8765                                        │
│    ├─ 发布 /odom_base、/odom、/base_status                         │
│    ├─ 发布 odom -> base_link TF                                   │
│    ├─ 接收 /cmd_vel 并转发给 xtark                                │
│    └─ 启停 RViz2 / slam_toolbox / Nav2                            │
│                                                                  │
│  ROS2 建图导航层                                                   │
│    ├─ 接收 /scan                                                  │
│    ├─ 接收 /odom_base 或 /odom                                    │
│    ├─ 使用 base_link -> unilidar_lidar / laser TF                 │
│    ├─ slam_toolbox 建图                                           │
│    └─ Nav2 后续导航验证                                           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 5. 职责边界

| 模块 | 负责 | 不负责 |
|---|---|---|
| xtark 底盘 | 执行运动、回传里程计、回传状态、接收速度命令 | 不跑重 SLAM，不做主导航决策 |
| Unitree L1 | 环境扫描、IMU 数据采集 | 不直接参与底盘控制 |
| 车载采集节点 | 接 L1 USB，发布 ROS2 点云/IMU/scan | 不承担完整导航任务 |
| WSL2 | 数据汇聚、TF、建图、导航、调试 | 不直接接底盘串口 |
| pc-client | 人机入口、连接 xtark、启停建图/导航、发速度命令 | 不承担传感器 USB 驱动本体 |

## 6. 2D 雷达处理策略

当前 xtark 原有 2D 雷达可以拆下，但建议按阶段处理：

### 6.1 第一阶段：逻辑停用

不先物理拆除，只让 WSL2 建图链路不再依赖原车 2D 雷达 `/scan`，改为使用 L1 转换出的 `/scan`。

### 6.2 第二阶段：拔线验证

拔掉原 2D 雷达 USB，确认 xtark 底盘链路仍正常：

- `/odom` 正常。
- JSON 8765 正常。
- `cmd_vel` 能驱动车体。
- `base_status` 正常。

如果 xtark bringup 日志中出现 `/dev/lidar` 找不到，但不影响底盘和 JSON，则可以接受。

### 6.3 第三阶段：物理拆除

只有当 L1 `/scan`、xtark `/odom_base`、TF、slam_toolbox 建图都能跑通后，再正式拆除原 2D 雷达和支架。

## 7. L1 安装与外参

L1 可以安装在原 2D 雷达附近，也可以安装在更高、更利于前向观测的位置。

必须实测以下外参：

```text
base_link -> unilidar_lidar
  x
  y
  z
  roll
  pitch
  yaw
```

仓库中已有临时配置：

```text
plj/src/slam_bringup/config/robot_tf.yaml
```

临时值只适合启动 demo，不适合最终验收。尤其是 L1 若存在俯仰角，`pitch` 必须实测，否则点云转 `/scan` 会歪，建图容易漂。

## 8. 数据接口设计

### 8.1 L1 原始输出

推荐话题：

```text
/unilidar/cloud   sensor_msgs/PointCloud2
/unilidar/imu     sensor_msgs/Imu
```

启动入口参考：

```text
plj/src/slam_bringup/launch/l1_driver.launch.py
```

### 8.2 L1 转 2D scan

推荐将 L1 点云转换为 2D `/scan`，供 slam_toolbox / Nav2 使用。

启动入口参考：

```text
plj/src/slam_bringup/launch/obstacle_scan.launch.py
```

关键参数：

```text
cloud_topic: /unilidar/cloud
scan_topic: /scan
target_frame: base_link
min_height: -0.05
max_height: 0.35
range_min: 0.25
range_max: 6.0
angle_min: -1.5708
angle_max: 1.5708
```

这些参数第一版只作为保守起点，后续要根据 L1 安装高度、俯仰角和现场障碍物高度调整。

### 8.3 xtark 底盘输出

xtark 通过 JSON 桥接提供：

```text
odom_base
base_status
```

WSL2 / pc-client 转换为：

```text
/odom_base
/odom
/base_status
odom -> base_link
```

### 8.4 控制输入

WSL2 / Nav2 / pc-client 发布：

```text
/cmd_vel
```

pc-client 将 `/cmd_vel` 转发到 xtark JSON 8765，由 xtark 底盘执行。

## 9. 推荐实现路径

### P0：保留 xtark 当前底盘链路

目标：确认 xtark 仍然只是稳定底盘。

验收：

```bash
ros2 topic hz /odom_base
ros2 topic echo /base_status --once
ros2 run tf2_ros tf2_echo odom base_link
```

pc-client 低速遥控能让小车前进、后退、旋转。

### P1：L1 单独跑通

目标：L1 驱动稳定输出点云和 IMU。

验收：

```bash
ros2 topic hz /unilidar/cloud
ros2 topic echo /unilidar/imu --once
```

RViz2 中能看到点云，点云方向与实际车体前方大致一致。

### P2：L1 点云转 `/scan`

目标：生成 2D 建图可用 `/scan`。

验收：

```bash
ros2 topic hz /scan
ros2 topic echo /scan --once
ros2 topic echo /scan --once | grep frame_id
```

要求：

```text
/scan 有稳定频率
/scan.header.frame_id 与 TF 链一致
```

### P3：WSL2 汇聚 `/scan + odom + TF`

目标：WSL2 同时收到 L1 scan 和 xtark odom。

验收：

```bash
ros2 topic hz /scan
ros2 topic hz /odom_base
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_ros tf2_echo base_link unilidar_lidar
```

如果 `/scan` 使用 `laser` 作为 frame，则确认：

```bash
ros2 run tf2_ros tf2_echo base_link laser
```

### P4：低速建图 demo

目标：用 slam_toolbox 生成初版地图。

操作：

```text
1. 启动 pc/qt_client。
2. 连接 xtark JSON 8765。
3. 确认 /scan、/odom_base、TF 正常。
4. 启动 RViz2 / slam_toolbox。
5. 小范围低速遥控：
   - 原地小角度旋转 10 到 20 度
   - 前进 0.5 到 1 米
   - 停住观察 /map
   - 再缓慢转回或后退
```

验收：

```text
/map 有内容
地图方向与车体运动方向一致
没有持续大量 Message Filter dropping
车体停止后地图不持续漂移
```

### P5：导航 demo

目标：基于已保存地图启动 Nav2，发目标点后由 WSL2 规划并通过 pc-client 控制 xtark。

前提：

- P4 建图稳定。
- 已保存地图。
- `/cmd_vel` 到 xtark 的转发链路稳定。
- 急停和手动接管可用。

验收：

```text
RViz2 下发 2D Goal
Nav2 发布 /cmd_vel
pc-client 转发到 xtark
xtark 低速移动
能到达近距离目标或安全停止
```

## 10. WSL2 与采集节点部署选择

### 10.1 推荐方案：车载节点跑 L1 驱动

```text
L1 USB -> 车载 Linux -> unitree_lidar_ros2 -> ROS2 topic -> WSL2
```

优点：

- USB 时序更稳定。
- 驱动离硬件近。
- WSL2 只处理网络 ROS2 topic。
- 后续可替换采集节点，不影响 xtark 底盘。

缺点：

- 需要车上有一台能跑 ROS2 的采集设备。

### 10.2 不推荐第一版：远程 USB / 串口转发

```text
L1 USB -> xtark/车载设备 -> TCP 串口转发 -> WSL2 驱动
```

不推荐原因：

- L1 数据量和时序敏感。
- 远程串口容易丢包或断连。
- 驱动问题和网络问题会混在一起，排查成本高。

### 10.3 可选方案：L1 转 `/scan` 在车载节点完成

如果 WSL2 只需要 2D 建图，也可以在车载节点完成点云转 scan：

```text
车载节点:
  /unilidar/cloud -> pointcloud_to_laserscan -> /scan

WSL2:
  只接 /scan
```

这会降低 WSL2 侧数据量，但会减少后续在 WSL2 调点云参数的灵活性。

## 11. 风险与应对

| 风险 | 表现 | 应对 |
|---|---|---|
| L1 外参不准 | 地图倾斜、墙体弯曲、运动方向不一致 | 实测 `base_link -> unilidar_lidar` |
| 点云转 scan 参数不合适 | 障碍物缺失或虚假障碍很多 | 调 `min_height/max_height/range/angle` |
| WSL2 DDS 不稳定 | topic 能看到但 echo/hz 没数据 | 固定 ROS_DOMAIN_ID，检查 WSL2 mirrored 网络和防火墙 |
| 时间戳/TF 不匹配 | slam_toolbox 大量 message filter dropping | 检查 `/scan` frame、TF、transform timeout，必要时 relay 重打时间戳 |
| xtark 原 2D 雷达拆除影响 bringup | 日志报 `/dev/lidar` 缺失 | 确认 `/odom`、JSON、cmd_vel 不受影响；必要时修改 bringup |
| L1 算力占用高 | 采集节点卡顿、scan 频率下降 | 降低点云处理频率，优先只发 `/scan` |
| Nav2 直接控车风险 | 车速过快或规划不稳 | 第一版限速，保留急停，先做近距离目标 |

## 12. 验收标准

### 12.1 传感器验收

```text
/unilidar/cloud 稳定
/unilidar/imu 可读
/scan 稳定
RViz2 可视化方向正确
```

### 12.2 底盘验收

```text
xtark JSON 8765 可连接
/odom_base 稳定
/base_status 可读
/cmd_vel 可驱动车体
```

### 12.3 TF 验收

```text
odom -> base_link 可查
base_link -> unilidar_lidar 可查
如果使用 laser frame，则 base_link -> laser 可查
```

### 12.4 建图验收

```text
slam_toolbox 可启动
/map 可生成
低速移动时地图连续
停止后地图不明显漂移
```

### 12.5 导航验收

```text
Nav2 可启动
RViz2 可下发目标点
/cmd_vel 经 pc-client 转发到 xtark
小车低速响应
可手动停止或急停
```

## 13. 不要做什么

第一版不要做：

- 不要把 L1、3D SLAM、Nav2 全部塞进 xtark 本机。
- 不要一开始就拆掉 2D 雷达支架，先拔线验证。
- 不要未量外参就做自主导航。
- 不要直接在复杂场景高速跑 Nav2。
- 不要把 WSL2、Windows 原生 Qt、Docker ROS2 混成三套入口。
- 不要把 UI 显示当作真实闭环验证，必须看 topic、TF、日志和实际运动。

## 14. 最小 demo 任务书

### 背景

xtark 作为完整移动底盘，L1 安装在车体上采集环境。重计算搬到 WSL2 / PC-client。

### 目标

完成 L1 `/scan` + xtark `/odom_base` + WSL2 slam_toolbox 的低速建图 demo。

### 修改范围

优先使用现有文件：

```text
pc/qt_client/
pc/docs/WSL2统一栈运行与调试.md
plj/src/slam_bringup/launch/l1_driver.launch.py
plj/src/slam_bringup/launch/obstacle_scan.launch.py
plj/src/slam_bringup/config/robot_tf.yaml
```

必要时新增：

```text
pc/qt_client/config/l1_xtark_scan.yaml
pc/qt_client/config/l1_xtark_mapping.rviz
```

### 实现步骤

1. 保持 xtark JSON 8765 和底盘 bringup 正常。
2. 在车载采集节点启动 L1 ROS2 驱动。
3. 发布 `/unilidar/cloud` 和 `/unilidar/imu`。
4. 启动点云转 `/scan`。
5. 在 WSL2 确认 `/scan` 可见。
6. 启动 `pc/qt_client`，连接 xtark。
7. 确认 `/odom_base`、`/base_status`、TF 正常。
8. 启动 RViz2 / slam_toolbox。
9. 低速遥控小范围建图。
10. 保存地图并记录验收日志。

### 注意事项

- 低速测试，优先室内空旷区域。
- 保留人工急停。
- L1 外参先用临时值，建图前必须确认方向大致正确。
- 若 slam_toolbox 丢帧，先查 TF 和时间戳，不要盲目调 SLAM 参数。

### 验收标准

```text
ros2 topic hz /scan           稳定
ros2 topic hz /odom_base      稳定
tf2_echo odom base_link       正常
tf2_echo base_link unilidar_lidar 正常
slam_toolbox 输出 /map
pc-client 可低速控制 xtark
```

## 15. 推荐结论

这个方案可行，而且是当前最稳妥的路线：

```text
xtark 做底盘
L1 做采集
车载节点做传感器发布
WSL2 / pc-client 做建图导航与控制闭环
```

第一版不要追求“完整自主扫地机器人”，先证明三件事：

```text
L1 能稳定出 /scan
xtark 能稳定出 odom 并接收 cmd_vel
WSL2 能用 /scan + odom + TF 生成 /map
```

这三件事跑通后，再进入 Nav2、覆盖清扫路径规划和任务恢复。
