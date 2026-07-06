> 归档说明：这是 RK3568 / xtark / PC 联调的临时讨论稿。关键结论已整理到 `pc/docs/WSL2统一栈运行与调试.md`、`pc/docs/移动平台外挂感知建图导航方案.md` 和 `xtark/docs/archive/JSON控制适配方案.md`。本文件仅保留参考。

你的计划方向是对的：**RK3568 和 xtark 解耦，PC 做汇聚中心**，这和仓库里 `xtark/docs/archive/JSON控制适配方案.md` 第 11 节、RK3568 外挂感知方案一致。我会按「先独立、再汇聚、先可视化、后 SLAM」来试，每步都有明确验收，不过线不往下走。

---

## 总体原则

```text
三条链路分开验：
  RK3568 /scan          — ROS2 网络
  xtark odom_base       — TCP JSON
  xtark 控制 cmd_vel    — TCP JSON（Qt 调试台，与反馈分开）

PC 只做汇聚，不做“绑死”：
  不把 xtark 雷达拉起来
  不让 RK3568 控底盘
```

---

## 第一步：两条链路独立稳定（1–2 天）

### A. RK3568 `/scan`

```bash
# RK3568 上
cd ~/deploy/sensor_stack && docker compose up -d

# PC 上（ROS2 Humble，与 RK 同网段、同 ROS_DOMAIN_ID）
export ROS_DOMAIN_ID=0   # 与 RK 一致
ros2 topic list | grep scan
ros2 topic hz /scan
ros2 topic echo /scan --once
```

**验收：**
- `/scan` 稳定存在，频率大致 5–10 Hz（看雷达型号）
- 连续 5 分钟无断流
- `frame_id` 记下来（后面 TF 用，常见 `laser` 或 `laser_link`）

Astra 这一步**先不验**，第一轮只要 `/scan`。

### B. xtark `odom_base`

```text
终端1: xtark_driver
终端2: json_base_adapter
PC:    pc/qt_client  或  pc/tools/xtark_json_keyboard.py
```

**验收：**
- Qt 调试台稳定收到 `odom_base`、`base_status`
- 低速前进：`x` 增大；左转：`yaw` 按约定方向变
- 反馈频率约 20 Hz（adapter 配置），电池电压有数

### C. 时间戳/频率记录表（手写即可）

| 来源 | 字段 | 期望 |
|------|------|------|
| RK `/scan` | `header.stamp` | 单调递增，延迟 < 100ms 量级 |
| xtark JSON | `stamp_ms` | 与 PC 本地时间差 < 200ms |
| xtark JSON | 实际到达率 | ~20 Hz odom，~2 Hz status |

**这一步不做建图，不做 ROS2 转换。**

---

## 第二步：PC 数据汇聚层（核心，建议新建 `pc/ros2_bridge/`）

这是我会优先写的小程序，职责单一：

```text
json_odom_bridge.py（或一个小 package）
  订阅：TCP JSON（复用 json_client 逻辑）
  发布：ROS2 /odom_base (nav_msgs/Odometry)
        ROS2 /base_status (自定义 msg 或 std_msgs/String JSON)
  可选：tf2 广播 odom -> base_link
```

**PC 上同时跑：**

```text
[已有] RK3568 ROS2  →  PC 直接 ros2 topic echo /scan
[新建] json bridge  →  PC 发布 /odom_base
```

**验收：**

```bash
ros2 topic hz /scan
ros2 topic hz /odom_base
ros2 topic echo /odom_base --once
```

两边 topic 同时有数据，且**遥控时 odom 在动、雷达 scan 也在刷**。

实现上建议：
- Python + `rclpy`，复用 `pc/qt_client/json_client.py` 的 TCP 部分
- `odom_base` 的 `frame_id` 先固定：`odom`（pose）、`base_link`（child）
- twist 直接用 JSON 里的 `linear_x/y`、`angular_z`（adapter 已做差分）

---

## 第三步：RViz2 可视化（先不 SLAM）

```bash
rviz2
```

添加：
- **LaserScan** → `/scan`，Fixed Frame 先用 `odom` 或 `base_link`
- **Odometry** → `/odom_base`
- 看 **TF** 树是否缺链

**重点检查（低速遥控一圈）：**

| 检查项 | 期望 |
|--------|------|
| 前进 | `x` 增加，scan 随车体一起“走” |
| 左转 | `yaw` 增加方向与车头一致 |
| 雷达方向 | scan 开口朝前（不对就调 `base_link→laser` 的 yaw） |
| 连续性 | 无明显跳变、卡顿 |

这一步**仍不跑 slam_toolbox**，只看“数据能不能对上”。

---

## 第四步：补静态 TF

```bash
# base_link -> laser（量出来的安装位）
ros2 run tf2_ros static_transform_publisher \
  0.15 0 0 0 0 0 base_link laser
```

```text
odom -> base_link   由 json bridge 根据 odom_base 动态发布
base_link -> laser  静态，手工测量后写入 launch/yaml
```

**验收：**

```bash
ros2 run tf2_tools view_frames
```

TF 树至少是：

```text
odom -> base_link -> laser
```

RViz2 Fixed Frame 设 `odom`，scan 和轨迹应重合。

---

## 第五步：slam_toolbox 低速闭环

PC 上最小配置：

```text
输入：/scan + /odom_base（或 remap 成 /odom）+ TF
输出：/map
控制：pc/qt_client 低速遥控
```

**第一轮目标不是漂亮地图，而是：**

- 走一圈能闭合（大致）
- 地图随运动展开，不整片漂移
- 断流/延迟时观察是否立刻坏图

参数建议：先低速 `0.05–0.10 m/s`，角速度 `0.1–0.15 rad/s`。

---

## 我会怎么排终端（联调时）

| 机器 | 进程 |
|------|------|
| RK3568 | `sensor_stack` Docker（/scan） |
| xtark | `xtark_driver` + `json_base_adapter` |
| PC | `json_odom_bridge`（ROS2 发布） |
| PC | `qt_client`（控制 + 看 JSON 反馈） |
| PC | `rviz2` / 后续 `slam_toolbox` |

控制用 Qt，状态监控也用它；**不要再让键盘脚本和 RViz 抢焦点**。

---

## 阶段边界（同意你的裁剪）

**第一轮 RK 联调只做到：**

```text
✓ PC 同时有 /scan + /odom_base
✓ RViz2 里方向、运动一致
✗ Nav2 / AMCL / 避障 / 相机点云 / 融合
```

---

## 风险点（提前知道）

1. **ROS2 跨机**：`ROS_DOMAIN_ID`、防火墙、多网卡要一致；RK 用 `network_mode: host` 一般没问题。
2. **时间同步**：第一轮用各自时间戳即可；SLAM 漂移大时再考虑 NTP/Chrony。
3. **frame 命名**：RK 的 `laser` 与 xtark 的 `base_link` 要对齐，否则 RViz 会“雷达飞走”。
4. **控制与反馈分离**：JSON 控制走 Qt；ROS2 只管感知汇聚，避免混在一个进程里。
5. **xtark 自带雷达别启**：`xtark_bringup` 里 rplidar 会报错，可忽略；建图只用 RK 的 `/scan`。

---

## 建议的下一步（若开始写代码）

按优先级：

1. **`pc/ros2_bridge/`** — JSON → `/odom_base` + TF（第二步）
2. **`pc/ros2_bridge/launch/`** — 静态 `base_link→laser` + bridge 一键起
3. **文档** — 在 `xtark/docs/archive/JSON控制适配方案.md` 补 PC 环境变量和验收命令（你文档里第 11 节已有骨架）

如果你愿意，我可以下一步直接帮你搭 `pc/ros2_bridge` 的最小 `json_odom_bridge` 节点（`rclpy` + 复用现有 TCP 客户端），把第二步落地。
