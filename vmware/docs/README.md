# vmware 文档目录

塔克官方 VMware 虚拟开发机 `xtark-vmpc`（`192.168.1.154`）的说明，与真机 `xtark-robot`（`192.168.1.169`）分开维护。

## 文档

| 文档 | 定位 |
|------|------|
| [VMware开发环境.md](./VMware开发环境.md) | VM 实探测、ROS 网络、`~/ros_ws` 布局 |
| [VMware Qt客户端整体方案.md](./VMware%20Qt客户端整体方案.md) | VMware Qt 纯客户端实施方案 |
| [VMware Qt纯客户端实现与测试报告.md](./VMware%20Qt纯客户端实现与测试报告.md) | 2026-07-03 实现结果与真机/VM 验收记录 |

## 相关（真机 / 脚本）

| 位置 | 说明 |
|------|------|
| [xtark/docs/远端登录.md](../../xtark/docs/远端登录.md) | 真机 SSH、plink、ROS 环境 |
| [xtark/docs/远端硬件与传感器.md](../../xtark/docs/远端硬件与传感器.md) | 真机硬件与话题 |
| [xtark/scripts/pc_stack.sh](../../xtark/scripts/pc_stack.sh) | 真机 ROS 服务栈（配 VMware Qt） |
| [xtark/scripts/pc_stack_remote.bat](../../xtark/scripts/pc_stack_remote.bat) | Windows 部署/控制真机 `pc_stack` |
| [vmware/qt/](../qt/) | VM 上 PyQt5 纯客户端（本地 RViz + topic 诊断） |
| [vmware/scripts/vm_qt_remote.bat](../scripts/vm_qt_remote.bat) | Windows 部署 `vmware/qt` 到 VM |

## 快速命令

```bash
# 真机（手动）
~/ros_ws/scripts/pc_stack.sh camera-start
# 或 full-start
```

```bat
rem VM
vmware\scripts\vm_qt_remote.bat run
```
