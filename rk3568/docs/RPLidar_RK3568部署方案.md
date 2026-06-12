# RPLidar RK3568 部署方案

在 **RK3568（aarch64）** 上部署从 xtark 拆下的 **思岚 RPLidar XAS**（USB 转串口 **CH341 `1a86:7523`**），输出 ROS2 **`/scan`**，与已验收的深度相机 **并行采集**（相机见 `Astra_RK3568部署方案.md`）。

| 板子路径 | 内容 |
|----------|------|
| `~/ros2_ws/src/sllidar_ros2/` | 雷达驱动（待克隆） |
| `~/ros2_ws/install/` | 与 Astra 共用 colcon 产物（可选） |
| `/etc/udev/rules.d/99-lidar.rules` | 固定 `/dev/lidar` |

---

## 快速开始（进度）

| 步骤 | 状态 | 说明 |
|------|------|------|
| USB 识别 `1a86:7523` | **已完成** | 两个 CH341，Bus 2 |
| 确认 `ttyUSB` → 雷达 | **已完成** | udev：`/dev/lidar` → `ttyUSB0`（Hub `2-1.3`） |
| udev → `/dev/lidar` | **已完成** | `rk3568/deploy/sensor_stack/config/99-lidar.rules` |
| 源码 + colcon | **已完成** | 本机 tar；`build-lidar`；`sllidar_node` 在 install |
| install 备份 | **已完成** | `~/ros2_ws_install_backup_before_lidar.tar.gz` |
| 发布 `/scan` 并测 `hz` | **已完成** | `/dev/ttyUSB0`，~**14.3 Hz**；见 §6.4 |
| 与 `astra-camera` 同时运行 | **已完成** | `start_sensors.sh` 同容器并行 |

**板子 SSH：** `marvsmart@192.168.1.163`（凭据不写本文档）。

---

## 1. 硬件与拓扑

### 1.1 雷达型号（xtark 对照）

| 项目 | xtark (ROS1) | RK3568（本方案） |
|------|----------------|------------------|
| 型号 | RPLidar **XAS** | 同硬件 |
| USB | QinHeng HL-340 `1a86:7523` | 同 |
| xtark 节点 | `/dev/lidar` → `ttyUSB0` | 本板需自建 udev |
| 驱动 | `rplidar_ros` (Melodic) | **`sllidar_ros2`** (Humble) |
| 话题 | `/scan_raw` → `/scan` | 默认 **`/scan`** |

### 1.2 与深度相机共存

2026-06-03 实机 USB 树（相机已验收时）：

```text
Bus 05  Astra 2bc5:0403 + 2bc5:0502
Bus 02  CH341 1a86:7523 → /dev/ttyUSB0（雷达口，以拔插实测为准）
```

两路 **不同 USB 控制器**，可同时插线；2D 雷达带宽远小于深度流，**不与相机争同一总线**。

---

## 2. 硬件检查（阶段 A：宿主机）

**勿与占用串口的进程同时测。** 深度相机容器可不占 `ttyUSB`。

```bash
lsusb | grep 1a86
# 期望：1a86:7523 QinHeng Electronics HL-340 USB-Serial adapter

ls -l /dev/ttyUSB*
lsusb -t | grep -A2 "1a86"
```

若 **两个** `ttyUSB`（载板可能多一路 CH341）：只拔雷达 USB，看消失的节点即为雷达。

---

## 3. 确认串口（必做）

```bash
# 记录拔插前后
ls /dev/ttyUSB*
```

记下雷达对应设备，例如 `/dev/ttyUSB0`。下文 udev 按实测 **Hub port / devpath** 写死。

查看稳定路径（示例）：

```bash
udevadm info -q property -n /dev/ttyUSB0 | grep -E 'ID_PATH|ID_SERIAL'
```

---

## 4. udev 固定 `/dev/lidar`

将 `devpath` 换成你板上雷达所在 Hub 口（`1.3` 或 `1.4` 等，以 `udevadm` 为准）：

```bash
sudo tee /etc/udev/rules.d/99-lidar.rules <<'EOF'
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", ATTRS{devpath}=="1.4", SYMLINK+="lidar", GROUP="dialout", MODE="0666"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
ls -l /dev/lidar
```

用户加入串口组（重登生效）：

```bash
sudo usermod -aG dialout $USER
```

---

## 5. 安装 ROS2 驱动（sllidar_ros2）

### 5.0 必读：容器、编译产物、备份（避免误操作）

| 概念 | 实际行为 |
|------|----------|
| `~/ros2_ws` **挂载**进容器 | `build/`、`install/`、`src/` 在 **宿主机**，不随容器删除 |
| `docker compose run --rm build` | **`--rm` 只删容器实例**，不删宿主机 `install/astra_camera` |
| **`build` 服务（无 packages-select）** | 会 **重编整个工作空间**（含 `astra_camera`，约 30min）—— **加雷达时不要用** |
| **`build-lidar` 服务** | 仅 `colcon build --packages-select sllidar_ros2`，**不重编相机** |
| `docker compose up astra-camera` | **vfs** 下会 **新建容器**（慢）；与 colcon 无关 |
| `ros-humble-astra:deps` 镜像 | **commit 一次** 后复用；勿重复 `deps-install`+commit |

**编译前备份（强烈建议）：**

```bash
tar -czf ~/ros2_ws_install_backup_$(date +%Y%m%d_%H%M).tar.gz -C ~/ros2_ws install
ls -lh ~/ros2_ws_install_backup_*.tar.gz
```

恢复示例：`rm -rf ~/ros2_ws/install && tar -xzf ~/ros2_ws_install_backup_xxxx.tar.gz -C ~/ros2_ws`

### 5.1 获取源码（开发机下载 → 拷板，勿在板子 git clone）

开发机（仓库内已可打包）：

```bash
# 已有 rk3568/deploy/src/sllidar_ros2 时：
cd rk3568 && tar -czf sllidar_ros2.tar.gz -C deploy/src sllidar_ros2
scp sllidar_ros2.tar.gz marvsmart@192.168.1.163:~/
```

板子解压：

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
rm -rf sllidar_ros2
tar -xzf ~/sllidar_ros2.tar.gz
ls sllidar_ros2/package.xml
```

### 5.2 编译（只用 `build-lidar`，勿用全量 `build`）

```bash
# 1. 备份
tar -czf ~/ros2_ws_install_backup_$(date +%Y%m%d_%H%M).tar.gz -C ~/ros2_ws install

# 2. 仅编雷达（compose 需含 build-lidar 服务，见 deploy/sensor_stack/docker-compose.yml）
cd ~/sensor_stack
docker compose --profile build-lidar run --rm build-lidar
ls ~/ros2_ws/install/sllidar_ros2
ls ~/ros2_ws/install/astra_camera/lib/astra_camera/astra_camera_node   # 应仍在
```

**勿执行：** `docker compose --profile build run --rm build`（除非你要重编相机）。

### 5.3 依赖

`sllidar_ros2` 依赖 `rclcpp`、`sensor_msgs` 等，**`ros-humble-ros-base` / deps 镜像通常已满足**。若缺包，在 deps 容器内 `apt install ros-humble-sllidar-ros2`（若源里有）或按包 `package.xml` 补装。

---

## 6. 启动与验收

### 6.1 推荐：复用已有 `astra-camera` 容器（快，勿 `docker run`）

**慢的原因：** 本板 Docker 用 **vfs**，每次 `docker run` / `docker compose run` 都会 **新建容器**（拷贝 ~1.56GB 镜像层，约 **5～10 分钟**），**不是**重新编译、也不是首次 apt。  
**快的方式：** `docker compose start astra-camera`（**秒级**，复用 18h 前已建好的容器）。

容器通过 `/dev:/host_dev` 挂载读取宿主机设备，雷达串口使用 **`/host_dev/ttyUSB0`**。这样即使容器早于 USB 串口枚举启动，后续出现的串口也能被容器看到。

```bash
cd ~/sensor_stack
docker compose start astra-camera

docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  nohup ros2 launch sllidar_ros2 sllidar_a1_launch.py serial_port:=/host_dev/ttyUSB0 frame_id:=laser \
    > /tmp/lidar.log 2>&1 &
  sleep 12
  timeout 16 ros2 topic hz /scan
'
```

失败时先在宿主机确认实际串口，再换 `serial_port:=/host_dev/ttyUSB1`。勿对每个测试都 `docker run` 新容器。

### 6.2 一键脚本（宿主机有 ROS 时）

`deploy/sensor_stack/scripts/test_lidar_acceptance.sh` — 仅当板子已装 `/opt/ros/humble` 时使用；否则用 §6.1。

### 6.3 手动 launch

**通过标准：** `/scan` 有数据，`ranges` 非空，`frame_id` 正常（如 `laser`），无持续 `open port failed`。

### 6.4 2026-06-04 实机验收

| 项目 | 结果 |
|------|------|
| 串口 | 宿主机 **`/dev/ttyUSB0`**；容器内通过 **`/host_dev/ttyUSB0`** 访问 |
| Launch | `sllidar_a1_launch.py` |
| 健康 | `SLLidar health status : OK` |
| 固件 | 1.29，Hardware Rev 7 |
| 模式 | Sensitivity，标称 scan **10 Hz** |
| **`/scan` 实测** | **~14.3 Hz**（`ros2 topic hz`） |
| 与深度相机 | 同容器 `astra-camera` 内并行，`/camera/*` + `/scan` 同时存在 |

**通过标准：** `/scan` 有稳定帧率，`ranges` 非空 — **已满足**。

### 6.5 常用 launch 参数

| 参数 | 说明 |
|------|------|
| `serial_port` | `/dev/lidar` |
| `serial_baudrate` | 多数 RPLidar A 系 **115200** |
| `frame_id` | 建议 `laser`，便于与远端 Nav2 一致 |
| `scan_mode` | 留空或按型号文档 |

型号与 launch 文件名以 [sllidar_ros2](https://github.com/Slamtec/sllidar_ros2) 仓库为准（A1/A2/A3/S 等 launch 不同）。

---

## 7. 常驻、开机自启与双传感器并行

`deploy/sensor_stack/docker-compose.yml` 中 **`astra-camera`** 已改为：

- `restart: unless-stopped` — **Docker 服务起来后自动拉起容器**（板子重启后同样生效）
- 挂载 `scripts/start_sensors.sh` — **同一容器**内启动 Astra + RPLidar
- 挂载 `/dev:/host_dev`，解决 USB 串口晚枚举后容器内看不到的问题
- `.env`：`ENABLE_LIDAR=true`、`LIDAR_SERIAL=/host_dev/ttyUSB0`、`LIDAR_WAIT_SECONDS=30`

**板子一次性启用（改 compose 后执行一次，vfs 下可能较慢）：**

```bash
# 确保 Docker 开机自启（一般已 enable）
sudo systemctl enable docker

cd ~/sensor_stack
# 同步仓库里的 compose、scripts、.env 后：
cp -n .env.example .env   # 或合并 ENABLE_LIDAR / LIDAR_SERIAL 行
docker compose up -d astra-camera
```

**日常：**

```bash
docker compose stop astra-camera    # 停止
docker compose start astra-camera   # 启动（秒级，勿 down 后 up 除非改配置）
docker compose logs -f astra-camera
```

**验收：**

```bash
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash && source /ros2_ws/install/setup.bash
  ros2 topic list | grep -E "scan|camera"
'
```

**说明：**

| 项目 | 行为 |
|------|------|
| 重启 3568 | `docker.service` → 自动 **start** 已有 `astra-camera` 容器（通常 **几十秒** 内话题恢复） |
| `docker compose down` | 删容器；下次 `up` 又 **Creating**（vfs 慢）— **尽量避免** |
| 仅关雷达 | `.env` 设 `ENABLE_LIDAR=false` 后 `up -d --force-recreate`（会慢一次） |

---

## 8. 远端建图 / 导航（边缘采集）

3568 作传感器节点、**有线千兆 / WiFi** 把 `/scan`（+ 可选压缩深度）发给远端 ROS2：

| 话题 | 建议 |
|------|------|
| `/scan` | **优先转发**，带宽小 |
| `/tf`、`/tf_static` | 需与远端统一 `frame_id` |
| `/camera/depth/image_raw` | 全帧 30Hz 不适合长期 WiFi；见深度相机文档 |

同一 `ROS_DOMAIN_ID`、NTP 同步；跨网用 VPN 或 `dds-router` / `zenoh`。

---

## 9. 常见问题

| 现象 | 处理 |
|------|------|
| 无 `/dev/ttyUSB*` | 线材、Hub 供电、换 USB 口（Bus 2） |
| `open failed` | udev、`dialout` 组、是否被 ModemManager 占用：`sudo systemctl stop ModemManager` |
| 两个 CH341 | 拔插法确认雷达口，改 udev `devpath` |
| 有 `/scan` 但全 0 / inf | 型号/波特率/launch 文件不匹配 |
| colcon 找不到包 | 确认 `~/ros2_ws/src/sllidar_ros2` 存在且 `colcon build` 成功 |
| Docker 内无串口 | compose 已加 `LIDAR_SERIAL`；容器内用 **ttyUSB0** 非 `/dev/lidar` |
| 重启后无话题 | `systemctl is-enabled docker`；`docker ps` 看 astra-camera 是否 Up |

---

## 10. 参考

- Slamtec ROS2：<https://github.com/Slamtec/sllidar_ros2>
- 板端深度相机验收：`rk3568/docs/Astra_RK3568部署方案.md`
- xtark 雷达硬件说明：`xtark/docs/README.md`（ROS1 仅供参考）

---

**文档版本：** 2026-06-04（雷达 `/scan` 验收通过）  
**板子：** `192.168.1.163` — RPLidar + Astra 可在同一 `astra-camera` 容器内并行运行。
