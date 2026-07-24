# WSL2 统一栈运行与调试

## 1. 当前结论

技术路线已经跑通，建图前的软件和硬件链路具备条件：

```text
RK3568 -> WSL2   /scan
xtark  -> WSL2   JSON cmd_vel / base_status / odom_base
WSL2   -> GUI    qt_client
WSL2   -> ROS2   /odom_base /base_status + TF
WSL2   -> 建图   RViz2 / slam_toolbox
```

当前阶段可以暂告一段落。下一步不再继续调整架构，而是进行真机低速试建图：

```text
先小范围、低速度验证 /scan + odom + TF + map
若 SLAM 持续丢帧，再调整时间戳、TF 或 slam_toolbox 参数
```

## 2. 统一架构

```text
RK3568
  astra-camera Docker 容器
  ├── sllidar_ros2 -> /scan
  └── astra_camera -> /camera/*

xtark
  xtark_driver
  └── xtark_json_bridge -> TCP 0.0.0.0:8765

WSL2 + ROS2 Humble + WSLg
  pc/qt_client
  ├── 连接 xtark JSON
  ├── 发布 /odom_base
  ├── 发布 /base_status
  ├── 发布 TF odom -> base_link
  ├── 发布静态 TF base_link -> laser
  └── 启停 RViz2 / slam_toolbox
```

原则：

- `pc/qt_client` 在 WSL2 下运行，是日常唯一入口。
- WSL2 ROS2 使用 apt 原生安装，不用 WSL2 Docker 做跨机 DDS 联调。
- RK3568 继续使用 Docker，因为 USB 传感器在 RK 本机。
- xtark 本机雷达可以忽略，建图使用 RK3568 `/scan`。
- 不把 Qt GUI 放回 Windows 原生运行，避免 Windows / WSL2 两套环境分裂。

## 3. 启动顺序

### 3.1 RK3568

RK 侧 `astra-camera` 容器已配置 `restart: unless-stopped`，Docker 服务启动后会自动拉起容器。确认：

```bash
docker ps
docker logs astra-camera --tail 80
```

容器内确认 `/scan`：

```bash
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  export ROS_DOMAIN_ID=0
  ros2 topic info /scan
  timeout 8 ros2 topic hz /scan
  timeout 5 ros2 topic echo /scan --once | grep frame_id
'
```

当前验收：

```text
/scan 有 1 个 publisher
频率约 14 到 15 Hz
frame_id: laser
```

### 3.2 xtark

启动脚本已放在小车：

```bash
~/ros_ws/scripts/json_stack.sh
```

常用命令：

```bash
~/ros_ws/scripts/json_stack.sh start
~/ros_ws/scripts/json_stack.sh status
~/ros_ws/scripts/json_stack.sh stop
```

`logs` 会持续跟随日志：

```bash
~/ros_ws/scripts/json_stack.sh logs
```

当前验收：

```text
xtark_bringup.launch 正在运行
json_base_adapter.launch 正在运行
json_base_adapter_node.py 正在运行
TCP 0.0.0.0:8765 正在监听
/odom 约 23 Hz
```

注意：`bringup.log` 中可能有 xtark 本机 `/dev/lidar` 绑定失败。当前建图使用 RK `/scan`，这条日志不影响统一栈。

### 3.3 WSL2 / qt_client

启动：

```bash
cd /mnt/d/Downloads/work/ros-dev/pc/qt_client
./run.sh
```

仅验证 JSON / GUI：

```bash
./run.sh --no-ros
```

`run.sh` 会加载 venv、ROS2 Humble，并设置 `ROS_DOMAIN_ID=0`。

GUI 中连接：

```text
192.168.1.168:8765
```

## 4. 建图前检查

另开 WSL2 终端：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
```

检查 topic：

```bash
ros2 topic hz /scan
ros2 topic hz /odom_base
ros2 topic echo /base_status --once
```

检查 TF：

```bash
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_ros tf2_echo base_link laser
```

检查 scan frame：

```bash
ros2 topic echo /scan --once | grep frame_id
```

当前裸链路验收值：

| 项 | 结果 |
|----|------|
| `/scan` | 约 14 到 15 Hz |
| `/scan.header.frame_id` | `laser` |
| `/odom_base` | 约 11 到 12 Hz |
| `/base_status` | 约 2 Hz |
| `odom -> base_link` | 可查 |
| `base_link -> laser` | 可查 |
| RViz2 / slam_toolbox | 已安装 |

时间戳说明：

- `/scan` 由 RK 发布，`/odom_base` 和 TF 由 WSL2 根据 xtark JSON 发布。
- 跨设备时间戳存在百毫秒级偏差和偶发抖动。
- 当前不阻断低速试建图。
- 如果 SLAM 日志持续出现 message filter 丢帧，再考虑调整 `transform_timeout` 或增加 `/scan` 重打时间戳 relay。

## 5. GUI 建图流程

1. 启动 `./run.sh`。
2. 点击连接，连接 xtark `192.168.1.168:8765`。
3. 确认状态区有 `base_status` 和 `odom_base`。
4. 完成第 4 节检查。
5. 点击一键启动建图栈，启动 RViz2 和 SLAM。
6. 真机低速测试：

```text
先原地小角度转 10 到 20 度
再前进 0.5 到 1 米
停住观察 /map
再慢慢转回或后退
```

7. SLAM 运行中、RViz 里 `/map` 已有内容时，在 GUI 点击「保存地图」（输出到 `pc/qt_client/maps/`）。
8. 结束时先全部停止，再断开并关闭窗口。

建图时重点观察：

- RViz 中 `/scan`、TF、map 是否方向一致。
- `/map` 是否稳定生成。
- SLAM 日志是否持续大量丢帧。
- 运动时 `/odom_base` 的 `x/y/yaw` 是否连续变化。

## 6. 常见警告

### 6.1 WSLg / Qt 警告

类似：

```text
QStandardPaths: wrong permissions on runtime directory
Dropped Escape call with ulEscapeCode
```

通常不影响运行。只要 GUI 没退出、RViz2 能弹窗，可以先忽略。

### 6.2 SLAM message filter 丢帧

类似：

```text
Message Filter dropping message: frame 'laser' ... queue is full
```

含义：

```text
SLAM 收到 /scan，但等待 TF / 时间关系时被堵住。
```

优先检查：

```bash
ros2 topic hz /scan
ros2 topic hz /odom_base
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_ros tf2_echo base_link laser
```

重点看：

- `/scan.header.frame_id` 是否为 `laser`
- `base_link -> laser` 是否存在
- `odom -> base_link` 是否连续
- `/odom_base` 是否在车运动时连续刷新

如果只是偶发丢帧，先继续低速测试。如果持续丢帧，再调整 `pc/qt_client/config/slam_toolbox_xtark.yaml`。

### 6.3 slam_toolbox 找不到

```bash
sudo apt install ros-humble-slam-toolbox
```

### 6.3.1 存图失败

```bash
sudo apt install ros-humble-nav2-map-server
```

确认 SLAM 在跑且 `/map` 有数据后再点「保存地图」。

### 6.4 RViz2 找不到

```bash
sudo apt install ros-humble-rviz2
```

## 7. GUI 导航流程

前提：已完成建图并存入 `pc/qt_client/maps/*.yaml`。

1. 连接 xtark，确认 `/scan`、`/odom`（由 JSON 桥发布）正常。
2. 在 GUI「导航栈」选择地图 yaml，点击「一键启动导航栈」。
3. RViz2 中 **2D Goal Pose** 设目标；Nav2 经 `/cmd_vel` → JSON 驱动底盘。
4. 导航中禁用手动遥控；**急停** / `K` / 空格取消导航并停车。
5. 结束点「停止导航栈」。

依赖：

```bash
sudo apt install ros-humble-nav2-bringup
```

参数：`pc/qt_client/config/nav2_xtark.yaml`（麦轮低速、/scan costmap）。

## 8. 仍待真机联调

- WSL2 直连 USB 传感器
- 相机点云融合
- 修改 xtark 底盘串口或 `xtark_driver`
- `/scan` 与 JSON 里程计时间戳精细对齐（AMCL 更敏感）
- `base_link -> laser` 外参实测
