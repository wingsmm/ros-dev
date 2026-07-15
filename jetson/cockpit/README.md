# cockpit - PC/VMware Jetson Qt 控制台

`jetson/cockpit/` 是运行在 VMware 观测端的 Qt 上位机，不部署到 Jetson。当前 L1/RViz 观测闭环只认 VMware 侧验证。

当前阶段：

```text
PC / VMware cockpit Qt
  -> ROS2 /cmd_vel（干跑遥控）
  -> 雷达观测面板：
       原始点云 / 车体对齐：启动雷达 / 打开雷达视图 / 停止雷达
       雷达/里程计：启动定位 / 打开定位视图 / 停止定位

Jetson ~/qt/ros2_ws
  -> unitree_lidar_ros2 -> /unilidar/cloud + /unilidar/imu
  -> l1_static_tf       -> base_link -> unilidar_lidar -> unilidar_imu
  -> l1_cloud_align     -> /unilidar/cloud_aligned (frame=base_link)
  -> Point-LIO          -> /aft_mapped_to_init + /cloud_registered
  -> lio_odom_adapter   -> /odom + /odom_path + TF odom->base_link
```

本阶段不调用 `car_web` 电机、不从 `/cmd_vel` 伪造 odom；雷达可视化走观测端本机 RViz2。

## 目录

```text
cockpit/
  app.py                         Qt 入口
  main_window.py                 主窗口
  run.sh                         source ROS2 Humble 后启动 Qt
  .env                           本地运行配置
  requirements.txt               PC/VM 本地 Qt 依赖
  logs/                          本地日志目录
  core/
    config.py                    读取 .env
    logging_config.py            控制台 + 文件日志
    ros2_probe.py                ROS2 DDS 图 / topic 连接性检查
    ros2_control.py              Qt worker：发布 /cmd_vel，订阅动作回显
  ui/
    status_panel.py              连接状态面板
    lidar_panel.py               雷达观测：RViz2 一键启动 + Hz/port
    teleop_panel.py              五键 dead-man 遥控面板
    topic_panel.py               Topic 诊断面板
  config/
    unilidar.rviz                阶段一原始点云（Fixed Frame=unilidar_lidar）
    unilidar_base.rviz           阶段二车体对齐（Fixed Frame=base_link）
    unilidar_mapping.rviz        阶段四 LIO/odom（勿用于阶段二）
  scripts/
    start_unilidar_rviz.sh       无 Qt 时一键 RViz2
    stop_unilidar_rviz.sh
    verify_cmd_vel_bridge.sh     旧本机冒烟脚本（不作为支持入口）
    cmd_vel_sender.py            CLI 调试：发一次 /cmd_vel
    control_action_echo.py       CLI 调试：监听 /vehicle/control_action
```

## 运行 Qt Cockpit

```bash
cd jetson/cockpit
bash run.sh
```

如果直接执行权限已保留，也可以：

```bash
./run.sh
```

## 配置

本地配置写在 `cockpit/.env`（从 `.env.example` 复制，不入库密钥）。

**为何需要 `.env`：** `vmware.sh deploy` 只同步 `jetson/cockpit/` 到 VM，不含仓库根的 `jetson/scripts/jetson.sh`。外参「读取 / 应用」走 **ssh 直连 Jetson**，主机地址、用户、端口、密码必须在 **VM 本地** `cockpit/.env` 配置。外参 YAML 仍在 Jetson 端，不放 cockpit `.env`。

开发机整仓调试仍可用 `jetson/scripts/jetson.sh ros2 tf-*`；cockpit 内不依赖该脚本。

| 变量 | 默认 | 说明 |
|---|---|---|
| `ROS_DOMAIN_ID` | `0` | ROS2 DDS domain |
| `CMD_VEL_TOPIC` | `/cmd_vel` | cockpit 发布的速度 topic |
| `CONTROL_ACTION_TOPIC` | `/vehicle/control_action` | Jetson dry-run bridge 回显 topic |
| `TELEOP_LINEAR_SPEED` | `1.0` | 前进 / 后退线速度值 |
| `TELEOP_ANGULAR_SPEED` | `1.0` | 左转 / 右转角速度值 |
| `TELEOP_REPEAT_HZ` | `10` | 按住运动时重发频率 |
| `TELEOP_ENABLE_KEYBOARD` | `1` | 是否启用键盘遥控 |
| `JETSON_COCKPIT_LOG_DIR` | `logs` | 本地日志目录 |
| `JETSON_COCKPIT_LOG_LEVEL` | `INFO` | 日志等级 |
| `LIDAR_CLOUD_TOPIC` | `/unilidar/cloud` | 雷达原始点云 topic |
| `LIDAR_CLOUD_ALIGNED_TOPIC` | `/unilidar/cloud_aligned` | l1_cloud_align 输出 topic（车体对齐 RViz） |
| `LIDAR_IMU_TOPIC` | `/unilidar/imu` | 雷达 IMU topic |
| `LIDAR_RVIZ_CONFIG` | `config/unilidar.rviz` | 阶段一原始点云 RViz |
| `LIDAR_BASE_RVIZ_CONFIG` | `config/unilidar_base.rviz` | 阶段二车体对齐 RViz |
| `LIDAR_MAPPING_RVIZ_CONFIG` | `config/unilidar_mapping.rviz` | 阶段四 LIO/odom RViz |
| `JETSON_SSH_HOST` | *(空)* | Jetson IP；VM 上必填 |
| `JETSON_SSH_USER` | `nvidia` | SSH 用户 |
| `JETSON_SSH_PORT` | `22` | SSH 端口 |
| `JETSON_SSH_PASSWORD` | *(空)* | SSH 密码（仅 VM 本地 `.env`，不入库） |
| `JETSON_SSH_KEY` | *(空)* | 可选私钥；有密码时不必配 |
| `JETSON_REMOTE_ROS2_WS` | `~/qt/ros2_ws` | 远端 ws，用于 `scripts/l1_static_tf.sh` |

VM 首次配置（密码方式）：

```bash
sudo apt install -y sshpass
# 编辑 ~/ros-dev/jetson/cockpit/.env（deploy 不覆盖已有 .env）：
# JETSON_SSH_HOST=172.0.0.82
# JETSON_SSH_USER=nvidia
# JETSON_SSH_PASSWORD=你的密码
```

面板外参调试区分三类状态：

- **写入**：读取 / 应用对齐参数的 SSH + YAML 结果
- **对齐节点**：`l1_cloud_align` 在 Jetson 上是否运行，能否输出 `/unilidar/cloud_aligned`
- **点云**：原始模式看 `/unilidar/cloud`，车体对齐模式看 `/unilidar/cloud_aligned`；频率只是辅助显示，publisher 存在才是打开 RViz 的主判断

日志文件写入：

```text
logs/jetson-cockpit-YYYY-MM-DD.log
```

## 雷达观测（L1 原始点云）

L1 对接的主入口文档是 [../docs/宇树L1对接方案.md](../docs/宇树L1对接方案.md)。本节只说明 cockpit / 观测端怎么打开 RViz 和怎么判断 DDS 是否通。当前 L1/RViz 验证只认 VMware/VM 观测端。

阶段一只看官方原始点云：

```text
Jetson unitree_lidar_ros2 -> /unilidar/cloud + /unilidar/imu
VMware rviz2              -> Fixed Frame=unilidar_lidar
```

Qt cockpit 不是必须链路；它只是本地启动 RViz 和显示诊断状态的壳。要排查时，可以直接在 VM 里跑 `rviz2 -d config/unilidar.rviz`。

**方式 A：cockpit 内一键**

```bash
cd jetson/cockpit
bash run.sh
```

雷达观测面板（阶段二闭环；SSH 远程启停 Jetson L1+TF，不暴露 TF 进程按钮）：

| 模式 | RViz 配置 | Fixed Frame | 主显示 | 按钮 | 阶段 |
|------|-----------|-------------|-----------------|------|------|
| 原始点云 | `unilidar.rviz` | `unilidar_lidar` | `/unilidar/cloud` | 启动/打开/停止雷达 | 1 |
| 车体对齐 | `unilidar_base.rviz` | `base_link` | `/unilidar/cloud_aligned` | 启动/打开/停止雷达 | 2 |
| 雷达/里程计 | `unilidar_mapping.rviz` | `odom` | `/cloud_registered` + `/odom` + `/odom_path` | 启动/打开/停止定位 | 4 |

`/unilidar/cloud_aligned` 由 `l1_cloud_align` 用 ROS2 `SensorDataQoS`
发布，可靠性是 **Best Effort**。`unilidar_base.rviz` 的 PointCloud2
Display 必须同样使用 `Reliability Policy: Best Effort`；如果误设为
`Reliable`，现象是原始点云正常、`l1_stack` 显示 `aligned=yes`，但车体
对齐 RViz 空白，并在 RViz 日志中出现
`incompatible QoS ... RELIABILITY_QOS_POLICY`。

主按钮：

- **启动雷达**（原始/对齐模式）：幂等 start L1 驱动 + static TF + l1_cloud_align
- **启动定位**（雷达/里程计模式）：SSH 执行 `l1_lio.sh start`（L1 栈 + Point-LIO + lio_odom_adapter）
- **打开雷达视图 / 打开定位视图**：topic/TF 预检通过后打开本地 RViz
- **停止雷达 / 停止定位**：对应远端 stop，并关闭本地 RViz

定位视图打开前必须同时满足：

```text
/cloud_registered publisher
/odom publisher
/odom_path publisher
TF odom -> base_link
```

任一缺失时拒绝打开，并提示具体缺失项。`/odom` 由 `lio_odom_adapter` 从 `/aft_mapped_to_init` 按

```text
T_odom_base = T_camera_init_imu * inverse(T_base_imu)
```

变换得到，**不**使用 `/cmd_vel`。
一行摘要示例：

```text
原始点云：点云 8.8Hz · TF 正常 · 雷达运行中
车体对齐：对齐点云在线 · TF 缺失(仅坐标轴) · 雷达运行中
```

车体对齐视图的点云已经由 `l1_cloud_align` 发布成 `frame=base_link`，
所以主画面显示以 `/unilidar/cloud_aligned` publisher 为准。`base_link →
unilidar_lidar` 静态 TF 缺失只会影响 RViz 里的坐标轴/TF 辅助显示，不应
判定为“车体对齐点云不可用”。

展开 **点云对齐…** → 编辑 xyz（米） / roll·pitch·yaw（度）→ **读取对齐参数** / **应用对齐参数**
（应用对齐参数 = 写 `l1_cloud_align.yaml` + 仅重启 l1_cloud_align 节点，不动 L1 驱动，不动 static TF）

点云对齐窗口的姿态微调是给现场使用者看的“人话”：

```text
roll（左右歪，先调这个）
pitch（前后翘，再调这个）
yaw（车头方向偏，最后调）
```

这里调的是 `/unilidar/cloud_aligned` 的点云整体，不是 RViz 坐标轴显示。
当前现场调平楼顶/地面时，`roll` 已验证为主调参数。

代码和 YAML 里的语义如下，后续 agent 不要混淆：

- `base_rpy_rad`：L1 卧放安装基准，表示 `lidar +Z -> base +X`、`lidar +X -> base +Z`、`lidar +Y -> base -Y`，通常不由 UI 修改。
- `trim_rpy_rad`：在 `base_link` 车体系里的现场微调。UI 只改这一组。
- 最终点云变换是 `R_final = R_trim_base * R_base_lidar`，也就是先把 L1 原始点云转进车体，再绕车体轴微调。

闭环：

```text
启动雷达 -> 打开雷达视图 -> 点云对齐 -> 应用对齐参数 -> 目视确认 -> 停止雷达
```

- 地面/楼顶左右倾斜：优先调 **roll**
- 前后俯仰不平：调 **pitch**
- 水平车头方向错：调 **yaw**
- 点云整体前后左右偏、姿态已平：再调 `xyz`

阶段二不再靠 `base_link -> unilidar_lidar` 静态 TF 来「视觉调平」——
static TF 只用于保证坐标树存在；真实的点云旋转由 `l1_cloud_align`
在 Jetson 上完成并发布到 `/unilidar/cloud_aligned`。

首次同步 Jetson 脚本（开发机）：

```bash
bash jetson/scripts/jetson.sh ros2 push --yes
# 可选 CLI：bash jetson/scripts/jetson.sh ros2 l1-status
```

VM cockpit：`bash jetson/scripts/vmware.sh deploy`，并在 VM `cockpit/.env` 配好 `JETSON_SSH_*`。

`l1_stack.sh stop` / `l1_static_tf.sh stop` 会结束 `unilidar_lidar` 相关 static TF；**勿同时手工另起同 child frame 的 static TF**。

然后 VM 上 `bash run.sh` → 选「车体对齐」→ 启动 RViz。

**方式 B：仅脚本（无 Qt）**

```bash
cd jetson/cockpit
export ROS_DOMAIN_ID=0
bash scripts/start_unilidar_rviz.sh
# 关闭：bash scripts/stop_unilidar_rviz.sh
```

也可以完全绕过 Qt：

```bash
cd /mnt/d/Downloads/work/ros-dev/jetson/cockpit
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
ros2 topic list
timeout 12 ros2 topic hz /unilidar/cloud
rviz2 -d config/unilidar.rviz
```

验收：VMware/VM 观测端 `ros2 topic list` 能看到 `/unilidar/cloud`，`/unilidar/cloud` 接近 9Hz，`/unilidar/imu` 高频；RViz 不手动 Add Display 即可看到点云，遮挡雷达有变化。

### 阶段一验收状态（2026-07-09）

阶段一已通过。Jetson 侧 L1 正常：

```text
/dev/unilidar_lidar -> ttyCH341USB0
/unilidar/cloud publisher=unitree_lidar_ros2_node, ~8.76Hz
/unilidar/imu ~246Hz
Jetson ROS_DOMAIN_ID=0, ROS_LOCALHOST_ONLY=0
```

VM `172.0.0.87` 作为观测端已完成闭环：

```text
可见 /unilidar/cloud 和 /unilidar/imu
/unilidar/cloud ~8.8Hz
/unilidar/imu ~246Hz
RViz: config/unilidar.rviz
Fixed Frame: unilidar_lidar
PointCloud2: /unilidar/cloud
RViz 目视点云已确认
```

历史 DDS 观测端故障已经归档到 [../docs/archive/历史-DDS观测端排障记录.md](../docs/archive/历史-DDS观测端排障记录.md)。当前不再维护其他 cockpit/RViz 运行环境。

### L1 安装方向（卧放）与坐标轴对齐（重要）

宇树 L1 的坐标系定义以官方文档为准（示意图/说明见 [L1 Overview & Use](https://support.unitree.com/home/zh/L1_SDK/L1_Overview_Use)）。

如果 L1 **卧放**安装，实车上常见现象是：在 RViz 里看 `unilidar_lidar` 的三色轴时，
**蓝色 Z 轴**可能指向车头（“Z 轴超前”）。这会导致点云/障碍的“前后左右”与车体直觉不一致。

**不要靠猜**，用 RViz 直接确认：

- Fixed Frame 临时设为 `unilidar_lidar`
- 打开 `Axes_lidar`（`unilidar.rviz` 已包含），观察车头方向对应 `X(红)/Y(绿)/Z(蓝)` 哪根轴

处理原则（避免乱改）：

- **阶段 2（只看原始点云）**：优先用 `Fixed Frame=unilidar_lidar`，不依赖 `odom/base_link` TF，先把点云“能看见”跑通。
- **阶段 2.5（雷达/里程计联动）**：当你需要 `Fixed Frame=odom`（点云跟随 `/odom` 移动）时，必须保证 TF 链完整：
  `odom -> base_link -> unilidar_lidar`。
  若确认存在“Z 轴超前”，L1 卧放安装基准必须在静态 TF 与 `l1_cloud_align` 配置中保持一致，把雷达前方对齐到 `base_link` 的 **X** 轴；
  现场目视调平只修改 `l1_cloud_align.yaml` 的 `trim_rpy_rad`，不要用转 RViz 坐标轴代替点云对齐，也不要改 topic 名称或驱动发布逻辑。

### LIO / 里程计观测（阶段 4）

Jetson 端完整定位栈：

```bash
bash jetson/scripts/jetson.sh ros2 push --yes
bash jetson/scripts/jetson.sh ros2 lio-build
bash jetson/scripts/jetson.sh ros2 lio-start   # = l1_lio.sh start
```

或在 VMware cockpit 选择 **「雷达/里程计」** → **「启动定位」** → **「打开定位视图」**，加载 `config/unilidar_mapping.rviz`：

```text
Fixed Frame: odom
CloudRegistered: /cloud_registered
Odometry: /odom
Path: /odom_path
TF: enabled（odom -> base_link -> unilidar_lidar -> unilidar_imu）
RawCloud: disabled
```

`/odom` 由 Jetson 侧 `lio_odom_adapter` 从 Point-LIO 的 `/aft_mapped_to_init` 适配而来。底盘不可用时，真实移动观测来自 L1 点云 + L1 内置 IMU，不用 `/cmd_vel` 伪造 odom。
2026-07-14 已完成约 35 cm 人工搬运：物理位移可在 RViz 中由 `/odom`、`/odom_path` 和配准点云连续显示，估计位移约 34.9 cm。该结果证明定位观测闭环基本成立，但没有严格地面尺量，不能替代导航级精度验收。

下一步等底盘恢复正常行走后，完成 3～5 米直行、往返和转向测试；通过后再进入台阶识别与相机互补。当前不把短距离搬运结果写成“导航完成”。
## 遥控模式

遥控面板参考 `vmware/qt` 的基础遥控模式，保持同一套按键语义：

- 按住运动、松开停止。
- 运动期间约 10Hz 重发当前 `/cmd_vel`。
- 左 / 右是原地转向。
- 窗口失焦、隐藏、关闭时发送停止。
- `K` / `Space` 为停止。

| 动作 | 鼠标按钮 | 键盘 | `/cmd_vel` |
|---|---|---|---|
| 前进 | 前进 | `W` / `I` / `↑` | `linear.x = 1.0`, `angular.z = 0.0` |
| 后退 | 后退 | `S` / `↓` | `linear.x = -1.0`, `angular.z = 0.0` |
| 左转 | 左转 | `A` / `Q` / `J` / `←` | `linear.x = 0.0`, `angular.z = 1.0` |
| 右转 | 右转 | `D` / `E` / `L` / `→` | `linear.x = 0.0`, `angular.z = -1.0` |
| 停止 | 停止 | `K` / `Space` | `linear.x = 0.0`, `angular.z = 0.0` |

Jetson 侧 dry-run bridge 会把 `/cmd_vel` 转译为：

```text
FORWARD / BACKWARD / TURN_LEFT / TURN_RIGHT / STOP
```

并发布：

```text
/vehicle/control_action  std_msgs/String
```

## 连接性检查

界面参考 `vmware/qt` 的「环境状态 / Topic 诊断」，但 ROS2 没有 ROS1 Master，
所以这里检查的是 DDS graph：

- 「刷新状态」：查询 `ros2 node list`，并检查关键 topic。
- 「检查环境」：显示 `ROS_DOMAIN_ID`、`ros2`、`rclpy`、node list、topic list。
- 「检查关键 topic」：
  - `/cmd_vel` 应该有 subscriber，表示 Jetson 侧 dry-run bridge 正在订阅。
  - `/vehicle/control_action` 应该有 publisher，表示 Jetson 侧 dry-run bridge 正在回显动作。

注意：远端能力仍只在 `jetson/mirror/ros2_ws` 里实现，当前只有
`/cmd_vel -> FORWARD/BACKWARD/TURN_LEFT/TURN_RIGHT/STOP` 的简单转译。
cockpit 只做本地 Qt 控制台、DDS 连接性观察和调试入口。

## CLI 调试工具

CLI 只是 smoke test，不是 cockpit 主入口：

```bash
cd jetson/cockpit
source /opt/ros/humble/setup.bash

python3 scripts/cmd_vel_sender.py forward
python3 scripts/cmd_vel_sender.py backward
python3 scripts/cmd_vel_sender.py left
python3 scripts/cmd_vel_sender.py right
python3 scripts/cmd_vel_sender.py stop

python3 scripts/control_action_echo.py
```

## 验收边界

`cockpit/` 只运行在 VMware 观测端，不部署到 Jetson。雷达驱动编译与 topic 验证**只认远端 Jetson**；任何本机构建都不作为雷达验收依据，L1/RViz 观测只认 VMware 侧闭环。

### 改哪里要部署

| 改动位置 | 要不要上 82 | 怎么生效 |
|----------|-------------|----------|
| 只改 `jetson/cockpit/`（`.rviz`、Qt 面板、`scripts/*.sh`） | **不用** | `cd jetson/cockpit && bash run.sh`，重开 RViz |
| 改 `jetson/mirror/ros2_ws/`（yaml、脚本、ROS2 包） | **要 deploy** | `jetson.sh ros2 deploy` → `jetson.sh ros2 restart` |
| 只想重启 LIO 层调试 | 不改代码时不用 build | `jetson.sh ros2 lio-stop` → `jetson.sh ros2 lio-start` |

```bash
bash jetson/scripts/jetson.sh ros2 deploy
bash jetson/scripts/jetson.sh ros2 restart
```

### 控制链路（干跑）

```text
PC / VMware cockpit -> /cmd_vel
Jetson ~/qt/ros2_ws -> cmd_vel_car_web_bridge -> /vehicle/control_action
```

验收：cockpit 发五向指令，Jetson 日志或 `/vehicle/control_action` 回显
`FORWARD / BACKWARD / TURN_LEFT / TURN_RIGHT / STOP`。

部署：`bash jetson/scripts/jetson.sh ros2 deploy` + `ros2 start`。

### 雷达观测（L1 原始点云）

```text
Jetson 82 -> /unilidar/cloud + /unilidar/imu
VMware/VM -> cockpit 雷达面板 / rviz2（config/unilidar.rviz）
```

验收：

1. 观测端 `ros2 topic list` 能看到 `/unilidar/cloud` 和 `/unilidar/imu`。
2. cockpit 选择「原始点云」后点「启动 RViz (观测端本地)」（或 `scripts/start_unilidar_rviz.sh`），无需手配 Display。
2. RViz 点云可见，遮挡雷达有变化；左侧 Displays 无红色异常项。
3. 面板或 CLI：cloud ~9Hz、imu 高频。

`/odom`、`/odom_path`、`/cloud_registered`、TF 链完整性属于后续 LIO / TF 阶段，不作为 L1 原始点云阶段的验收条件。观测端可用 `ros2 topic hz /unilidar/cloud` 辅助确认；最终以 Jetson 侧频率、观测端 topic discovery、RViz 目视三者共同为准。

## 当前边界

不要在本阶段做这些事：

- 不调用 `car_web` HTTP API。
- 不引入 `requests` 做控制。
- 不碰前轮、扒手、升降、调平或串口电机代码。
- 不做导航、SLAM、自动避障。
- 不把 cockpit 部署到 Jetson。

Jetson 侧 ROS2 包在：

```text
jetson/mirror/ros2_ws/src/cmd_vel_car_web_bridge/
```
