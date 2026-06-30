# 深度相机 VM 独立试验方案

> 归档说明：这是 VMware + USB 直连深度相机的历史试验方案。当前主线已改为 RK3568 接 USB 传感器，PC / WSL2 通过网络做 ROS2 联调。本文件仅保留参考，不作为当前部署入口。

在 **VMware Ubuntu 22.04** 上，用 **Docker + ROS2 Humble** 驱动 **Orbbec Astra Pro**，完成深度 / 红外 / 彩色三路图像与点云 demo。

工程目录：`~/Desktop/depth_camera_demo/`（含 `docker-compose.yml`、`.env`）。

---

## 1. 硬件与话题

### 1.1 三个光学孔、两路 USB

| 光学 | 数据通路 | USB | ROS2 话题 |
|------|----------|-----|-----------|
| 深度 | OpenNI | `2bc5:0403` | `/camera/depth/image_raw`、`/camera/depth/points` |
| 红外 IR | 同深度模组 | 同上 | `/camera/ir/image_raw` |
| 彩色 RGB | UVC | `2bc5:0502` | `/camera/color/image_raw` |

彩色另对应 VM 内 `/dev/video0`（`v4l2-ctl --list-devices` 可见）。

Launch 成功标志：

```text
depth is started
ir is started
Start UVC camera → device started
```

### 1.2 实测设备（本机）

| 项目 | 值 |
|------|-----|
| 序列号 | `16120710778` |
| 彩色 UVC launch 参数 | `uvc_product_id:=1282`（对应 `0x0502`） |

---

## 2. VM 与 Docker

### 2.1 虚拟机

| 项目 | 值 |
|------|-----|
| 主机名 | `wingsmm-virtual-machine` |
| IP | `192.168.211.129`（以 `hostname -I` 为准） |
| SSH 用户 | `wingsmm` |
| 系统 | Ubuntu 22.04.4 LTS x86_64 |

```powershell
ssh wingsmm@192.168.211.129
```

按提示输入账户密码（勿写入文档或脚本）。

### 2.2 VMware USB

- 控制器建议：**USB 3.1**
- 菜单：**虚拟机 → 可移动设备 → Orbbec**，深度（`0403`）与彩色（`0502`）**都连接到虚拟机**
- 宿主机 USB 直插主板 USB3 口，少用 Hub

### 2.3 Docker 镜像

| 镜像 | 说明 |
|------|------|
| `osrf/ros:humble-desktop-full` | 官方基镜像 |
| `ros-humble-astra:local` | **日常使用**（已 commit，含 libglog 等运行时库） |

```bash
docker images | grep -E 'astra|humble'
```

---

## 3. 一次性环境准备

已完成可跳过。

### 3.1 Windows 导出镜像（可选）

```powershell
docker pull osrf/ros:humble-desktop-full
docker save -o D:\Downloads\work\ros-dev\ros-humble-desktop-full.tar osrf/ros:humble-desktop-full
scp D:\Downloads\work\ros-dev\ros-humble-desktop-full.tar wingsmm@192.168.211.129:~/
```

### 3.2 VM：Docker、Compose、导入镜像

```bash
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# 注销重新登录
docker load -i ~/ros-humble-desktop-full.tar
rm ~/ros-humble-desktop-full.tar   # 可选
```

### 3.3 Compose 工程与 `.env`

```bash
mkdir -p ~/Desktop/depth_camera_demo
cd ~/Desktop/depth_camera_demo
# 历史归档命令：旧 demo 曾从 .env.example 复制 .env；当前 pc/qt_client 不再维护 .env.example。
# cp .env.example .env
# 确认 ROS2_WS=/home/wingsmm/ros2_ws
```

### 3.4 udev 与驱动源码

```bash
sudo apt install -y git build-essential cmake pkg-config \
  libopenni2-dev libusb-1.0-0-dev libudev-dev \
  libgoogle-glog-dev libgflags-dev libeigen3-dev nlohmann-json3-dev libuvc-dev \
  v4l-utils python3-colcon-common-extensions

mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone --depth 1 https://github.com/orbbec/ros2_astra_camera.git
cd ~/ros2_ws/src/ros2_astra_camera/astra_camera/scripts
sudo bash install.sh
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 3.5 编译驱动并保存镜像

```bash
cd ~/Desktop/depth_camera_demo
docker compose --profile build run --rm build
```

或手工进 `osrf/ros:humble-desktop-full` 容器执行 `colcon build`（见旧流程）。

保存自定义镜像：

```bash
docker ps
docker commit <容器ID> ros-humble-astra:local
```

---

## 4. 日常启动（Docker Compose）

**在 VM 的 Ubuntu 里执行**（不是 Windows，也不是容器里再跑 docker）。

```bash
lsusb | grep -i orbbec
cd ~/Desktop/depth_camera_demo
docker compose up -d astra-camera
docker compose logs -f astra-camera
```

| 命令 | 作用 |
|------|------|
| `docker compose up -d astra-camera` | 后台启动相机 |
| `docker compose logs -f astra-camera` | 看日志 |
| `docker compose down` | 停止 |
| `docker compose run --rm cli` | 进 shell 测话题（已自动 source 工作空间） |
| `docker compose --profile rviz run --rm rviz` | RViz2 |
| `docker compose --profile build run --rm build` | 重新 colcon 编译 |

`.env` 常用项：

| 变量 | 说明 |
|------|------|
| `ROS2_WS` | 工作空间绝对路径 |
| `UVC_PRODUCT_ID=1282` | FHD 彩色 `0x0502` |
| `USE_UVC=false` | 仅深度+红外，不启 UVC |

---

## 5. 验证 ROS2 话题

相机容器保持运行，另开终端：

```bash
cd ~/Desktop/depth_camera_demo
docker compose run --rm cli
```

容器内直接测话题（已自动 source 工作空间）：

```bash
ros2 topic list | grep camera
ros2 topic info /camera/depth/image_raw -v    # Publisher count: 1
ros2 topic hz /camera/depth/image_raw         # 等 10～15 秒
ros2 topic hz /camera/ir/image_raw
ros2 topic hz /camera/color/image_raw         # 彩色可能很慢，多等 30 秒
```

也可在相机容器内测（无需 cli）：

```bash
docker exec -it astra-camera bash
source /opt/ros/humble/setup.bash
source /ros2_ws/install/setup.bash
ros2 topic hz /camera/depth/image_raw
```

### 5.1 话题一览

| 话题 | 用途 |
|------|------|
| `/camera/depth/image_raw` | 深度图 |
| `/camera/depth/points` | 点云 |
| `/camera/ir/image_raw` | 红外 |
| `/camera/color/image_raw` | 彩色 |
| `/tf`、`/tf_static` | 坐标系 |

---

## 6. RViz2 预览

VM **图形桌面**终端：

```bash
xhost +local:
cd ~/Desktop/depth_camera_demo
docker compose --profile rviz run --rm rviz
```

Add → By topic：

| 类型 | 话题 | Fixed Frame |
|------|------|-------------|
| Image | `/camera/depth/image_raw` | `camera_depth_optical_frame`（勾选 Normalize Range） |
| Image | `/camera/ir/image_raw` | `camera_ir_optical_frame` |
| Image | `/camera/color/image_raw` | `camera_color_optical_frame` |
| PointCloud2 | `/camera/depth/points` | `camera_depth_optical_frame` |

**Topic 显示 OK 但窗口 “No Image”：**

- Fixed Frame 改为上表中的 optical_frame
- 彩色帧率在 Docker 下可能极低，先看深度图
- `astra-camera` 必须保持运行

---

## 7. VM 内原生预览彩色（v4l2，不经 ROS）

用于确认 **UVC 硬件 / VMware USB** 是否正常。与 Docker **互斥占用** `/dev/video0`。

```bash
cd ~/Desktop/depth_camera_demo
docker compose stop astra-camera
```

若 `/dev/video0` 不存在，重载驱动：

```bash
sudo modprobe -r uvcvideo
sudo modprobe uvcvideo
v4l2-ctl --list-devices
```

**命令行抓流（实测约 21～23 fps）：**

```bash
v4l2-ctl -d /dev/video0 --set-fmt-video=width=640,height=480,pixelformat=MJPG
v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=60 --stream-to=/tmp/astra_test.mjpg
ls -lh /tmp/astra_test.mjpg
```

**图形预览：**

```bash
sudo apt install -y guvcview
guvcview -d /dev/video0
```

测完恢复 ROS：

```bash
pkill guvcview
docker compose up -d astra-camera
```

深度 / 红外 **不能** 用 v4l2 预览，只能走 ROS（上一节）。

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| `docker compose ps` 报 no configuration file | 先 `cd ~/Desktop/depth_camera_demo` |
| 在容器里执行 `docker` 报 command not found | `exit` 回到 VM 再执行 compose |
| `libglog.so.0` 缺失 | 使用 `ros-humble-astra:local` |
| UVC 默认 `0501` 失败 | `.env` 中 `UVC_PRODUCT_ID=1282` |
| 停容器后无 `/dev/video0` | `sudo modprobe -r uvcvideo && sudo modprobe uvcvideo` |
| v4l2 流畅、ROS 彩色极慢 | VMware + Docker 双占用 UVC；可 `USE_UVC=false` 或只用 v4l2 测彩色 |
| Docker 下深度约 2～3 Hz | VM 透传性能限制，属常见现象 |
| RViz Fixed Frame 警告 | 改为 `camera_*_optical_frame` |
| `install.sh` 找不到 | 路径为 `astra_camera/scripts/install.sh` |

日志中 `unsupported descriptor subtype`、`attempt to claim already-claimed interface` 在 VMware 上常见，出现 **`device started`** 后一般可继续用。

---

## 9. 参考

- Orbbec ROS2 驱动：<https://github.com/orbbec/ros2_astra_camera>
- ROS2 Humble 镜像：`osrf/ros:humble-desktop-full`
- Compose 文件：`depth_camera_demo/docker-compose.yml`（VM 上为 `~/Desktop/depth_camera_demo/docker-compose.yml`）

---

**文档版本：** 2026-06-03，VM 实机验证（`ros-humble-astra:local`，序列号 `16120710778`）。
