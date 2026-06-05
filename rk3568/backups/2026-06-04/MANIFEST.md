# RK3568 本机备份清单

备份时间：2026-06-04

来源设备：`marvsmart@192.168.1.163`，主机名 `rk356x`

## 文件

| 文件 | 大小 | SHA256 | 说明 |
|------|------|--------|------|
| `../../packages/rk3568_ros-humble-astra-deps_2026-06-04.tar.gz` | 578 MB | `a47483947bc4ce878263e5b44fda0f8a56b99fa1a358e39d21dda2b93a109df7` | `ros-humble-astra:deps` Docker 运行镜像 |
| `workspace/rk3568_ros2_ws_src_build_install_2026-06-04.tar.gz` | 46 MB | `4037dee074033c4eb678ae7c73e65e5eaf0a8b0de34554488258d12c3a1f415a` | RK3568 实机 `~/ros2_ws/src build install` |
| `runtime/rk3568_depth_camera_demo_runtime_2026-06-04.tar.gz` | 3.8 KB | `6415d9647a03bef304fc6df9221dc4ecc1140b1ae4b127271f9e463ea36c9194` | RK3568 实机 `~/depth_camera_demo` 运行目录 |
| `../../packages/rk3568_deploy_files_2026-06-04.tar.gz` | 2.3 MB | `31ab68c60dd059b02e754b10034b6deddfe1799e74e03f2aac9b0f35a37564f8` | 本地整理后的轻量部署文件包，不含大镜像和已编译工作区 |
| `source_archives/ros2_astra_camera.tar` | 8.7 MB | `ab86a2b2a41f1d2d0eedc4fa53c73c3545a065d358234bf179869413011102b4` | Astra 源码归档备份 |
| `source_archives/sllidar_ros2.tar.gz` | 366 KB | `a26e0110b60bbbf4fd6510328eb1dda463fc7463ecc4048fd295423dab2fbbf9` | SLLidar 源码归档备份 |

## 说明

- Docker 镜像已从远端 `docker save` 后 gzip 压缩。
- ROS2 工作区备份包含 `src`、`build`、`install`，因为当前 `install` 是 `--symlink-install` 产物，不能单独作为完整二进制备份。
- 轻量部署文件包包含 `README.md`、`deploy` 和 `docs`。
- 远端临时导出文件已在校验完成后删除，RK3568 根分区恢复到约 8.3 GB 可用。

## 恢复示例

导入 Docker 镜像：

```bash
gzip -dc rk3568_ros-humble-astra-deps_2026-06-04.tar.gz | docker load
```

恢复 ROS2 工作区：

```bash
mkdir -p ~/ros2_ws
tar -xzf rk3568_ros2_ws_src_build_install_2026-06-04.tar.gz -C ~/ros2_ws
```

恢复运行目录：

```bash
tar -xzf rk3568_depth_camera_demo_runtime_2026-06-04.tar.gz -C ~
cd ~/depth_camera_demo
docker compose up -d astra-camera
```
