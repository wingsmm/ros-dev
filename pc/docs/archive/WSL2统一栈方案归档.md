# WSL2 统一栈方案

> 状态：**已实现**（`pc/qt_client/`）

## 1. 目标

PC 联调侧 **只开一个程序** `pc/qt_client`，在 WSL2 + WSLg 下完成：

```text
连接 xtark、GUI 遥控、看 JSON 状态
JSON → ROS2（/odom_base、TF）
GUI 一键启停 RViz2、slam_toolbox
```

**不要：**

- 拆 `json_gateway` + GUI 两个进程
- 开 local proxy 8766
- 建图时再开第三个、第四个终端跑 rviz / slam / static_tf

**要：**

- 一个窗口：连车、遥控、看状态、开 RViz、开 SLAM
- xtark 仍然只有 **1 条 TCP**

## 2. 架构

```text
┌─────────────────────────────────────────────────────────┐
│ WSL2 + ROS2 Humble + WSLg                               │
│                                                         │
│  qt_client（单进程、单窗口）                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 连接区      host:port、连接/断开                  │   │
│  │ 遥控区      WASD / 按钮、速度参数                 │   │
│  │ 状态区      odom_base、base_status               │   │
│  │ 建图栈区    [启动 RViz2] [启动 SLAM] [全部停止]   │   │
│  │ 日志区      JSON / 栈启停日志                     │   │
│  └─────────────────────────────────────────────────┘   │
│       │ TCP cmd_vel              ▲ JSON odom_base       │
│       ▼                          │                      │
│  json_client ────────────────────┘                      │
│  ros2_pub  ──► /odom_base、TF(odom→base_link→laser)     │
│  ros_stack ──► 子进程 rviz2、slam_toolbox（GUI 启停）   │
│                                                         │
│  RK3568 ──DDS──► /scan ──► RViz / SLAM 订阅             │
└─────────────────────────────────────────────────────────┘

xtark :8765 ◄── 唯一 TCP
```

## 3. 模块划分（全在 `pc/qt_client/`）

| 模块 | 文件 | 职责 |
|------|------|------|
| 主界面 | `app.py` | 布局、事件、退出清理 |
| TCP JSON | `json_client.py` | 已有；连 xtark、发 cmd_vel、收反馈 |
| ROS2 发布 | `ros2_pub.py` | odom_base → /odom_base + 动态/静态 TF |
| 建图栈管理 | `ros_stack.py` | 子进程启停 rviz2、slam_toolbox |
| 界面组件 | `widgets/` | control / status / log + stack_panel |

进程关系：

```text
app.py
  ├─ json_client     与 xtark 通信
  ├─ ros2_pub        同进程 rclpy（QTimer spin_once）
  └─ ros_stack       子进程管理（不同进程，但由 GUI 按钮控制，用户不碰终端）
```

说明：RViz2 / slam 仍是独立 OS 进程（ROS 工具本身如此），但 **由 GUI 启动和停止**，用户不需要自己开终端。

## 4. 界面设计

### 4.1 建图栈面板（`StackPanel`）

| 控件 | 行为 |
|------|------|
| 启动 RViz2 | `subprocess` 启动 `rviz2`，WSLg 弹窗 |
| 停止 RViz2 | SIGTERM 进程组 |
| 启动 SLAM | `ros2 launch slam_toolbox online_async_launch.py` |
| 停止 SLAM | SIGTERM 进程组 |
| 一键启动建图栈 | 依次启动 SLAM → RViz2（或并行） |
| 全部停止 | 关 SLAM、RViz2；GUI 退出时也自动调用 |

状态显示：`RViz2: 运行中/未运行`、`SLAM: 运行中/未运行`

### 4.2 推荐操作流（用户视角）

```text
1. WSL2 开一个终端：source ROS2 → python app.py
2. GUI 点「连接」→ xtark
3. GUI 点「一键启动建图栈」
4. 用 WASD 低速遥控建图
5. 结束：点「全部停止」→ 断开 → 关窗口
```

全程 **一个终端 + 一个 GUI 窗口**（RViz 会多一个可视化窗口，但不是命令行终端）。

## 5. ROS2 职责

### 5.1 `ros2_pub.py`（同进程）

收到 JSON 后：

| JSON | ROS2 输出 |
|------|-----------|
| `odom_base` | `/odom_base`（nav_msgs/Odometry）+ TF `odom→base_link` |
| `base_status` | `/base_status`（std_msgs/String，JSON 原文） |

启动时一次性发布静态 TF：

```text
base_link → laser（z 等参数可配置，默认 z=0.15）
```

不再单独跑 `static_transform_publisher` 终端。

### 5.2 `ros_stack.py`（子进程）

启动前自动注入环境：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0   # 与 RK3568 一致
```

| 服务 | 命令 |
|------|------|
| RViz2 | `rviz2` |
| SLAM | `ros2 launch slam_toolbox online_async_launch.py use_sim_time:=false slam_params_file:=config/slam_toolbox_xtark.yaml` |

子进程用 `start_new_session=True`，停止时对进程组发 SIGTERM，避免残留。
子进程 stdout / stderr 写入 `pc/qt_client/logs/`，启动后立即退出时 GUI 日志会提示退出码和日志路径。

### 5.3 SLAM 所需 topic（第一轮）

| Topic / TF | 来源 |
|------------|------|
| `/scan` | RK3568 DDS |
| `/odom_base` 或 TF odom→base_link | ros2_pub |
| TF base_link→laser | ros2_pub 静态 |
| `/map` | slam_toolbox 输出 |

## 6. 运行模式

| 模式 | 启动 | 用途 |
|------|------|------|
| **默认** | `python app.py` | GUI + ROS2 + 建图栈按钮 |
| **仅 JSON** | `python app.py --no-ros` | 只验 TCP；建图栈按钮禁用 |

默认连接 `192.168.1.169:8765`。

## 7. 启动命令（用户只需记这一条）

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
cd /mnt/d/Downloads/work/ros-dev/pc/qt_client
./run.sh
```

其余（RViz、SLAM、static TF）全在 GUI 里点。

## 8. 验收标准

| 阶段 | 验收 |
|------|------|
| JSON | 连接 xtark，odom x/y/yaw 随车变 |
| ROS2 | 连接后 `ros2 topic hz /odom_base` 有数据（可在 WSL2 另开终端仅做 debug，日常不必） |
| GUI 建图栈 | 点「启动 RViz2」弹出窗口；点「启动 SLAM」无报错 |
| 同屏 | RViz 里 /scan + TF 方向与遥控一致 |
| SLAM | 低速遥控一圈，/map 有内容 |
| 清理 | 「全部停止」+ 关 GUI 后无残留 rviz/slam 进程 |

## 9. 与下周 TODO 映射

| TODO | 本方案 |
|------|--------|
| 1. xtark bringup | xtark 上 bringup + json_adapter |
| 2. 复验 JSON | `python app.py --no-ros` |
| 3. 频率 | 连接后看 GUI 状态 + 可选 `ros2 topic hz` |
| 4. JSON→ROS2 | 实现 `ros2_pub.py` |
| 5. TF | 合在 `ros2_pub.py`，不另开终端 |
| 6. RViz2 | `StackPanel` + `ros_stack.start_rviz()` |
| 7. slam_toolbox | `StackPanel` + `ros_stack.start_slam()` |
| 8. 文档 | 本文 |

## 10. 实现顺序（写代码时）

1. **P0** `ros2_pub.py` + 接入 `app.py`（JSON → ROS2 + TF）
2. **P0** `ros_stack.py` + `widgets/stack_panel.py`（RViz / SLAM 启停）
3. **P1** 退出 / 全部停止时：发 stop cmd_vel、停子进程、ros2 shutdown
4. **P2** RViz 默认配置 `.rviz`（可选，第一轮可手动 Add Display）
5. **P2** Nav2 / ROS2 `/cmd_vel` 订阅（第一轮不做）

## 11. 约束与风险

| 项 | 说明 |
|----|------|
| 一条 TCP | 不要同时开 qt_client 和 `check_links.py` 连 xtark |
| WSLg | GUI / RViz 需 WSLg；Windows 直跑仅备用 |
| rclpy | 系统 ROS2 包，不进 pip |
| slam 参数 | 第一轮用 slam_toolbox 默认 launch；frame 不对再调 yaml |
| RViz 不是嵌入 Qt | RViz 仍独立窗口，只是 **从 GUI 启动**，不嵌入 PyQt（避免过度复杂） |

## 12. 与旧方案差异

| 旧 | 新 |
|----|-----|
| json_gateway + qt_client + proxy | **一个 qt_client** |
| RViz / SLAM 另开终端 | **GUI 按钮启停** |
| static_tf 单独命令 | **合入 ros2_pub** |
| Windows + WSL2 分裂 | **统一 WSL2** |

---

**一句话：一个 GUI 搞定连车、遥控、ROS2 发布、开 RViz、开 SLAM；用户只开一次 `python app.py`。**
