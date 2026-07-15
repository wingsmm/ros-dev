# 历史 PC 联调资产

`pc/` 保存旧 PC/RK3568/ROS2 联调客户端、工具和方案，不属于当前两代产品线的支持入口。

- 一代 ROS1 使用 [xtark](../xtark/README.md) + [VMware](../vmware/README.md) + [Android](../android/README.md)。
- 二代 ROS2 使用 [Jetson](../jetson/README.md) + `jetson/cockpit`。
- `pc/qt_client/` 与 `pc/tools/` 只供历史代码追溯，不再作为日常运行环境或新功能承载面。
- 旧联调、建图、相机和统一栈方案已移入 [docs/archive/](docs/archive/)。

不要从本目录恢复第三条产品主线；可复用结论应重新评估后迁入对应产品线的权威文档。
