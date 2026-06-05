# Docker 镜像归档（arm64）

| 文件 | 说明 |
|------|------|
| `ros-humble-ros-base-jammy-arm64.tar` | `ros:humble-ros-base-jammy` arm64，`docker save` 导出，约 245MB |

`*.tar` 已加入 `.gitignore`，不提交 Git。

板子与 Win11 上可不长期保留同名 tar / 已 load 的镜像，需要时：

```powershell
scp rk3568\images\ros-humble-ros-base-jammy-arm64.tar marvsmart@192.168.1.163:/home/marvsmart/
```

```bash
docker load -i ~/ros-humble-ros-base-jammy-arm64.tar
docker tag ros:humble-ros-base-jammy-arm64 ros:humble-ros-base-jammy
```
