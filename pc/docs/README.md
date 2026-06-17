# PC / WSL2 文档目录

本目录放 PC 作为联调中心时需要看的文档，当前主线是 WSL2 统一栈：在 WSL2 中运行 `qt_client`，汇聚 xtark 底盘 JSON、RK3568 `/scan`、ROS2 TF，并启动 RViz2 / slam_toolbox。

| 文档 | 用途 |
|------|------|
| `WSL2统一栈运行与调试.md` | 当前主线：运行、验收、建图前检查、真机低速测试流程 |
| `qt_client完整说明与开发方案.md` | 上位机能力盘点、与 ROS 手机 App 对比、分阶段开发路线 |
| `PC端相机显示对齐Android方案.md` | PC Qt 摄像头页方案、HTTP/MJPEG MVP 落地状态、长期 ROS 话题对齐边界 |
| `建图联调现状与问题记录.md` | 建图真机联调记录、问题与 A/B/C 阶段任务 |
| `移动平台外挂感知建图导航方案.md` | RK3568 / PC / 底盘平台的总体架构 |
| `底盘JSON对接协议草案.md` | 底盘 JSON 协议草案和 xtark 适配参考 |
| `archive/` | 旧方案、临时计划和历史联调记录归档 |

当前阶段结论：

```text
RK3568 -> WSL2   /scan 已通
xtark  -> WSL2   JSON odom_base / base_status / cmd_vel 已通
WSL2   -> ROS2   /odom_base /base_status + TF 已通
WSL2   -> 建图   RViz2 / slam_toolbox 依赖和启动链路已通
```

建图前的软件和硬件链路已经具备条件。下一阶段进入真机低速试建图，重点观察 `/map` 是否稳定生成、SLAM 是否持续丢帧、RViz 中 `/scan` / TF / map 方向是否一致。

不放在这里：

```text
RK3568 单机传感器部署   -> rk3568/docs/
xtark 原生 ROS1 小车文档 -> xtark/docs/
```
