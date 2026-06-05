# PC 联调环境

PC 侧用于开发、调试和算法验证。当前推荐使用 WSL2 作为 ROS2 x86 联调环境，Windows 侧保留 Qt 调试台和命令行工具。

## 当前角色

```text
PC / WSL2:
  接收 RK3568 的 ROS2 /scan
  接收 xtark 的 TCP JSON odom_base / base_status
  发送 xtark 的 TCP JSON cmd_vel
  后续运行 RViz2 / slam_toolbox / 算法验证
```

RK3568 只做传感器盒，xtark 只做底盘运动和里程计反馈。

## 目录

| 路径 | 用途 |
|------|------|
| `docs/` | PC / WSL2 联调方案和记录 |
| `tools/` | PC / WSL2 / RK3568 可运行的命令行 JSON 工具 |
| `qt_client/` | Windows PC 图形调试台 |

## 推荐入口

| 场景 | 入口 |
|------|------|
| Windows 图形遥控 / 状态查看 | `pc/qt_client/` |
| WSL2 / 命令行快速测试 | `pc/tools/` |
| WSL2 ROS2 联调说明 | `pc/docs/WSL2_ROS2联调方案.md` |
| 跨设备总体方案 / JSON 协议 | `pc/docs/` |

## 已确认

- WSL2 可以访问 xtark `192.168.1.169`。
- WSL2 可以访问 RK3568 `192.168.1.163`。
- xtark JSON 控制链路已经完成第一阶段低速验证。
- WSL2 原生 ROS2 可以订阅 RK3568 `/scan`，约 14 Hz。
- RK3568 USB 传感器继续由 RK 本机 Docker 采集，不在 WSL2 里直连 USB。

## 下一步

先补齐 xtark 运动反馈：

```text
xtark_bringup -> /odom -> json_base_adapter -> odom_base -> WSL2
```

然后在 WSL2 中做 `JSON odom_base -> ROS2 /odom_base` 适配层。
