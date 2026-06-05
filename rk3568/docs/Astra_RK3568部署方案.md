# 深度相机 RK3568 试验方案报告

## 1. 结论

本方案在 RK3568 实机上使用 Docker + ROS2 Humble 驱动 Orbbec Astra Pro 深度相机，输出深度、红外、彩色图像和点云话题。2026-06-03 实机复核结果表明：相机已被 RK3568 识别，`astra-camera` 容器正在运行，ROS2 话题发布正常，深度与红外接近 30 Hz，彩色约 24 Hz，满足当前深度相机试验要求。

当前建议状态：

| 项目 | 结论 |
|------|------|
| 板端系统 | Ubuntu 20.04.6 LTS，aarch64，内核 4.19.193 |
| Docker | Docker 26.1.3，Compose 2.27.1，服务 active |
| Docker 存储驱动 | `vfs` |
| 内存与 swap | 3.8 GiB RAM，2 GiB swap 已启用 |
| 相机识别 | `2bc5:0403` 深度/红外，`2bc5:0502` 彩色 UVC |
| ROS2 容器 | `astra-camera` 已运行，镜像 `ros-humble-astra:deps` |
| 验收结果 | 深度 29.19 Hz，红外 29.71 Hz，彩色 24.02 Hz |

密码、私钥等登录凭据不写入本文档。

## 2. 实机环境

### 2.1 主机信息

| 项目 | 实测值 |
|------|--------|
| 主机名 | `rk356x` |
| SSH 地址 | `marvsmart@192.168.1.163` |
| 系统 | Ubuntu 20.04.6 LTS |
| 架构 | `aarch64` |
| 内核 | `4.19.193` |
| 运行时长 | 2026-06-03 17:37 复核时已运行约 2 小时 |
| 根分区 | 29 GiB，总使用约 70%，剩余约 8.3 GiB |

基础检查命令：

```bash
hostname
uname -a
cat /etc/os-release
free -h
swapon --show
df -h / /userdata /var/lib/docker
```

### 2.2 Docker 环境

| 项目 | 实测值 |
|------|--------|
| Docker | `Docker version 26.1.3` |
| Docker Compose | `Docker Compose version 2.27.1` |
| 服务状态 | `active` |
| 存储驱动 | `vfs` |
| Cgroup driver | `cgroupfs` |

当前镜像：

| 镜像 | 大小 | 用途 |
|------|------|------|
| `ros:humble-ros-base-jammy` | 720 MB | ROS2 Humble arm64 基础镜像 |
| `ros:humble-ros-base-jammy-arm64` | 720 MB | 基础镜像 load 后保留标签 |
| `ros-humble-astra:deps` | 1.56 GB | 已安装相机编译和运行依赖的运行镜像 |

当前容器：

| 容器 | 状态 | 镜像 |
|------|------|------|
| `astra-camera` | Up | `ros-humble-astra:deps` |

## 3. 硬件枚举

### 3.1 USB 拓扑

RK3568 当前识别到 Astra Pro 的两个 USB 设备：

| USB ID | 说明 | 当前总线 |
|--------|------|----------|
| `2bc5:0403` | Astra 深度/红外 OpenNI 设备 | Bus 5 |
| `2bc5:0502` | Astra 彩色 UVC 设备 | Bus 5 |

实测 USB 树：

```text
Bus 06: USB3 root hub，当前无下游设备
Bus 05: USB2 xhci root hub，480M
  Genesys Logic 4-port hub
    2bc5:0403  Astra 深度/红外
    2bc5:0502  Astra 彩色 UVC

Bus 02: USB2 ehci root hub，480M
  Realtek WiFi/BT
  1a86:7523 QinHeng CH341 串口，/dev/ttyUSB0
```

检查命令：

```bash
lsusb
lsusb -t
ls -l /dev/bus/usb/005/*
```

### 3.2 视频与串口节点

宿主机当前 `v4l2-ctl --list-devices` 只列出板载 RKISP：

| 设备 | 节点 |
|------|------|
| `rkisp_mainpath` | `/dev/video0` 到 `/dev/video6` |
| `rkisp-statistics` | `/dev/video7`、`/dev/video8` |
| media | `/dev/media0` |
| CH341 串口 | `/dev/ttyUSB0` |

注意：当前 ROS2 彩色图像发布正常，但宿主机未枚举出 Astra 的 `/dev/video9`、`/dev/video10`。容器日志显示彩色相机实际通过 libuvc 打开 `2bc5:0502`，容器内可见 `/dev/bus/usb/005/005` 与 `/dev/bus/usb/005/006`。因此，重建容器前应先复核 `/dev/video9`、`/dev/video10` 是否存在；若不存在，应优先保留现有容器并使用 `docker compose stop/start`，避免不必要的 `down` 后重建。

## 4. 板端工程结构

### 4.1 目录

| 路径 | 内容 |
|------|------|
| `~/sensor_stack/` | Compose 工程、`.env`、测试脚本、配置、日志、数据目录 |
| `~/ros2_ws/src/ros2_astra_camera/` | Astra ROS2 驱动源码 |
| `~/ros2_ws/build/` | colcon 编译中间产物 |
| `~/ros2_ws/install/` | 容器运行时 source 的安装产物 |

当前 `~/sensor_stack/.env`：

```bash
BASE_IMAGE=ros:humble-ros-base-jammy
DEPS_IMAGE=ros-humble-astra:deps
ASTRA_IMAGE=ros-humble-astra:deps

ROS2_WS=/home/marvsmart/ros2_ws
UVC_PRODUCT_ID=1282
USE_UVC=true
VIDEO0=/dev/video9
VIDEO1=/dev/video10
MEDIA0=/dev/media0
ENABLE_LIDAR=true
LIDAR_SERIAL=/host_dev/ttyUSB0
LIDAR_WAIT_SECONDS=30
SENSOR_LOG_DIR=/var/log/sensor_stack
```

### 4.2 Compose 运行模型

`astra-camera` 服务采用以下方式运行：

| 配置 | 作用 |
|------|------|
| `network_mode: host` | ROS2 DDS 使用宿主机网络 |
| `pid: host`、`ipc: host` | 降低容器隔离导致的设备和共享内存问题 |
| `privileged: true` | 允许访问 USB、video、media 设备 |
| `/dev/bus/usb:/dev/bus/usb` | Astra 深度、红外、UVC 的主要访问路径 |
| `/dev:/host_dev` | RPLidar 串口热枚举访问路径 |
| `~/ros2_ws:/ros2_ws` | 源码编译产物挂载进容器 |
| `tmpfs: /dev/mqueue` | 避免 mqueue 挂载错误 |
| `pull_policy: never` | 禁止运行时从公网拉镜像 |

容器启动命令：

```bash
source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash
ros2 launch astra_camera astra_pro.launch.xml uvc_product_id:=1282
```

## 5. 部署与运行流程

### 5.1 基础镜像

基础镜像只需在板端 load 一次：

```bash
docker load -i ~/ros-humble-ros-base-jammy-arm64.tar
docker tag ros:humble-ros-base-jammy-arm64 ros:humble-ros-base-jammy
docker images | grep humble
```

### 5.2 依赖镜像

依赖镜像 `ros-humble-astra:deps` 已存在。只有在基础镜像、依赖包或系统重装后才需要重做：

```bash
cd ~/sensor_stack
docker compose --profile deps run --rm=false --name astra-deps-once deps-install
docker commit astra-deps-once ros-humble-astra:deps
docker rm astra-deps-once
```

### 5.3 编译驱动

编译产物保存在宿主机 `~/ros2_ws`，容器重建不应删除该目录：

```bash
cd ~/sensor_stack
docker compose --profile build run --rm build
```

编译前检查：

```bash
docker images | grep ros-humble-astra
free -h
swapon --show
ls ~/ros2_ws/src/ros2_astra_camera/astra_camera/package.xml
```

成功标志：

```text
Finished <<< astra_camera
Summary: 2 packages finished
```

### 5.4 启动相机

日常启动：

```bash
cd ~/sensor_stack
docker compose up -d astra-camera
docker compose logs -f astra-camera
```

日常停止和恢复优先使用：

```bash
docker compose stop astra-camera
docker compose start astra-camera
```

由于 Docker 当前使用 `vfs`，容器重建会比较慢。非必要不要频繁执行 `docker compose down` 后再 `up`。

## 6. 验收结果

### 6.1 容器启动日志

2026-06-03 实测日志关键行：

```text
Found 1 devices
Trying to open device: 2bc5/0403@5/5
Device connected: Astra serial number: 16120710778
set depth video mode Resolution :640x480@30Hz
set ir video mode Resolution :640x480@30Hz
uvc config: vendor_id: 2bc5, product_id: 502, width: 640, height: 480, fps: 30
open camera success
depth is started
ir is started
Start UVC camera
set uvc mode 640x480@30 format UVC_FRAME_FORMAT_MJPEG
device  started.
```

日志中偶发以下信息时，只要后续出现 `device started` 且话题正常发布，可作为可接受现象处理：

```text
unsupported descriptor subtype VS_COLORFORMAT
attempt to claim already-claimed interface 1
Corrupt JPEG data: ... extraneous bytes before marker 0xd9
```

### 6.2 ROS2 话题

当前容器内已发布话题：

```text
/camera/color/camera_info
/camera/color/image_raw
/camera/depth/camera_info
/camera/depth/image_raw
/camera/depth/points
/camera/ir/camera_info
/camera/ir/image_raw
```

验收命令：

```bash
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  ros2 topic list | grep camera
  ros2 topic hz /camera/depth/image_raw
  ros2 topic hz /camera/ir/image_raw
  ros2 topic hz /camera/color/image_raw
  ros2 topic bw /camera/depth/image_raw
'
```

### 6.3 性能数据

2026-06-03 实测：

| 数据流 | 分辨率/格式 | 实测 |
|--------|-------------|------|
| 深度 | 640x480，30 Hz 配置 | 29.19 Hz |
| 红外 | 640x480，30 Hz 配置 | 29.71 Hz |
| 彩色 | 640x480，MJPEG，30 Hz 配置 | 24.02 Hz |
| 深度带宽 | ROS2 `/camera/depth/image_raw` | 约 18 MB/s |
| 点云 | `/camera/depth/points` | 已发布 |

判定：深度、红外达到接近 30 Hz；彩色 UVC 能稳定发布，帧率低于配置值但满足当前联调观察和数据采集需求。

## 7. 运维注意事项

| 风险 | 处理 |
|------|------|
| `vfs` 导致容器 Creating 时间长 | 日常使用 `stop/start`，避免频繁 `down/up` |
| `/dev/video9`、`/dev/video10` 当前未在宿主机枚举 | 重建容器前先 `ls -l /dev/video9 /dev/video10`；若不存在，不要贸然重建 |
| `ros-humble-astra:deps` 丢失 | 重新执行 deps 容器并 commit |
| build 卡住或 SSH 变慢 | 检查 swap；当前 2 GiB swap 已启用 |
| Docker pull 超时 | 当前 Compose 配置为 `pull_policy: never`，应使用本地镜像 |
| UVC 彩色不发布 | 确认 `USE_UVC=true`、`UVC_PRODUCT_ID=1282`，并检查 `/dev/bus/usb` 挂载 |
| 只需要深度/红外 | 可临时以 `use_uvc_camera:=false` 启动，降低彩色链路影响 |
| 点云占用资源 | 可按需关闭 `enable_point_cloud`，保留深度图像 |

## 8. 推荐后续动作

1. 保持当前 `astra-camera` 容器运行状态，不做无必要重建。
2. 若需要重启服务，优先执行 `docker compose stop astra-camera` 和 `docker compose start astra-camera`。
3. 若必须 `down/up` 重建容器，先确认 `/dev/video9`、`/dev/video10` 是否存在；若不存在，应先调整 Compose 设备映射，只依赖 `/dev/bus/usb` 与必要的 `/dev/media0`。
4. 将验收命令固化为现场测试流程：USB 枚举、容器日志、话题列表、深度/红外/彩色频率、深度带宽。
5. 若后续要长期运行，建议持续观察根分区空间；当前剩余约 8.3 GiB，镜像和 colcon 产物继续增长时需要清理无用镜像与日志。

## 9. 现场核查清单

```bash
# 1. 系统与资源
hostname
uname -a
free -h
swapon --show
df -h /

# 2. USB 与设备
lsusb | grep 2bc5
lsusb -t
ls -l /dev/bus/usb/005/*
v4l2-ctl --list-devices

# 3. Docker 状态
docker --version
docker compose version
systemctl is-active docker
docker images
docker ps -a

# 4. 相机容器
cd ~/sensor_stack
docker compose logs astra-camera | tail -80
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  ros2 topic list | grep camera
'

# 5. 性能验收
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  timeout 12 ros2 topic hz /camera/depth/image_raw
  timeout 12 ros2 topic hz /camera/ir/image_raw
  timeout 15 ros2 topic hz /camera/color/image_raw
  timeout 8 ros2 topic bw /camera/depth/image_raw
'
```

**后续：** 同板 RPLidar 部署见 `rk3568/docs/RPLidar_RK3568部署方案.md`。

**文档版本：** 2026-06-03  
**当前状态：** RK3568 实机深度相机 ROS2 发布正常，深度/红外接近 30 Hz，彩色约 24 Hz。
