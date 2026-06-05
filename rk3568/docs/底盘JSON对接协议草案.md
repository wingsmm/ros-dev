# 底盘 JSON 对接协议草案

## 1. 目标

底盘侧不需要接入 ROS2。底盘只需要通过普通通信协议接收 JSON 控制指令，并返回 JSON 运动反馈。

RK / PC 侧会实现适配程序：

```text
ROS2 /cmd_vel -> JSON cmd_vel -> 底盘
底盘 JSON odom_base -> ROS2 /odom_base
```

这样导航系统仍可使用 ROS2，底盘开发只需要按本协议收发 JSON。

## 2. 推荐传输方式

第一版建议：

```text
TCP 长连接 + 一行一个 JSON
```

也就是 NDJSON：

```text
{"type":"cmd_vel","linear_x":0.2,"angular_z":0.0}
{"type":"cmd_vel","linear_x":0.0,"angular_z":0.5}
```

其他方式也可讨论：

| 方式 | 说明 |
|------|------|
| TCP | 第一版推荐，简单可靠 |
| UDP | 延迟低，但需要处理丢包 |
| WebSocket | 调试方便，跨语言友好 |
| HTTP | 不适合高频控制，只适合状态、配置类接口 |
| 串口 / CAN | 可以使用同样字段，但需要另行定义帧格式 |

## 3. 消息类型

| 方向 | `type` | 作用 |
|------|--------|------|
| RK / PC -> 底盘 | `cmd_vel` | 速度控制 |
| 底盘 -> RK / PC | `odom_base` | 底盘位姿和速度反馈 |
| 底盘 -> RK / PC | `wheel_feedback` | 简化运动增量反馈 |
| 底盘 -> RK / PC | `base_status` | 状态、急停、电池、故障 |

## 4. 控制指令：`cmd_vel`

方向：RK / PC -> 底盘

```json
{
  "type": "cmd_vel",
  "seq": 1024,
  "stamp_ms": 1780000000123,
  "linear_x": 0.20,
  "linear_y": 0.00,
  "angular_z": 0.00
}
```

字段说明：

| 字段 | 类型 | 单位 | 必需 | 说明 |
|------|------|------|------|------|
| `type` | string | - | 是 | 固定为 `cmd_vel` |
| `seq` | integer | - | 建议 | 递增序号，便于调试和丢包判断 |
| `stamp_ms` | integer | ms | 建议 | 发送时间戳，Unix epoch 毫秒 |
| `linear_x` | number | m/s | 是 | 前进 / 后退速度，正数前进 |
| `linear_y` | number | m/s | 可选 | 左右横移速度，麦轮 / 全向底盘使用；差速底盘可忽略或置 0 |
| `angular_z` | number | rad/s | 是 | 转向角速度，正数方向需双方约定 |

底盘侧需要完成：

```text
接收 cmd_vel
-> 限速 / 安全检查
-> 转换为底盘内部控制协议
-> 驱动电机
```

建议底盘侧增加超时保护：如果超过约 300-500 ms 没收到新的 `cmd_vel`，自动停车。

## 5. 运动反馈：`odom_base`

方向：底盘 -> RK / PC

如果底盘能计算完整里程计，优先返回 `odom_base`：

```json
{
  "type": "odom_base",
  "seq": 1024,
  "stamp_ms": 1780000000456,
  "x": 1.25,
  "y": 0.08,
  "yaw": 0.12,
  "linear_x": 0.19,
  "linear_y": 0.00,
  "angular_z": 0.01
}
```

字段说明：

| 字段 | 类型 | 单位 | 必需 | 说明 |
|------|------|------|------|------|
| `type` | string | - | 是 | 固定为 `odom_base` |
| `seq` | integer | - | 建议 | 递增序号 |
| `stamp_ms` | integer | ms | 建议 | 反馈时间戳，Unix epoch 毫秒 |
| `x` | number | m | 是 | 底盘估算的 X 位置 |
| `y` | number | m | 是 | 底盘估算的 Y 位置 |
| `yaw` | number | rad | 是 | 底盘朝向角 |
| `linear_x` | number | m/s | 是 | 实际线速度 |
| `linear_y` | number | m/s | 可选 | 实际横移速度，麦轮 / 全向底盘使用 |
| `angular_z` | number | rad/s | 是 | 实际角速度 |

## 6. 简化运动反馈：`wheel_feedback`

如果底盘暂时无法计算完整 `x / y / yaw`，可先返回运动增量：

```json
{
  "type": "wheel_feedback",
  "seq": 1025,
  "stamp_ms": 1780000000500,
  "delta_x": 0.01,
  "delta_y": 0.00,
  "delta_yaw": 0.002,
  "linear_x": 0.20,
  "linear_y": 0.00,
  "angular_z": 0.01
}
```

字段说明：

| 字段 | 类型 | 单位 | 必需 | 说明 |
|------|------|------|------|------|
| `type` | string | - | 是 | 固定为 `wheel_feedback` |
| `seq` | integer | - | 建议 | 递增序号 |
| `stamp_ms` | integer | ms | 建议 | 反馈时间戳，Unix epoch 毫秒 |
| `delta_x` | number | m | 是 | 本周期前进距离 |
| `delta_y` | number | m | 可选 | 本周期横移距离，麦轮 / 全向底盘使用 |
| `delta_yaw` | number | rad | 是 | 本周期转角增量 |
| `linear_x` | number | m/s | 是 | 实际线速度 |
| `linear_y` | number | m/s | 可选 | 实际横移速度，麦轮 / 全向底盘使用 |
| `angular_z` | number | rad/s | 是 | 实际角速度 |

## 7. 状态反馈：`base_status`

方向：底盘 -> RK / PC

```json
{
  "type": "base_status",
  "stamp_ms": 1780000000600,
  "online": true,
  "estop": false,
  "battery_v": 24.3,
  "mode": "auto",
  "error_code": 0
}
```

字段说明：

| 字段 | 类型 | 单位 | 必需 | 说明 |
|------|------|------|------|------|
| `type` | string | - | 是 | 固定为 `base_status` |
| `stamp_ms` | integer | ms | 建议 | 反馈时间戳 |
| `online` | boolean | - | 建议 | 底盘是否在线 |
| `estop` | boolean | - | 是 | 是否急停 |
| `battery_v` | number | V | 建议 | 电池电压 |
| `mode` | string | - | 建议 | `manual` / `auto` / `idle` 等 |
| `error_code` | integer | - | 建议 | 0 表示无故障 |

## 8. 第一版最小要求

底盘开发第一版至少需要支持：

| 能力 | 要求 |
|------|------|
| 接收控制 | 支持 `cmd_vel.linear_x`、`cmd_vel.angular_z` |
| 全向底盘 | 如支持麦轮 / 全向运动，增加 `cmd_vel.linear_y` |
| 安全停车 | 控制指令超时后自动停车 |
| 运动反馈 | 支持 `odom_base` 或 `wheel_feedback` 之一 |
| 状态反馈 | 至少返回急停状态 `estop` |

## 9. 待双方确认

| 项目 | 说明 |
|------|------|
| 通信方式 | TCP / UDP / WebSocket / 串口 / CAN |
| 连接角色 | 底盘作为 server，还是 RK / PC 作为 server |
| 控制频率 | 建议 20-50 Hz，可按底盘能力调整 |
| 反馈频率 | 建议 20-50 Hz，可按底盘能力调整 |
| 坐标方向 | `linear_x` 正方向、`angular_z` 正方向 |
| 限速参数 | 最大线速度、最大角速度、加速度限制 |
| 急停策略 | 急停触发、恢复流程 |
| 时间戳来源 | 使用底盘本地时间，还是 RK / PC 时间 |
