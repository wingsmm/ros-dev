# Orbbec Astra Pro 深度相机资料

本文只记录 Orbbec Astra Pro 这款深度相机的关键资料。平台文档只保留各自设备状态，不再重复展开。

## 1. 设备速查

| 项目 | 内容 |
|------|------|
| 型号 | Orbbec Astra Pro / Astra Pro FHD Camera |
| 厂商 | 奥比中光 Orbbec |
| 深度/红外 USB ID | `2bc5:0403` |
| 彩色 UVC USB ID | `2bc5:0502` |
| 常见彩色识别名 | `Astra Pro FHD Camera` |

Astra Pro 有两条链路：

| 链路 | 输出 | 备注 |
|------|------|------|
| 深度/红外 | depth / IR / points | 走 OpenNI / Astra 驱动 |
| 彩色 UVC | color image | 走 UVC / libuvc / v4l2 |

## 2. 参数与实测

| 数据流 | 配置/格式 | RK3568 实测 |
|--------|-----------|-------------|
| 深度 | 640x480，30 Hz 配置 | 约 29.19 Hz |
| 红外 | 640x480，30 Hz 配置 | 约 29.71 Hz |
| 彩色 | 640x480，MJPEG，30 Hz 配置 | 约 24.02 Hz |
| 点云 | 由深度生成 `/camera/depth/points` | 已发布 |
| 深度带宽 | `/camera/depth/image_raw` 全帧 | 约 18 MB/s |

补充说明：

| 项目 | 说明 |
|------|------|
| 彩色 UVC product id | `0x0502`，启动参数里常写作 `uvc_product_id:=1282` |
| 深度/红外设备 | `2bc5:0403` |
| 彩色 UVC 设备 | `2bc5:0502` |
| video 设备号 | 不建议绑定固定 `/dev/videoX`，实机更应以 USB ID / libuvc 为准 |

## 3. 与当前主线的关系

| 场景 | 是否依赖 Astra 深度链路 |
|------|------------------------|
| Android 相机页 | 否，订阅 xtark UVC 彩色 `/image_raw/compressed` |
| PC Qt 摄像头页 | 否，当前拉 HTTP/MJPEG `/camera/image_raw` |
| 两点导航 / 2D 建图 | 否，主链路是 `/scan`、`/odom`、`/map`、`/cmd_vel` |
| RGB-D、点云、RTAB-Map、近场避障 | 是 |

结论：短期主线不需要启动深度相机。需要 RGB-D / 点云能力时再单独打开。

## 4. xtark Jetson / ROS1

| 项目 | 内容 |
|------|------|
| 平台 | xtark Jetson Nano |
| ROS | ROS1 Melodic |
| 当前看图主链路 | `/dev/video0` UVC 彩色 |
| Android 默认图像话题 | `/image_raw/compressed` |
| Qt/浏览器预览话题 | `/camera/image_raw` |
| 深度相机包 | `xtark_nav_depthcamera` |
| 深度相机 launch | `xtark_depthcamera.launch` |
| 深度相机话题 | `/camera/rgb/*`、`/camera/depth/*` |

xtark 当前已验证主线是 UVC 彩色看图；深度相机不是 Android/Qt 默认启动栈。

## 5. RK3568 / ROS2 已验收状态

| 项目 | 内容 |
|------|------|
| 平台 | RK3568 aarch64 |
| ROS | ROS2 Humble，Docker 内运行 |
| 容器 | `astra-camera` |
| 镜像 | `ros-humble-astra:deps` |
| USB 访问 | `/dev/bus/usb` |
| 验收结果 | 深度约 29.19 Hz，红外约 29.71 Hz，彩色约 24.02 Hz |

已验收话题：

| 话题 | 内容 |
|------|------|
| `/camera/depth/image_raw` | 深度图 |
| `/camera/depth/points` | 点云 |
| `/camera/ir/image_raw` | 红外图 |
| `/camera/color/image_raw` | 彩色图 |
| `/camera/*/camera_info` | 相机参数 |

带宽注意：`/camera/depth/image_raw` 全帧约 18 MB/s，不适合长期直接走 WiFi。

## 6. 常用命令

RK3568 容器：

```bash
docker compose start astra-camera
docker compose stop astra-camera
docker compose logs -f astra-camera
```

USB 检查：

```bash
lsusb | grep -Ei "2bc5|orbbec|astra"
lsusb -t
```

ROS2 话题检查：

```bash
docker exec astra-camera bash -lc '
  source /opt/ros/humble/setup.bash
  source ~/ros2_ws/install/setup.bash
  ros2 topic list | grep camera
  timeout 12 ros2 topic hz /camera/depth/image_raw
  timeout 12 ros2 topic hz /camera/ir/image_raw
  timeout 15 ros2 topic hz /camera/color/image_raw
'
```

## 7. 常见问题

| 现象 | 处理 |
|------|------|
| 有彩色、无深度 | 查 `2bc5:0403` 是否枚举，查 Astra/OpenNI 驱动 |
| 有深度、无彩色 | 查 `2bc5:0502`、UVC 参数、`UVC_PRODUCT_ID` |
| `/dev/videoX` 不固定 | 不要绑定固定 video 编号，优先走 `/dev/bus/usb` / libuvc |
| 容器重建很慢 | 优先 `docker compose stop/start`，不要无必要 `down` |
| 点云或深度图占资源 | 按需开启；建图主线优先 `/scan` |
