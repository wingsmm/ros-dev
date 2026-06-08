# xtark WSL2 联调客户端

`qt_client` 是 WSL2 统一栈的日常入口。它同时承担两个角色：

- GUI 程序：连接、状态显示、遥控、建图栈启停。
- ROS 网关：把 xtark TCP JSON 转成 ROS2 topic / TF，并接入 RK3568 `/scan` 给 slam_toolbox。

## 依赖

```bash
cd /mnt/d/wingsmm/Desktop/other/pc/qt_client
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`rclpy` 来自 WSL2 系统 ROS2，不由 venv 安装：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
```

建图栈依赖：

```bash
sudo apt-get install -y ros-humble-rviz2 ros-humble-slam-toolbox
```

## 启动

```bash
cd /mnt/d/wingsmm/Desktop/other/pc/qt_client
./run.sh
```

仅验证 JSON / GUI，不发布 ROS2：

```bash
./run.sh --no-ros
```

`run.sh` 会自动激活 venv、加载 ROS2 Humble，并设置 `ROS_DOMAIN_ID=0`。

## 使用流程

1. 启动 `./run.sh`。
2. 在 GUI 中连接 `192.168.1.169:8765`。
3. 确认状态区出现 `base_status` 和 `odom_base`。
4. 启动建图栈前，另开 WSL2 终端检查：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0

ros2 topic hz /scan
ros2 topic hz /odom_base
ros2 topic echo /base_status --once
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_ros tf2_echo base_link laser
```

5. 检查通过后，在 GUI 中启动 RViz2 / SLAM。
6. 真机低速小范围移动，先验证 `/map`、TF 和雷达方向。

## 当前验收状态

- RK3568 `/scan` 到 WSL2：约 14 到 15 Hz，`frame_id=laser`
- xtark JSON：`192.168.1.169:8765` 可连接
- `/odom_base`：约 11 到 12 Hz，来自 JSON `odom_base`
- `/base_status`：约 2 Hz
- TF：`odom -> base_link` 动态发布，`base_link -> laser` 静态发布
- 建图依赖：RViz2 / slam_toolbox 已安装

注意：跨设备 `/scan` 时间戳存在百毫秒级偏差和偶发抖动。当前不阻断低速试建图；如果 SLAM 持续丢帧，再调整 slam_toolbox 参数或增加 `/scan` 重打时间戳 relay。

## 目录

```text
qt_client/
├── app.py
├── run.sh
├── gateway/
│   ├── json_client.py      # TCP NDJSON client: xtark <-> GUI
│   └── ros2_pub.py         # JSON feedback -> /odom_base, /base_status, TF
├── mapping/
│   └── ros_stack.py        # RViz2 / slam_toolbox process manager
├── ui/
│   ├── fonts.py
│   └── widgets/
│       ├── control_panel.py
│       ├── stack_panel.py
│       ├── status_panel.py
│       └── log_panel.py
├── config/
│   └── slam_toolbox_xtark.yaml
└── logs/
```
