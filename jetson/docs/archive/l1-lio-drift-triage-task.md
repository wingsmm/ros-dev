# 历史：Unitree L1 / Point-LIO 漂移混乱记录与排查任务书

> **历史状态（2026-07-08）**：本文描述的是当时已经撤回的旧整栈，只用于追溯排障过程。当前日常入口和验收边界以 `jetson/docs/宇树L1对接方案.md` 为准；不要按本文命令部署或启动当前系统。文中的 WSL 只代表当时的历史观测端，现已废弃。

本文记录 Jetson 上 Unitree L1 雷达、Point-LIO、`lio_odom_adapter`、WSL RViz/cockpit 之间的边界和排查方法。

目标不是继续加入口或调 UI，而是让实施 agent 按固定顺序把问题查清楚，并输出完整报告。

## 背景

当前小车底盘不可作为可靠里程计来源：

- 不使用轮速 odom。
- 不用 `/cmd_vel` 积分伪造 odom。
- 移动观测链路只认：`/unilidar/cloud` + `/unilidar/imu` -> Point-LIO -> `/aft_mapped_to_init` -> `lio_odom_adapter` -> `/odom`、`/odom_path`、TF。

L1 雷达当前是卧放安装。外参、坐标修正、RViz 配置都必须服务于这个事实，不能按“雷达竖直安装”去解释姿态。

## 当前目标

对齐 VMware Qt 的日常使用体验：

```text
一个日常入口
  -> 启动完整观测栈
  -> WSL/cockpit 打开 RViz
  -> 能看到 TF / odom / path / 点云
  -> 推车移动时轨迹连续、不过度飘
```

管理入口应收敛到：

```bash
bash jetson/scripts/jetson.sh ros2 deploy   # 改代码后
bash jetson/scripts/jetson.sh ros2 start    # bridge + L1 + Point-LIO + adapter
bash jetson/scripts/jetson.sh ros2 stop
bash jetson/scripts/jetson.sh ros2 status
bash jetson/scripts/jetson.sh ros2 logs
```

`lio-start` / `lio-stop` 只能作为调试入口，不应该成为日常步骤。

## 已知混乱

1. 只看 RViz 现象容易误判。
   - TF 图标红、Path 飘、Axes 方向怪，不一定是 RViz 配置错。
   - 如果原始雷达/IMU 输入已经掉频，Point-LIO 会直接发散。

2. 曾出现原始输入异常。
   - `/unilidar/cloud` 从健康的约 9 Hz 掉到约 2 Hz。
   - `/unilidar/imu` 频率也明显下降。
   - 这种状态下 Point-LIO 的 `camera_init -> aft_mapped` 可能漂到几千米量级。

3. 曾出现栈状态不一致。
   - 雷达输入重启了，但 LIO/adapter 没有干净重启。
   - 后续已要求 `ros2 start` 统一刷新完整观测栈，避免手工三步。

4. 曾出现错误方向调整冲动。
   - L1 是卧放，不是顶部竖装。
   - 方向要保留正确物理含义，不能为了让截图好看随便改 TF。

## 不要做什么

- 不要再用 `/cmd_vel` 生成 odom。
- 不要把底盘轮速、车体控制回显当 odom。
- 不要先调 RViz 配置来掩盖 LIO 漂移。
- 不要只凭 `ros2 topic list` 判断雷达健康。
- 不要把本地 `jetson/mirror/ros2_ws` 编译结果当 82 实机验证。
- 不要把 `lio-start` / `lio-stop` 写成日常使用步骤。

## 排查顺序

必须按下面顺序查。前一层不健康，不进入下一层。

### 1. 管理通道

在 WSL 中执行，不用 PowerShell 直接做远端 ROS 操作：

```bash
cd /mnt/d/Downloads/work/ros-dev
bash jetson/scripts/jetson.sh ros2 status
```

报告里记录：

- bridge 是否 running。
- unilidar 是否 running。
- unilidar port，预期为 `/dev/ttyCH341USB0`。
- point_lio 是否 running。
- odom adapter 是否 running。
- 是否能看到 `/odom`、`/odom_path`、`/aft_mapped_to_init`、`/cloud_registered`。

### 2. 原始 L1 输入健康度

在 WSL 中执行：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
timeout 12 ros2 topic hz /unilidar/cloud
timeout 12 ros2 topic hz /unilidar/imu
```

判定：

- `/unilidar/cloud` 应接近 9 Hz。
- `/unilidar/imu` 应稳定在高频，不应明显掉到几十 Hz 级别并剧烈抖动。
- 如果 `/unilidar/cloud` 只有约 2 Hz，先处理雷达输入，不要继续调 LIO。

### 3. Point-LIO 输出健康度

只有原始输入健康后再查：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
timeout 8 ros2 topic hz /aft_mapped_to_init
timeout 8 ros2 topic hz /cloud_registered
timeout 8 ros2 topic hz /odom
timeout 8 ros2 topic hz /odom_path
```

再查 TF：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
timeout 5 ros2 run tf2_ros tf2_echo odom base_link
timeout 5 ros2 run tf2_ros tf2_echo odom unilidar_lidar
timeout 5 ros2 run tf2_ros tf2_echo camera_init aft_mapped
```

判定：

- 静止时 `/odom_path` 不应快速画大圈或远距离跳线。
- `odom -> base_link` 应保持地面机器人视角，roll/pitch 接近 0，z 接近 0。
- `camera_init -> aft_mapped` 如果出现几百米、几千米级平移，说明 Point-LIO 已发散。

### 4. WSL / RViz 现象

只有前面三层健康后才看 RViz。

使用 cockpit 的单一 RViz 入口，或直接加载配置：

```bash
cd /mnt/d/Downloads/work/ros-dev/jetson/cockpit
export ROS_DOMAIN_ID=0
bash run.sh
```

RViz 里应至少看到：

- TF
- Odometry `/odom`
- Path `/odom_path`
- RawUnilidarCloud `/unilidar/cloud`
- CloudRegistered `/cloud_registered`

如果 RViz 日志出现大量 `Message Filter dropping message`，先结合 topic 频率判断是否是输入/LIO/TF 时序问题，不要直接改 Display。

## 恢复动作

当出现飘移、点云掉频、LIO 状态陈旧时，统一用完整栈重启：

```bash
cd /mnt/d/Downloads/work/ros-dev
bash jetson/scripts/jetson.sh ros2 stop
bash jetson/scripts/jetson.sh ros2 start
bash jetson/scripts/jetson.sh ros2 status
```

不要只重启 RViz。
不要只重启 adapter。
不要在雷达掉频时单独 `lio-start`。

## 建议加固项

实施 agent 可以改代码，但必须保持边界清晰。

### A. `ros2 status` 显示频率

增强 `ros2_stack.sh status` 或相关脚本，让状态输出不只列 topic，还能显示：

- `/unilidar/cloud` Hz
- `/unilidar/imu` Hz
- `/aft_mapped_to_init` Hz
- `/odom` Hz
- `/odom_path` 是否有数据

### B. `lio_stack.sh start` 增加输入健康门禁

启动 Point-LIO 前不要只检查 topic 是否存在，建议增加频率门槛：

- `/unilidar/cloud` 小于 6 Hz 时拒绝启动 LIO。
- `/unilidar/imu` 明显低频或无数据时拒绝启动 LIO。
- 报错信息明确提示先重启 L1 输入。

### C. LIO 发散保护

adapter 或 status 中可增加轻量异常检测：

- `camera_init -> aft_mapped` 平移超过合理范围时报警。
- 静止时 `/odom_path` 短时间累计距离异常时报警。

这只是保护提示，不要把异常数据硬裁剪成“正常 odom”。

## 实施报告要求

完成后给出一份完整报告，必须包含：

1. 执行时间。
2. 是否已经 `deploy` 到 82。
3. `ros2 status` 原始输出。
4. `/unilidar/cloud` Hz 输出。
5. `/unilidar/imu` Hz 输出。
6. `/aft_mapped_to_init`、`/odom`、`/odom_path` Hz 输出。
7. `tf2_echo odom base_link` 关键值。
8. `tf2_echo camera_init aft_mapped` 关键值。
9. RViz 现象描述。
10. 静止 30 秒是否漂移。
11. 手推小车 1 到 3 米后，轨迹是否连续。
12. 如果失败，明确失败层级：
    - 管理通道失败
    - 原始雷达输入失败
    - Point-LIO 发散
    - adapter / TF 问题
    - RViz 显示问题

报告必须区分：

- 已写代码
- 已部署到 82
- 已在 82 实机运行
- WSL DDS 已收到
- RViz 目视已确认

## 验收标准

阶段验收只看事实：

- `ros2 start` 一步拉起完整观测栈。
- `/unilidar/cloud` 接近 9 Hz。
- `/unilidar/imu` 高频稳定。
- `/odom` 和 `/odom_path` 存在且频率合理。
- 静止时 path 不大幅飘。
- 手推小车时 path 连续，不出现几百米/几千米跳变。
- RViz 使用一个入口即可看 TF / odom / path / 点云。

未达到这些标准之前，不宣布“对齐 VMware Qt”。
