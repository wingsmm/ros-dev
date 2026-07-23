# vmware 脚本入口

Windows 侧部署 VMware VM `192.168.1.154` 上的 **vmware/qt** 纯客户端。

| 脚本 | 目标 | 作用 |
|------|------|------|
| `vmware/scripts/vm_qt_remote.bat` | VM `154` | `deploy` 同步 `vmware/qt`；`astra-deploy` 同步近场 ROS 包并 `catkin_make --pkg` |
| `xtark/scripts/pc_stack_remote.bat` | 真机 `168` | 部署/启停 `pc_stack`（与 Qt 分离）；`deploy` 含 `astra_capture.sh` |

## 一次性准备（仅 VM Qt）

```bat
vmware\scripts\vm_qt_remote.bat bootstrap
```

近场 Stage B 包部署（不改变默认 Qt `deploy` 语义）：

```bat
vmware\scripts\vm_qt_remote.bat astra-deploy
```

## 日常使用

```bash
# 小车 169（手动）
~/ros_ws/scripts/pc_stack.sh camera-start
```

```bat
rem VM 154
vmware\scripts\vm_qt_remote.bat run
```

VM 内 Qt 只做本地 ROS 连接与 RViz，不 SSH、不调用 pc_stack。
