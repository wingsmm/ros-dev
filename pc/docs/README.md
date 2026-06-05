# PC / WSL2 文档目录

本目录放 PC 作为联调中心时需要看的文档，包括 WSL2、跨设备数据汇聚、底盘 JSON 协议和历史试验归档。

| 文档 | 用途 |
|------|------|
| `WSL2_ROS2联调方案.md` | WSL2 作为 ROS2 x86 联调中心的方案 |
| `移动平台外挂感知建图导航方案.md` | RK3568 / PC / 底盘平台的总体架构 |
| `底盘JSON对接协议草案.md` | 公司底盘或 xtark JSON 适配共用的接口草案 |
| `archive/` | 历史 VM 方案和临时计划归档 |

当前主线：

```text
RK3568 采集 /scan
xtark 提供 odom_base / base_status
PC / WSL2 汇聚数据，后续跑 RViz2 / slam_toolbox
```

不放在这里：

```text
RK3568 单机传感器部署    -> rk3568/docs/
xtark 原生 ROS1 小车文档 -> xtark/docs/
```
