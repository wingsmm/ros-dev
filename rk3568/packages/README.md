# RK3568 迁移包

远端迁移优先使用这两个文件：

| 文件 | 用途 |
|------|------|
| `rk3568_ros-humble-astra-deps_2026-06-04.tar.gz` | 已安装依赖的 ROS2 Docker 镜像 |
| `rk3568_deploy_files_2026-06-04.tar.gz` | 部署文件、脚本、配置模板和源码 |

远端示例：

```bash
mkdir -p ~/packages
scp rk3568_ros-humble-astra-deps_2026-06-04.tar.gz user@host:~/packages/
scp rk3568_deploy_files_2026-06-04.tar.gz user@host:~/packages/
```

```bash
cd ~/packages
gzip -dc rk3568_ros-humble-astra-deps_2026-06-04.tar.gz | docker load
tar -xzf rk3568_deploy_files_2026-06-04.tar.gz -C ~/
```

`ros-humble-ros-base-jammy-arm64.tar` 是基础镜像归档，仅在需要重新制作依赖镜像时使用。

