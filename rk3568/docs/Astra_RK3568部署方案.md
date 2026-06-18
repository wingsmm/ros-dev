# RK3568 Astra 深度相机设备状态

本文只保留 RK3568 平台上的 Astra 深度相机设备状态、运行入口和验收结果。深度相机型号、驱动、话题、排错和维护规则统一维护在 xtark 侧的集中资料文档中。

## 1. 当前状态

| 项目 | 状态 |
|------|------|
| 平台 | RK3568，aarch64 |
| 系统 | Ubuntu 20.04.6 LTS |
| ROS | ROS2 Humble，Docker 内运行 |
| 容器 | `astra-camera` |
| 镜像 | `ros-humble-astra:deps` |
| Docker | 已验证可运行 |
| 设备识别 | `2bc5:0403` 深度/红外，`2bc5:0502` 彩色 UVC |
| 验收结果 | 深度约 29.19 Hz，红外约 29.71 Hz，彩色约 24.02 Hz |

RK3568 当前定位是传感器盒，负责接 USB 传感器并发布 ROS2 topic，不负责底盘控制。

## 2. USB 设备信息

| USB ID | 说明 |
|--------|------|
| `2bc5:0403` | Astra 深度/红外 OpenNI 设备 |
| `2bc5:0502` | Astra 彩色 UVC 设备 |

注意：不要假设彩色 UVC 一定稳定枚举为某个固定 `/dev/videoX`。当前运行更依赖 `/dev/bus/usb` 和 libuvc 路径。

## 3. 运行入口

日常只使用已有容器的 stop/start：

```bash
docker compose start astra-camera
docker compose stop astra-camera
docker compose logs -f astra-camera
```

不建议无必要执行 `docker compose down` 后重建容器。

## 4. ROS2 话题

| 话题 | 内容 |
|------|------|
| `/camera/depth/image_raw` | 深度图 |
| `/camera/depth/camera_info` | 深度相机参数 |
| `/camera/depth/points` | 点云 |
| `/camera/ir/image_raw` | 红外图 |
| `/camera/ir/camera_info` | 红外相机参数 |
| `/camera/color/image_raw` | 彩色图 |
| `/camera/color/camera_info` | 彩色相机参数 |

## 5. 验收速查

```bash
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source ~/ros2_ws/install/setup.bash
  ros2 topic list | grep camera
  timeout 12 ros2 topic hz /camera/depth/image_raw
  timeout 12 ros2 topic hz /camera/ir/image_raw
  timeout 15 ros2 topic hz /camera/color/image_raw
  timeout 8 ros2 topic bw /camera/depth/image_raw
'
```

通过标准：

| 检查项 | 期望 |
|--------|------|
| 深度图 | 接近 30 Hz |
| 红外图 | 接近 30 Hz |
| 彩色图 | 能稳定发布 |
| 点云 | `/camera/depth/points` 有发布 |
| 带宽 | 深度全帧约 18 MB/s，网络转发需谨慎 |

## 6. 与 RPLidar 共存

当前 RK3568 可在 `astra-camera` 容器内同时运行 Astra 与 RPLidar：

| 设备 | 话题 |
|------|------|
| Astra | `/camera/*` |
| RPLidar | `/scan` |

建图调试优先使用低带宽 `/scan`；深度图、点云只在试验需要时开启或转发。

## 7. 本文边界

- 本文只记录 RK3568 平台事实。
- 不在本文展开 Astra 驱动、OpenNI、Docker 镜像构建、VMware 历史方案或深度相机通用排错。
- 后续如果 RK3568 的设备状态、容器名、话题或验收结果变化，只更新本平台差异。
