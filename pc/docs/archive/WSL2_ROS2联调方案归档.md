# WSL2 ROS2 联调方案

## 1. 目的

VMware 中直接接 USB 深度相机和 2D 雷达存在效率和网络问题，因此 USB 传感器改接 RK3568。PC 侧统一使用 WSL2 作为 ROS2 x86 开发和联调中心，`pc/qt_client` 是唯一日常入口。

当前主线：

```text
WSL2 (PC 联调中心)
  运行 pc/qt_client
  订阅 RK3568 ROS2 /scan
  TCP 接收 xtark odom_base / base_status
  TCP 发送 xtark cmd_vel
  GUI 启停 RViz2 / slam_toolbox

RK3568
  只负责 Astra / RPLidar 等 USB 传感器采集

xtark
  只负责底盘运动、里程计反馈、低速控制验证
```

不再使用 VMware 直连 USB 传感器作为当前主线。

## 2. 当前连通状态

日期：2026-06-05

| 链路 | 状态 | 说明 |
|------|------|------|
| WSL2 ↔ RK3568 ping | 通过 | 约 5-15 ms |
| RK3568 本机 `/scan` | 通过 | `astra-camera` 容器内约 14 Hz |
| WSL2 ← RK3568 `/scan` | 通过 | WSL 原生 `ros2 topic hz /scan` 约 14 Hz |
| WSL2 ↔ xtark ping | 通过 | xtark 开机时可达 |
| WSL2 ↔ xtark JSON `8765` | 通过 | `cmd_vel` 可发，`base_status` 正常 |
| WSL2 ← xtark `odom_base` | 待完成 | 需 `xtark_bringup` 跑起来后才有 `/odom` |

当前架构分工：

```text
RK3568  -> WSL2   /scan、/camera/*       已通
xtark   -> WSL2   base_status、cmd_vel    已通
xtark   -> WSL2   odom_base              待 bringup
WSL2    -> 建图   /scan + odom_base 汇聚  未做
```

阶段结论：

```text
WSL2 作为 PC 联调中心成立；
RK3568 /scan 已跨机进入 WSL2；
xtark JSON 控制和状态链路已通；
下一步只差 xtark bringup 后拿 odom_base。
```

## 3. 三端分工

| 设备 | 职责 |
|------|------|
| WSL2 | 运行 `pc/qt_client`，承载 GUI、JSON、ROS2 发布、RViz2、slam_toolbox |
| RK3568 | 传感器盒，发布 ROS2 `/scan` 和相机 topic |
| xtark | 底盘运动、`odom_base`、`base_status`、接收 `cmd_vel` |

不要把 USB 相机和雷达重新接回 WSL2。WSL2 只通过网络接收数据。也不要把 Qt GUI 放回 Windows 原生运行，避免 Windows / WSL2 两套环境分裂。

统一栈可行性：

```text
RK3568 /scan 已能进入 WSL2 原生 ROS2；
xtark JSON 8765 已能被 WSL2/PC 连接；
WSLg 支持 PyQt5 和 RViz2 窗口；
qt_client 可在同一进程中完成 JSON -> ROS2 /odom_base + TF。
```

## 4. 操作顺序

### 4.1 确认 WSL2 网络

WSL2 建议使用 Mirrored 网络，保证 WSL2 与 RK3568、xtark 在同一局域网段。

```bash
ip -4 addr
ping 192.168.1.163
ping 192.168.1.169
```

当前实测：

```text
RK3568: 192.168.1.163
xtark:  192.168.1.169
WSL2:   192.168.1.137 附近的 192.168.1.x 地址
```

### 4.2 确认 RK3568 `/scan`

RK3568 宿主机无 `ros2` 是正常的，ROS2 在 `astra-camera` 容器内。

RK3568 本机验收：

```bash
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  export ROS_DOMAIN_ID=0
  ros2 topic list | grep scan
  ros2 topic hz /scan
'
```

WSL2 跨机验收：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
ros2 topic hz /scan
```

通过标准：

```text
/scan average rate 约 14 Hz
```

注意：`ros2 topic list` 偶发可能较晚显示 `/scan`，以 `ros2 topic hz /scan` 稳定输出为准。

### 4.3 启动 xtark 车端

xtark 上启动底盘：

```bash
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
roslaunch xtark_driver xtark_bringup.launch
```

另一个终端启动 JSON 适配：

```bash
source /opt/ros/melodic/setup.bash
source ~/ros_ws/devel/setup.bash
roslaunch xtark_json_bridge json_base_adapter.launch
```

说明：

- `json_base_adapter` 监听 TCP `8765`。
- 只有 `json_base_adapter` 时可以收到 `base_status`，也可以发 `cmd_vel`。
- `odom_base` 依赖 xtark `/odom`，需要 `xtark_bringup` 正常运行。

### 4.4 WSL2 测 xtark JSON

```bash
cd /mnt/d/Downloads/work/ros-dev/pc/tools
python3 check_links.py
```

低速遥控：

```bash
python3 xtark_json_keyboard.py --host 192.168.1.169 --port 8765 --speed 0.10 --turn 0.20
```

只发低速测试指令：

```bash
python3 send_cmd_vel_json.py --host 192.168.1.169 --linear-x 0.05 --duration 2
```

## 5. 已解决的问题

| 问题 | 现象 | 处理 |
|------|------|------|
| WSL2 NAT | WSL2 是 `172.31.x.x`，RK3568 回连不到，DDS 发现失败 | 改 WSL2 Mirrored，WSL2 获得 `192.168.1.x` |
| Docker 测跨机 ROS2 不可靠 | `docker run --net=host` 仍在 `192.168.65.x` | WSL2 内原生安装 `ros-humble-ros-base` 测 DDS |
| PC 防火墙 / WLAN 公用网络 | RK3568 ping PC 不通，DDS 回包被拦 | 放行 UDP `7400-7500`，确保 RK 能 ping 通 WSL2/PC |
| xtark JSON 服务未自启 | `8765 Connection refused` | 远程启动 `json_base_adapter` |
| xtark bringup 未常驻 | 无 `/odom`，收不到 `odom_base` | 需要前台运行 `xtark_driver xtark_bringup.launch` |
| 传感器迁移到 RK3568 | xtark 上雷达不可用或可忽略 | 建图使用 RK3568 `/scan` + xtark `odom_base` |

## 6. DDS 注意事项

ROS2 DDS 发现需要双向 UDP，不是单向 ping 通就一定能发现 topic。

关键经验：

```text
WSL2 NAT 下：
  WSL2 -> RK3568 ping 可能通
  RK3568 -> WSL2 172.31.x.x 不通
  DDS 发现失败

WSL2 Mirrored 下：
  WSL2 使用 192.168.1.x
  RK3568 可回连
  /scan 可被 WSL2 订阅
```

当前推荐：

```text
WSL2 Mirrored + WSL2 原生 ROS2 + 防火墙放行 UDP 7400-7500
```

如果后续再次看不到 `/scan`，排查顺序：

| 问题 | 处理 |
|------|------|
| ping 不通 | 先查 Windows / WSL2 网络和防火墙 |
| ping 通但无 `/scan` | 查 `ROS_DOMAIN_ID` 是否一致 |
| domain 一致仍无 `/scan` | 再考虑 FastDDS / CycloneDDS peer 配置 |
| RK 本机无 `/scan` | 回到 RK3568 `sensor_stack` 检查容器和 USB |

## 7. 后续建图链路

数据流目标：

```text
RK3568 /scan  --------------------\
                                    -> WSL2 qt_client -> ROS2 / RViz2 / slam_toolbox
xtark JSON odom_base / base_status /
```

`qt_client` 负责把 JSON 反馈发布进 ROS2：

```text
xtark JSON odom_base -> ROS2 /odom_base
xtark JSON base_status -> ROS2 /base_status
```

再补 TF：

```text
odom -> base_link     来自 xtark odom_base
base_link -> laser    来自外挂雷达安装位置，先静态发布
```

## 8. 下一步

按优先级：

| 优先级 | 任务 | 验收 |
|--------|------|------|
| P0 | 前台启动 xtark `xtark_bringup` | WSL2 收到 `odom_base` |
| P0 | 记录 `/scan` 与 `odom_base` 频率 | `/scan` 约 14 Hz，`odom_base` 连续变化 |
| P1 | 用 `qt_client` 发布 JSON -> ROS2 | WSL2 出现 `/odom_base`、`/base_status` |
| P1 | 发布 TF | 有 `odom -> base_link`、`base_link -> laser` |
| P2 | RViz2 可视化 | 同屏看到 `/scan` 和里程计 |
| P2 | slam_toolbox 低速建图 | 手动遥控能生成初版地图 |

本阶段仍不做：

- WSL2 直连 USB 相机或雷达。
- Nav2 自主导航闭环。
- 相机点云融合。
- 修改 xtark 底盘串口或 `xtark_driver`。
