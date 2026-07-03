# vmware 脚本入口

Windows 侧部署 VMware VM `192.168.1.154` 上的 **vmware/qt** 纯客户端。

| 脚本 | 目标 | 作用 |
|------|------|------|
| `vmware/scripts/vm_qt_remote.bat` | VM `154` | 同步 `vmware/qt` + PyQt5 |
| `xtark/scripts/pc_stack_remote.bat` | 真机 `169` | 部署/启停 `pc_stack`（与 Qt 分离） |

## 一次性准备（仅 VM Qt）

```bat
vmware\scripts\vm_qt_remote.bat bootstrap
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
