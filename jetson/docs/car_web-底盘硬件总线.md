# car_web 底盘硬件总线

> 记录 Jetson 上底盘控制项目的串口拓扑、驱动器/传感器与 Modbus 约定。  
> 核验日期：2026-07-20，目标机 `172.0.0.82`。

## 代码从哪来

| 路径 | 角色 |
|------|------|
| `~/newCarProject` | **同事原项目**（权威源；仓库约定不改） |
| `~/qt/car_web` | 从 `~/newCarProject` 拷到 `~/qt/` 的工作副本，供本仓库 ROS2 / cockpit 对接 |
| `jetson/mirror/car_web/` | PC 侧只读镜像（`jetson.sh pull car_web`） |

2026-07-20 对比：`main.py`、`rwd_control.py`、`steer_control.py`、`rear_lift.py`、`front_grab.py` 与源项目 **md5 一致**；`front_walk.py` / `tilt_sensor.py` / `level_control.py` / `static/*` / `tool/*` 有少量差异。两边都是 stdlib `HTTPServer`，端口 `0.0.0.0:8080`。

相关文档：HTTP 对接见 [cmd_vel-car_web-对接方案.md](./cmd_vel-car_web-对接方案.md)；目录约束见 [../README.md](../README.md)。

## 总览

```text
HTTP GET :8080/api/...
  -> main.py (CarControlHandler)
  -> model/*.py  (pyserial + Modbus-RTU CRC16)
  -> /dev/serial1..5  (udev 别名)
  -> CH340×4 + FT232×1  -> RS485/UART 驱动器与传感器
```

统一波特率 **9600**。协议为 **Modbus-RTU**（`tool/crc16_modbus.py`）。端口写死在各 `model/*.py`，靠 udev 固定物理口；`config/` 目录目前为空。

## 串口别名（udev）

规则文件：`/etc/udev/rules.d/99-usb.rules`（按 **USB 口路径** `KERNELS` 绑定，换插口会错位）。

```text
KERNEL=="ttyCH341USB*", KERNELS=="1-2.1.2", MODE:="0777", SYMLINK+="serial1"
KERNEL=="ttyCH341USB*", KERNELS=="1-2.1.1", MODE:="0777", SYMLINK+="serial2"
KERNEL=="ttyCH341USB*", KERNELS=="1-2.1.3", MODE:="0777", SYMLINK+="serial3"
KERNEL=="ttyCH341USB*", KERNELS=="1-2.1.4", MODE:="0777", SYMLINK+="serial4"
KERNEL=="ttyUSB*",      KERNELS=="1-2.3",   MODE:="0777", SYMLINK+="serial5"
```

| 别名 | 实机节点（例） | USB 路径 | 芯片 | 总线用途 |
|------|----------------|----------|------|----------|
| `/dev/serial1` | `ttyCH341USB2` | `1-2.1.2` | CH340 | 后轮驱动 + 前轮转向（共总线） |
| `/dev/serial2` | `ttyCH341USB1` | `1-2.1.1` | CH340 | 后侧升降 + 前侧扒手（共总线） |
| `/dev/serial3` | `ttyCH341USB3` | `1-2.1.3` | CH340 | 前轮行走 L/R |
| `/dev/serial4` | `ttyCH341USB4` | `1-2.1.4` | CH340 | 转向角度传感器 |
| `/dev/serial5` | `ttyUSB0` | `1-2.3` | FT232 | 车身倾角传感器 |

`main.py` 注释里的 `COM10`–`COM14` 是 Windows 开发时的口名；Linux 上以 `/dev/serial*` 为准。

启动顺序（串口宿主先开，再挂复用模块）：

1. `rwd_motor_init()` → serial1  
2. `steer_motor_init()` → 复用 serial1；`angle_sensor_init()` → serial4  
3. `rear_lift_init()` → serial2  
4. `grab_motor_init()` → 复用 serial2  
5. `front_walk_init()` → serial3  
6. `tilt_sensor_init()` → serial5  

## 执行机构与传感器

### 1. 后轮驱动 — `model/rwd_control.py`

| 项 | 值 |
|----|-----|
| 驱动器 | FT-DM-01B 双路直流电机驱动器 |
| 串口 | `/dev/serial1`，设备地址 **1** |
| 写命令 | 功能码 `0x10`，方向+速度连续写 |
| 电机1（后右） | 寄存器 `0x0004` 方向、`0x0005` 速度 |
| 电机2（后左） | 寄存器 `0x0009` 方向、`0x000A` 速度 |
| 速度 | `0–100`（%） |
| 方向 | `0`=正转，`1`=反转 |

前进/后退拼装（`rear_drive`）：

- **前进** `dir=1`：电机1 反转 + 电机2 正转  
- **后退** `dir=0`：电机1 正转 + 电机2 反转  

HTTP：`/api/rear_drive?dr=&sp=`、`/api/rear_stop`、`/api/rear_walk/run?...`

### 2. 前轮转向 — `model/steer_control.py`

| 项 | 值 |
|----|-----|
| 驱动器 | 同型号 FT-DM-01B，**同串口 serial1**，地址 **2** |
| 电机1 | 右转向轮（寄存器同后轮电机1 布局） |
| 电机2 | 左转向轮 |
| 角度传感器 | `/dev/serial4`，地址 `0x01`，功能码 **`0x04`** 读输入寄存器 |
| 换算 | raw→电压 `(raw-30000)*0.001`；电压→角度 `V*72`（0–5V → 0–360°） |
| 闭环 | `steer_to_angle`：左右独立线程监测，死区 **2°**，过冲/超时停本轮 |

HTTP：`/api/steer/run`、`/api/steer/to_angle`、`/api/steer/stop`、`/api/steer/angle`

### 3. 后侧支腿升降 — `model/rear_lift.py`

| 项 | 值 |
|----|-----|
| 驱动器 | AQMD2403NS-M2B（成都爱控），RS485 |
| 串口 | `/dev/serial2`，地址 **1**（本模块为串口宿主） |
| 电机 | 直流有刷 + 编码器，位置闭环 |
| 限位 | SQ1 / SQ2（寄存器 `0x0018`/`0x0019`，`0x0000`=触发） |
| 找零 | 写 `0x00CF=0x0003`（SQ2 复位），到位后可写 `0x700A` 位置清零 |
| 绝对位置 | 写 `0x0046` 起多寄存器（转速 + 类型 + 32 位目标） |
| 速度模式 | 写 `0x0040`（有符号）；停止再写 `0x0044=1` 释放 |
| 读位置 | `0x002C–0x002D`（32 位） |

HTTP：`/api/lift/home|move_to|position|stop|limits|speed_run`

### 4. 前侧扒手 — `model/front_grab.py`

与升降同型号、**同 serial2**、地址 **2**。限位约定：SQ1=顶部原点，SQ2=行程限位。API 与升降对称（`/api/grab/*`）。未找零禁止 `move_to`。

### 5. 前轮行走 — `model/front_walk.py`

| 项 | 值 |
|----|-----|
| 串口 | `/dev/serial3` |
| 地址 | 右轮 `1`，左轮 `2`（拨码） |
| 速度 | 功能码 `0x10` 写寄存器 `0x0008`（转/分钟） |
| 点动 | 线圈 `0x0004` 正转、`0x0005` 反转（`0x05` 写线圈） |

HTTP：`/api/front_walk/run?id=&speed=&dir=`、`/api/front_walk/stop`

### 6. 倾角与调平 — `tilt_sensor.py` / `level_control.py`

| 项 | 值 |
|----|-----|
| 倾角串口 | `/dev/serial5`（FTDI），地址 1 |
| 读角 | 功能码 `0x03`，寄存器 `0x0000`；`raw/100` = 角度（°），有符号 |
| 调平 | 后台线程：`|angle|≤1°` 死区；前倾降后侧升降速度，后倾降前侧扒手速度 |

HTTP：`/api/tilt/angle`、`/api/leveling/start|stop|status`

### 7. 未实现

- `/api/stair/climb`、`/api/stair/stop`：占位，未接真实爬楼流程。

## 实机快检（只读）

```bash
# 别名与芯片
ls -la /dev/serial1 /dev/serial2 /dev/serial3 /dev/serial4 /dev/serial5
lsusb | grep -E '1a86:7523|0403:6001'

# 服务是否在跑
ss -lntp | grep 8080   # 或 netstat -lntp

# 可选：Modbus 口探测（会短暂占用串口）
cd ~/qt/car_web && python3 tool/port_scanner.py
```

换 USB 口后：用 `udevadm info -a -n /dev/ttyCH341USBx` 核对 `KERNELS`，再改 `99-usb.rules`，然后：

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## 与 ROS2 的边界

- 真机电机只由 `car_web`（或同事的 `~/newCarProject`）经串口驱动。  
- 本仓库 `cmd_vel_car_web_bridge` 只做 ROS → HTTP；**不直接开串口**。  
- 不修改 `~/newCarProject`；对 `~/qt/car_web` 的改动也需与同事对齐后再 pull 镜像。
