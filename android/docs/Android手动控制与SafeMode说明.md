# Android 手动控制与 SafeMode 说明

本文记录 RobotCA Android 客户端在 xtark 上测试时，手工按钮或摇杆“前进不灵活”的常见原因。

## 当前控制链路

Android/RobotCA 不走 TCP JSON `8765`，而是直接连接 xtark ROS1 master：

```text
Android /android/robot_controller
  -> ROS1 /cmd_vel
  -> xtark_driver
  -> 底盘
```

机器人端 Android 测试脚本只需要启动：

```text
roscore
xtark_bringup.launch
xtark_camera.launch
```

不需要启动 `json_base_adapter`。`json_base_adapter` 是 PC Qt client 的 TCP JSON 通道，监听 `8765`，与 Android 遥控链路无关。

## 手工控制入口

Android 左下角手工按钮和右下角摇杆最终都走同一个速度入口：

```text
ManualControlFragment / JoystickView
  -> RobotController.forceVelocity()
  -> RobotController.publishVelocity()
  -> ROS1 /cmd_vel
```

因此手工按钮不会绕过 RobotCA 原有安全逻辑。它会继续受这些配置影响：

- SafeMode 安全减速
- 三轴反转配置
- `/cmd_vel` topic 配置
- 急停/停车逻辑

## SafeMode 的行为

RobotCA 有一个基础的前向碰撞预警与安全减速功能，不是完整自主避障。

逻辑位置：

```text
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/WarningSystem.java
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Core/RobotController.java
src/android_foo/control_app/src/main/java/com/robotca/ControlApp/Fragments/HUDFragment.java
```

`WarningSystem` 会分析激光雷达前方约 `+-40 deg` 范围内的障碍物。如果前方距离过近，会触发 HUD 红色预警，并增加 `warnAmount`。

在 SafeMode 开启时，`RobotController.publishVelocity()` 会对前进速度做裁剪：

```java
if (context.getWarningSystem().isSafemodeEnabled() && linearVelocityX >= 0.0) {
    scale = (float) Math.pow(1.0f - context.getHUDFragment().getWarnAmount(), 2.0);
}
```

也就是说，请求速度会变成：

```text
实际前进速度 = 请求前进速度 * (1 - warnAmount)^2
```

示例：

```text
请求前进 0.10 m/s
warnAmount = 0.7 -> 实际约 0.009 m/s
warnAmount = 0.9 -> 实际约 0.001 m/s
```

所以当 HUD 大面积红色闪烁时，按“前进”可能看起来几乎不动。这通常不是 xtark 没收到命令，而是 Android 端在发布 `/cmd_vel` 前已经把前进速度压低了。

## 它是不是避障

可以把它理解为：

```text
前向碰撞预警 + 安全减速
```

它不是完整避障。它不会自动规划路线，也不会自己绕开障碍物；它只会在前方危险时降低或接近阻止继续前进。

## 典型现象

如果出现以下现象，优先怀疑 SafeMode 正在生效：

- HUD 顶部红色或闪红
- 前进不灵活、很慢、甚至像没反应
- 后退或原地转向相对正常
- 车端 `/cmd_vel` 有 Android publisher，链路并未断开

车端检查：

```bash
rostopic info /cmd_vel
rostopic hz /cmd_vel
rostopic echo /cmd_vel
```

正常链路应能看到：

```text
Publishers:
 * /android/robot_controller

Subscribers:
 * /xtark_driver
```

如果按住前进时 `/cmd_vel.linear.x` 很小，基本就是 SafeMode/预警裁剪导致。

## 调试建议

第一轮排障建议按顺序做：

1. 确认 Android 当前控制模式是“摇杆”。
2. 观察 HUD 是否红色预警。
3. 在车端 `rostopic echo /cmd_vel`，按住 Android 前进按钮，确认实际 `linear.x`。
4. 临时关闭 Android 设置里的 SafeMode，或把预警距离调小。
5. 再次按前进，对比 `/cmd_vel.linear.x` 和底盘运动。

建议测试参数：

```text
人工按钮线速度：0.10 m/s
人工按钮角速度：0.20 rad/s
预警距离临时调试值：0.6 ~ 1.0 m
```

如果关掉 SafeMode 后前进恢复正常，说明底盘和 ROS 链路没有问题，问题来源是预警参数过保守或现场障碍太近。

## 注意

不要因为 `192.168.1.169:8765` 不通就判断 Android 遥控异常。Android 当前不使用 `8765`，只要 ROS master 和 `/cmd_vel` 链路正常即可。
