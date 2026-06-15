# PC 联调环境

PC 联调统一在 **WSL2** 下进行。主入口程序是 `pc/qt_client`，负责 GUI 遥控、TCP JSON、ROS2 发布和建图栈启停。详细流程见 `docs/WSL2统一栈运行与调试.md`。

## 当前角色

```text
WSL2:
  qt_client 连接 xtark JSON 8765
  发布 /odom_base、/base_status 和 TF odom -> base_link
  订阅 RK3568 /scan
  GUI 启停 RViz2 / slam_toolbox
```

## 当前结论

建图前的软件和硬件链路已经具备条件：

- RK3568 `/scan` 可在 WSL2 订阅，约 14 到 15 Hz，`frame_id=laser`
- xtark JSON `192.168.1.169:8765` 可连接
- `qt_client` 已能把 `odom_base` / `base_status` 转为 ROS2 topic
- TF `odom -> base_link -> laser` 可查
- RViz2 和 slam_toolbox 已安装并可由 GUI 启动

下一阶段是真机低速试建图，不再继续拆架构或更换运行模式。

## 目录

| 路径 | 用途 |
|------|------|
| `docs/` | 联调方案、运行检查和历史归档 |
| `qt_client/` | WSL2 联调客户端，日常主入口 |
| `tools/` | 命令行 JSON 验链路工具 |

## 启动

```bash
cd /mnt/d/Downloads/work/ros-dev/pc/qt_client
./run.sh
```

连接目标：

```text
xtark: 192.168.1.169:8765
ROS_DOMAIN_ID: 0
```
