# RK3568 传感器节点迁移说明

## 结论

当前 `rk3568/` 已经可以作为 ARM64 传感器采集节点的迁移来源。对外迁移时不要把整个目录一股脑拷过去，按下面两类文件走就够了：

| 类型 | 文件 | 用途 |
|------|------|------|
| 部署包 | `packages/rk3568_deploy_files_2026-06-04.tar.gz` | Compose、脚本、udev 模板、源码和文档 |
| 运行镜像 | `packages/rk3568_ros-humble-astra-deps_2026-06-04.tar.gz` | 已装好 ROS2 依赖的 Docker 镜像 |

这两份是迁移到其他 ARM64 设备时最应该优先使用的东西。

## 本地目录怎么理解

`rk3568/` 本地目录分成三层，不需要混着看：

| 层级 | 路径 | 说明 |
|------|------|------|
| 当前方案 | `deploy/` | 可读、可改、可重新打包的部署来源 |
| 迁移包 | `packages/` | scp 到远端的压缩包和镜像 |
| 本机备份 | `backups/` | 已验证状态的备份，不作为日常编辑目录 |

简单说：**改方案看 `deploy/`，迁移交付看 `packages/`。**

## 迁移前提

目标设备建议满足：

| 项目 | 要求 |
|------|------|
| 架构 | `aarch64` / `arm64` |
| 系统 | Linux，能运行 Docker |
| USB | 能识别 Astra 和 RPLidar |
| 存储 | 至少预留 6 GB |

不建议直接迁移到 32 位 ARM。

## 推荐迁移流程

### 1. 解部署包

```bash
mkdir -p ~/rk3568_deploy
tar -xzf rk3568_deploy_files_2026-06-04.tar.gz -C ~/rk3568_deploy
```

解开后会得到 `deploy/` 和 `docs/`。按实际需要放置：

```text
~/sensor_stack/                       <- 来自 deploy/sensor_stack
~/ros2_ws/src/ros2_astra_camera/      <- 来自 deploy/src/ros2_astra_camera
~/ros2_ws/src/sllidar_ros2/           <- 来自 deploy/src/sllidar_ros2
```

### 2. 导入运行镜像

```bash
gzip -dc rk3568_ros-humble-astra-deps_2026-06-04.tar.gz | docker load
docker images | grep ros-humble-astra
```

### 3. 重配设备节点

目标设备上必须重新确认：

```bash
lsusb
lsusb -t
ls -l /dev/ttyUSB*
v4l2-ctl --list-devices
```

重点：

- RPLidar 串口可能不是 `/dev/ttyUSB0`，需要按目标设备重写 udev 规则和 `.env` 里的 `LIDAR_SERIAL`。
- Astra 优先依赖 `/dev/bus/usb`，不要假设 `/dev/video9`、`/dev/video10` 在新设备上仍然存在。

### 4. 启动

```bash
cd ~/sensor_stack
cp -n .env.example .env
# 按目标设备修改 LIDAR_SERIAL、VIDEO0、VIDEO1、MEDIA0
docker compose up -d astra-camera
```

### 5. 验收

```bash
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  ros2 topic list | grep -E "scan|camera"
  timeout 8 ros2 topic hz /scan
  timeout 8 ros2 topic hz /camera/depth/image_raw
'
```

通过标准：

| 话题 | 期望 |
|------|------|
| `/scan` | 有发布者，`ranges` 非空 |
| `/camera/depth/image_raw` | 有发布者，接近 30 Hz |
| `/camera/ir/image_raw` | 有发布者，接近 30 Hz |
| `/camera/color/image_raw` | 有发布者，稳定输出 |

## 已编译工作区备份

已编译工作区备份在：

```text
backups/2026-06-04/workspace/rk3568_ros2_ws_src_build_install_2026-06-04.tar.gz
```

它不是日常迁移的首选，而是同类设备快速恢复用的。原因是当前工作区使用 `--symlink-install`，只备份 `install/` 不完整，所以这里备份的是：

```text
~/ros2_ws/src
~/ros2_ws/build
~/ros2_ws/install
```

迁移到不同 ARM 板时，更稳妥的做法是用源码重新编译：

```bash
cd ~/sensor_stack
docker compose --profile build run --rm build
docker compose --profile build-lidar run --rm build-lidar
```

## 自启动

目标设备上需要：

```bash
sudo systemctl enable docker
```

Compose 中 `astra-camera` 保持：

```yaml
restart: unless-stopped
```

迁移后必须做一次重启验收，确认 Docker 服务、容器和 ROS2 话题会自动恢复。
