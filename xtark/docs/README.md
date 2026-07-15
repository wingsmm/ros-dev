# xtark 文档目录

本目录记录一代 ROS1 冻结维护版的机器人端能力。已实现流程保持可恢复、可排障；实验方案和历史方案不得当作正式产品基线。

## 文档状态

| 状态 | 文档 | 定位 |
|---|---|---|
| 冻结主线 | `Android与xtark交互说明.html` | Android ↔ 小车 ROS1 主契约。 |
| 冻结主线 | `远端登录.md` | SSH、plink、ROS 环境与远程检查。 |
| 冻结主线 | `远端硬件与传感器.md` | 真机硬件、设备节点和 ROS topic 基线。 |
| 冻结主线 | `机器人控制链路说明.md` | Android/VMware 手动控制、反馈和激光链路。 |
| 冻结主线 | `深度相机与机器人端相机功能梳理.md` | 已有 Android/VMware 相机链路边界。 |
| 资料基线 | `Orbbec_Astra_Pro_深度相机资料.md` | 设备身份、USB ID 和已验收话题。 |
| 实验记录 | `激光里程计实验方案.md` | RF2O `/odom_laser` 对比实验，不进入冻结产品默认栈。 |
| 历史归档 | `archive/` | 旧 JSON、建图和自主导航方案，只供追溯。 |

## 相关文档（VMware）

| 文档 | 定位 |
|------|------|
| [vmware/docs/VMware开发环境.md](../../vmware/docs/VMware开发环境.md) | VMware 虚拟机 `xtark-vmpc`（`192.168.1.154`）：RViz/遥控、`pc_stack` |

## 保留参考

| 文档 | 定位 |
|------|------|
| `archive/JSON控制适配方案.md` | PC/Qt JSON 控制适配方案。当前先归档；Android 两点导航调通后，再做 Android/Qt 方案一致性整理。 |
| `archive/真机建图与遥控方案.md` | 早期学习/参考文档：借鉴别人的原生 ROS1 建图、遥控、保存地图流程。当前不作为主线。 |
| `archive/真机自主导航方案.md` | 早期学习/参考文档：保存地图后的 AMCL + move_base/TEB 完整导航。当前不作为主线。 |

## 冻结主链路

```text
/scan + /odom
  -> gmapping
  -> /map
  -> Android 显示已走过地图

map -> base_footprint TF
  -> xtark_nav/launch/robot_pose_in_map.launch
  -> /robot_pose_in_map
  -> Android 显示小车位置

Android A/B 点
  -> /move_base_simple/goal
  -> move_base
  -> /cmd_vel
  -> xtark_driver
```

## 当前怎么跑

```bat
xtark\scripts\android_remote.bat all
xtark\scripts\android_remote.bat status
xtark\scripts\android_remote.bat stop
```

Android App 的 ROS Master URI：

```text
http://192.168.1.168:11311
```

## 维护规则

- 当前可执行流程、远端登录和硬件速查保留在活动文档。
- RF2O、深度增强等实验必须明确标记为实验，不得加入默认启动栈。
- 学习资料和旧方案放入 `archive/`；不删除历史，但不得称为当前主线。
- 新功能转入二代 Jetson ROS2；一代只做冻结维护。
