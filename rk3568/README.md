# RK3568 采集节点

## 架构图

```text
[传感器硬件]
  ├─ Astra Pro
  │    ├─ 深度 / 红外
  │    └─ 彩色 UVC
  │
  └─ RPLidar XAS
       └─ USB 转串口

        │
        │ USB
        ▼

[RK3568 宿主机]
  ├─ Ubuntu 20.04 / aarch64
  ├─ Docker + Docker Compose
  ├─ USB / 串口设备透传
  └─ ROS2 工作区挂载

        │
        │ docker compose
        ▼

[Docker 容器: astra-camera]
  ├─ ROS2 Humble
  ├─ Astra 驱动
  ├─ RPLidar 驱动
  └─ 统一启动脚本

        │
        │ ros2 launch
        ▼

[ROS2 采集节点]
  ├─ astra_camera_node
  │    ├─ /camera/depth/image_raw
  │    ├─ /camera/ir/image_raw
  │    ├─ /camera/color/image_raw
  │    └─ /camera/depth/points
  │
  └─ sllidar_node
       └─ /scan

        │
        │ DDS / ROS_DOMAIN_ID
        ▼

[远端主机]
  ├─ 订阅 /scan
  ├─ 订阅 /camera/*
  └─ 建图 / 导航 / 可视化
```

## 自启动链路

```text
RK3568 开机
  -> docker.service
  -> astra-camera 容器自动恢复
  -> 启动 Astra + RPLidar
  -> 发布 /camera/* + /scan
```

## 迁移包

远端迁移只需要优先看：

```text
packages/rk3568_ros-humble-astra-deps_2026-06-04.tar.gz
packages/rk3568_deploy_files_2026-06-04.tar.gz
```

第一个用于 `docker load`，第二个用于解出部署文件。

## 详细文档

```text
docs/Astra_RK3568部署方案.md
docs/RPLidar_RK3568部署方案.md
docs/README.md
deploy/README.md
```

跨设备联调和旧底盘 JSON 方案已经归档在：

```text
../pc/docs/
```
